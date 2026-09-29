"""PostgreSQL store for the source-circuit catalog's independent tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Literal, Protocol, TypeVar

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from app.catalog.circuit_models import (
    CircuitCatalogCandidate,
    CircuitCatalogEntry,
)
from app.catalog.circuit_rules import (
    circuit_puzzle_fingerprint,
    normalize_circuit_code,
)
from app.catalog.store import CatalogUnavailable
from app.puzzles.circuit.model import CircuitPuzzle


CircuitRecordDisposition = Literal["recorded", "duplicate", "digest_mismatch"]

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS circuit_catalog_entry (
        code text PRIMARY KEY CHECK (code ~ '^(V[0-9]{5}|WL[0-9]{4})$'),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS circuit_catalog_candidate (
        id bigserial PRIMARY KEY,
        code text NOT NULL REFERENCES circuit_catalog_entry(code) ON DELETE CASCADE,
        fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
        puzzle jsonb NOT NULL,
        observations integer NOT NULL DEFAULT 1 CHECK (observations >= 1),
        first_seen timestamptz NOT NULL DEFAULT now(),
        last_seen timestamptz NOT NULL DEFAULT now(),
        UNIQUE (code, fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS circuit_catalog_observation (
        id bigserial PRIMARY KEY,
        code text NOT NULL,
        image_sha256 text NOT NULL CHECK (image_sha256 ~ '^[0-9a-f]{64}$'),
        fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (code, image_sha256)
    )
    """,
    "CREATE INDEX IF NOT EXISTS circuit_catalog_observation_code_idx ON circuit_catalog_observation (code)",
)


@dataclass(frozen=True)
class CircuitObservation:
    code: str
    image_sha256: str
    fingerprint: str
    puzzle: dict[str, Any]

    def __post_init__(self) -> None:
        if normalize_circuit_code(self.code) != self.code:
            raise ValueError("circuit observation code must be canonical")
        if (
            len(self.image_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.image_sha256)
        ):
            raise ValueError("circuit observation image digest must be lowercase SHA-256")
        validated = CircuitPuzzle.model_validate(self.puzzle)
        if circuit_puzzle_fingerprint(validated) != self.fingerprint:
            raise ValueError("circuit observation fingerprint does not match its puzzle")


class CircuitCatalogStore(Protocol):
    def record(
        self, observation: CircuitObservation
    ) -> tuple[CircuitCatalogEntry, CircuitRecordDisposition]: ...

    def get(self, code: str) -> CircuitCatalogEntry | None: ...

    def close(self) -> None: ...


T = TypeVar("T")


class PostgresCircuitCatalogStore:
    def __init__(
        self,
        dsn: str,
        *,
        timeout: float = 3.0,
        min_size: int = 1,
        max_size: int = 4,
    ):
        self._dsn = dsn
        self._timeout = timeout
        self._min_size = min_size
        self._max_size = max_size
        self._lock = Lock()
        self._schema_lock = Lock()
        self._pool: ConnectionPool | None = None
        self._schema_ready = False

    def record(
        self, observation: CircuitObservation
    ) -> tuple[CircuitCatalogEntry, CircuitRecordDisposition]:
        def work(
            connection: psycopg.Connection[Any],
        ) -> tuple[CircuitCatalogEntry, CircuitRecordDisposition]:
            connection.execute(
                "INSERT INTO circuit_catalog_entry (code) VALUES (%s) "
                "ON CONFLICT (code) DO NOTHING",
                (observation.code,),
            )
            connection.execute(
                "SELECT 1 FROM circuit_catalog_entry WHERE code = %s FOR UPDATE",
                (observation.code,),
            )
            existing = connection.execute(
                "SELECT fingerprint FROM circuit_catalog_observation "
                "WHERE code = %s AND image_sha256 = %s",
                (observation.code, observation.image_sha256),
            ).fetchone()
            if existing is not None:
                disposition: CircuitRecordDisposition = (
                    "duplicate"
                    if existing["fingerprint"] == observation.fingerprint
                    else "digest_mismatch"
                )
                entry = self._entry(connection, observation.code)
                if entry is None:
                    raise CatalogUnavailable("源石电路题号目录记录无法读回")
                return entry, disposition

            connection.execute(
                "INSERT INTO circuit_catalog_observation "
                "(code, image_sha256, fingerprint) VALUES (%s, %s, %s)",
                (
                    observation.code,
                    observation.image_sha256,
                    observation.fingerprint,
                ),
            )
            connection.execute(
                "INSERT INTO circuit_catalog_candidate "
                "(code, fingerprint, puzzle, observations) VALUES (%s, %s, %s, 1) "
                "ON CONFLICT (code, fingerprint) DO UPDATE SET "
                "observations = circuit_catalog_candidate.observations + 1, "
                "last_seen = now()",
                (
                    observation.code,
                    observation.fingerprint,
                    Jsonb(observation.puzzle),
                ),
            )
            connection.execute(
                "UPDATE circuit_catalog_entry SET updated_at = now() WHERE code = %s",
                (observation.code,),
            )
            entry = self._entry(connection, observation.code)
            if entry is None:
                raise CatalogUnavailable("源石电路题号目录记录写入后无法读回")
            return entry, "recorded"

        return self._with_connection(work)

    def get(self, code: str) -> CircuitCatalogEntry | None:
        return self._with_connection(lambda connection: self._entry(connection, code))

    def close(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.close()

    def _with_connection(
        self, work: Callable[[psycopg.Connection[Any]], T]
    ) -> T:
        pool = self._open_pool()
        try:
            with pool.connection(timeout=self._timeout) as connection:
                self._ensure_schema(connection)
                with connection.transaction():
                    return work(connection)
        except CatalogUnavailable:
            raise
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            self._drop_pool()
            raise CatalogUnavailable("源石电路题号目录数据库暂时不可用") from exc

    def _open_pool(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None:
                try:
                    pool = ConnectionPool(
                        conninfo=self._dsn,
                        min_size=self._min_size,
                        max_size=self._max_size,
                        timeout=self._timeout,
                        open=False,
                        kwargs={
                            "connect_timeout": self._timeout,
                            "row_factory": dict_row,
                        },
                    )
                    pool.open(wait=True, timeout=self._timeout)
                except (psycopg.Error, PoolTimeout, OSError, ValueError) as exc:
                    raise CatalogUnavailable(
                        "无法连接源石电路题号目录数据库"
                    ) from exc
                self._pool = pool
            return self._pool

    def _drop_pool(self) -> None:
        with self._lock:
            pool, self._pool, self._schema_ready = self._pool, None, False
        if pool is not None:
            pool.close()

    def _ensure_schema(self, connection: psycopg.Connection[Any]) -> None:
        with self._schema_lock:
            if self._schema_ready:
                return
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()
            self._schema_ready = True

    def _entry(
        self, connection: psycopg.Connection[Any], code: str
    ) -> CircuitCatalogEntry | None:
        row = connection.execute(
            "SELECT code, updated_at FROM circuit_catalog_entry WHERE code = %s",
            (code,),
        ).fetchone()
        if row is None:
            return None
        candidates = [
            CircuitCatalogCandidate(
                fingerprint=item["fingerprint"],
                puzzle=CircuitPuzzle.model_validate(item["puzzle"]),
                status=(
                    "verified" if int(item["observations"]) >= 2 else "provisional"
                ),
                observations=int(item["observations"]),
                first_seen=_as_utc(item["first_seen"]),
                last_seen=_as_utc(item["last_seen"]),
            )
            for item in connection.execute(
                "SELECT id, fingerprint, puzzle, observations, first_seen, last_seen "
                "FROM circuit_catalog_candidate WHERE code = %s "
                "ORDER BY (observations >= 2) DESC, observations DESC, "
                "first_seen ASC, id ASC",
                (code,),
            ).fetchall()
        ]
        return CircuitCatalogEntry(
            code=row["code"],
            candidates=candidates,
            updated_at=_as_utc(row["updated_at"]),
        )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def circuit_catalog_store_from_settings(
    settings: Any,
) -> PostgresCircuitCatalogStore | None:
    """Reuse the existing catalog database settings for the independent store."""
    if not all(
        (
            settings.catalog_db_host,
            settings.catalog_db_name,
            settings.catalog_db_user,
            settings.catalog_db_password,
        )
    ):
        return None
    dsn = make_conninfo(
        host=settings.catalog_db_host,
        port=settings.catalog_db_port,
        dbname=settings.catalog_db_name,
        user=settings.catalog_db_user,
        password=settings.catalog_db_password,
        connect_timeout=settings.catalog_db_timeout_seconds,
    )
    return PostgresCircuitCatalogStore(
        dsn, timeout=settings.catalog_db_timeout_seconds
    )
