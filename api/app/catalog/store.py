"""PostgreSQL-backed catalog store.

Only the API process opens these connections. The OCR subprocess receives image
bytes and returns JSON; it never talks to the database. Every observation is
recorded in one transaction that locks the question-number row, so concurrent
uploads of the same screenshot stay idempotent and a second distinct image can
upgrade a candidate instead of overwriting it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Protocol, TypeVar

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.catalog.models import CatalogCandidate, CatalogEntry, CatalogStatus
from app.puzzles.balloon.model import BalloonPuzzle

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS balloon_catalog_entry (
        code text PRIMARY KEY,
        status text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS balloon_catalog_candidate (
        id bigserial PRIMARY KEY,
        code text NOT NULL REFERENCES balloon_catalog_entry(code) ON DELETE CASCADE,
        fingerprint text NOT NULL,
        puzzle jsonb NOT NULL,
        target_total_lift integer,
        observations integer NOT NULL DEFAULT 0,
        first_seen timestamptz NOT NULL DEFAULT now(),
        last_seen timestamptz NOT NULL DEFAULT now(),
        UNIQUE (code, fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS balloon_catalog_observation (
        id bigserial PRIMARY KEY,
        code text NOT NULL,
        image_sha256 text NOT NULL,
        fingerprint text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (code, image_sha256)
    )
    """,
    "CREATE INDEX IF NOT EXISTS balloon_catalog_observation_code_idx ON balloon_catalog_observation (code)",
)


class CatalogUnavailable(Exception):
    """The catalog database is not configured or cannot be reached right now."""


@dataclass(frozen=True)
class Observation:
    code: str
    image_sha256: str
    fingerprint: str
    puzzle: dict[str, Any]
    target_total_lift: int | None


class CatalogStore(Protocol):
    def record(self, observation: Observation) -> tuple[CatalogEntry, bool]:
        """Store one observation. Returns the entry and whether it was new."""

    def get(self, code: str) -> CatalogEntry | None: ...

    def close(self) -> None: ...


T = TypeVar("T")


class PostgresCatalogStore:
    def __init__(self, dsn: str, *, timeout: float = 3.0, min_size: int = 1, max_size: int = 4):
        self._dsn = dsn
        self._timeout = timeout
        self._min_size = min_size
        self._max_size = max_size
        self._lock = Lock()
        self._pool: ConnectionPool | None = None
        self._schema_ready = False

    def record(self, observation: Observation) -> tuple[CatalogEntry, bool]:
        def work(connection: psycopg.Connection[Any]) -> tuple[CatalogEntry, bool]:
            connection.execute(
                "INSERT INTO balloon_catalog_entry (code, status) VALUES (%s, 'provisional') "
                "ON CONFLICT (code) DO NOTHING",
                (observation.code,),
            )
            # Serialize concurrent observations of the same question number.
            connection.execute("SELECT 1 FROM balloon_catalog_entry WHERE code = %s FOR UPDATE",
                               (observation.code,))
            inserted = connection.execute(
                "INSERT INTO balloon_catalog_observation (code, image_sha256, fingerprint) "
                "VALUES (%s, %s, %s) ON CONFLICT (code, image_sha256) DO NOTHING RETURNING id",
                (observation.code, observation.image_sha256, observation.fingerprint),
            ).fetchone()
            if inserted is not None:
                connection.execute(
                    "INSERT INTO balloon_catalog_candidate "
                    "(code, fingerprint, puzzle, target_total_lift, observations) VALUES (%s, %s, %s, %s, 1) "
                    "ON CONFLICT (code, fingerprint) DO UPDATE SET "
                    "observations = balloon_catalog_candidate.observations + 1, last_seen = now()",
                    (observation.code, observation.fingerprint, Jsonb(observation.puzzle),
                     observation.target_total_lift),
                )
                counts = connection.execute(
                    "SELECT (SELECT count(*) FROM balloon_catalog_candidate WHERE code = %s) AS candidates, "
                    "(SELECT observations FROM balloon_catalog_candidate WHERE code = %s AND fingerprint = %s) AS confirmed",
                    (observation.code, observation.code, observation.fingerprint),
                ).fetchone()
                connection.execute(
                    "UPDATE balloon_catalog_entry SET status = %s, updated_at = now() WHERE code = %s",
                    (_status(int(counts["candidates"]), int(counts["confirmed"])), observation.code),
                )
            entry = self._entry(connection, observation.code)
            if entry is None:
                raise CatalogUnavailable("题号目录记录写入后无法读回")
            return entry, inserted is not None

        return self._with_connection(work)

    def get(self, code: str) -> CatalogEntry | None:
        return self._with_connection(lambda connection: self._entry(connection, code))

    def close(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.close()

    def _with_connection(self, work: Callable[[psycopg.Connection[Any]], T]) -> T:
        pool = self._open_pool()
        try:
            with pool.connection(timeout=self._timeout) as connection:
                self._ensure_schema(connection)
                with connection.transaction():
                    return work(connection)
        except CatalogUnavailable:
            raise
        except Exception as exc:  # psycopg errors, pool timeouts, schema failures
            self._drop_pool()
            raise CatalogUnavailable("题号目录数据库暂时不可用") from exc

    def _open_pool(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None:
                try:
                    pool = ConnectionPool(conninfo=self._dsn, min_size=self._min_size, max_size=self._max_size,
                                          timeout=self._timeout, open=False,
                                          kwargs={"connect_timeout": self._timeout, "row_factory": dict_row})
                    pool.open(wait=True, timeout=self._timeout)
                except Exception as exc:
                    raise CatalogUnavailable("无法连接题号目录数据库") from exc
                self._pool = pool
            return self._pool

    def _drop_pool(self) -> None:
        with self._lock:
            pool, self._pool, self._schema_ready = self._pool, None, False
        if pool is not None:
            pool.close()

    def _ensure_schema(self, connection: psycopg.Connection[Any]) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()
        self._schema_ready = True

    def _entry(self, connection: psycopg.Connection[Any], code: str) -> CatalogEntry | None:
        row = connection.execute("SELECT code, status, updated_at FROM balloon_catalog_entry WHERE code = %s",
                                 (code,)).fetchone()
        if row is None:
            return None
        candidates = [
            CatalogCandidate(
                fingerprint=item["fingerprint"],
                puzzle=BalloonPuzzle.model_validate(item["puzzle"]),
                target_total_lift=item["target_total_lift"],
                observations=int(item["observations"]),
                first_seen=_as_utc(item["first_seen"]),
                last_seen=_as_utc(item["last_seen"]),
            )
            for item in connection.execute(
                "SELECT fingerprint, puzzle, target_total_lift, observations, first_seen, last_seen "
                "FROM balloon_catalog_candidate WHERE code = %s ORDER BY first_seen, id",
                (code,),
            ).fetchall()
        ]
        return CatalogEntry(code=row["code"], status=_status_value(row["status"]),
                            candidates=candidates, updated_at=_as_utc(row["updated_at"]))


def _status(candidate_count: int, confirmed_observations: int) -> str:
    if candidate_count > 1:
        return "disputed"
    if confirmed_observations >= 2:
        return "verified"
    return "provisional"


def _status_value(raw: str) -> CatalogStatus:
    return raw if raw in ("provisional", "verified", "disputed") else "provisional"  # type: ignore[return-value]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def catalog_store_from_settings(settings: Any) -> PostgresCatalogStore | None:
    """Build the store from explicit settings; ``None`` keeps the catalog disabled."""
    if not all((settings.catalog_db_host, settings.catalog_db_name,
                settings.catalog_db_user, settings.catalog_db_password)):
        return None
    dsn = make_conninfo(
        host=settings.catalog_db_host,
        port=settings.catalog_db_port,
        dbname=settings.catalog_db_name,
        user=settings.catalog_db_user,
        password=settings.catalog_db_password,
        connect_timeout=settings.catalog_db_timeout_seconds,
    )
    return PostgresCatalogStore(dsn, timeout=settings.catalog_db_timeout_seconds)
