"""Real PostgreSQL tests for the independent source-circuit catalog store.

Set ``CATALOG_TEST_DSN`` to a throwaway PostgreSQL database. The suite only
truncates the three ``circuit_catalog_*`` tables and never changes balloon data.
"""

from __future__ import annotations

import copy
import hashlib
import os
import threading

import psycopg
import pytest

from app.catalog.circuit_rules import circuit_puzzle_fingerprint
from app.catalog.circuit_store import (
    CircuitObservation,
    PostgresCircuitCatalogStore,
)


DSN = os.getenv("CATALOG_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="CATALOG_TEST_DSN is not set")

PUZZLE = {
    "rule_version": "line-count-v1",
    "rows": 2,
    "columns": 2,
    "channels": [
        {"index": 0, "row_targets": [2, 0], "column_targets": [1, 1]}
    ],
    "blocked_cells": [],
    "fixed_cells": [],
    "pieces": [{
        "channel": 0,
        "cells": [{"row": 0, "column": 0}, {"row": 0, "column": 1}],
    }],
}
VERTICAL_PUZZLE = {
    **PUZZLE,
    "channels": [
        {"index": 0, "row_targets": [1, 1], "column_targets": [2, 0]}
    ],
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def observation(puzzle: dict, image: str) -> CircuitObservation:
    return CircuitObservation(
        code="V40020",
        image_sha256=digest(image),
        fingerprint=circuit_puzzle_fingerprint(puzzle),
        puzzle=copy.deepcopy(puzzle),
    )


def _balloon_snapshot(connection: psycopg.Connection) -> tuple:
    tables = tuple(
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
            "AND tablename LIKE 'balloon_catalog_%' ORDER BY tablename"
        ).fetchall()
    )
    snapshot = []
    for table in tables:
        # Names came from pg_catalog and are additionally restricted to the
        # fixed prefix; Identifier keeps the diagnostic safe and generic.
        query = psycopg.sql.SQL(
            "SELECT count(*), coalesce(md5(string_agg(row_to_json(t)::text, '|' "
            "ORDER BY row_to_json(t)::text)), '') FROM {} AS t"
        ).format(psycopg.sql.Identifier(table))
        snapshot.append((table, *connection.execute(query).fetchone()))
    return tables, tuple(snapshot)


@pytest.fixture()
def store() -> PostgresCircuitCatalogStore:
    with psycopg.connect(DSN) as connection:
        balloon_before = _balloon_snapshot(connection)
    created = PostgresCircuitCatalogStore(
        DSN, timeout=10, min_size=1, max_size=10
    )
    created.get("V00000")
    with psycopg.connect(DSN) as connection:
        assert _balloon_snapshot(connection) == balloon_before
        connection.execute(
            "TRUNCATE circuit_catalog_observation, circuit_catalog_candidate, "
            "circuit_catalog_entry RESTART IDENTITY CASCADE"
        )
        connection.commit()
    yield created
    created.close()
    with psycopg.connect(DSN) as connection:
        assert _balloon_snapshot(connection) == balloon_before


def test_schema_has_only_three_independent_circuit_tables(
    store: PostgresCircuitCatalogStore,
) -> None:
    assert store.get("V40020") is None
    with psycopg.connect(DSN) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
                "AND tablename LIKE 'circuit_catalog_%'"
            ).fetchall()
        }
    assert tables == {
        "circuit_catalog_entry",
        "circuit_catalog_candidate",
        "circuit_catalog_observation",
    }


def test_record_duplicate_confirmation_variants_and_stable_order(
    store: PostgresCircuitCatalogStore,
) -> None:
    first, disposition = store.record(observation(PUZZLE, "a1"))
    assert disposition == "recorded"
    assert first.candidates[0].status == "provisional"

    duplicate, disposition = store.record(observation(PUZZLE, "a1"))
    assert disposition == "duplicate"
    assert duplicate.candidates[0].observations == 1

    second_variant, disposition = store.record(
        observation(VERTICAL_PUZZLE, "b1")
    )
    assert disposition == "recorded"
    assert len(second_variant.candidates) == 2
    assert all(item.status == "provisional" for item in second_variant.candidates)

    confirmed_b, _ = store.record(observation(VERTICAL_PUZZLE, "b2"))
    assert [item.status for item in confirmed_b.candidates] == [
        "verified", "provisional"
    ]
    assert confirmed_b.candidates[0].fingerprint == circuit_puzzle_fingerprint(
        VERTICAL_PUZZLE
    )

    confirmed_both, _ = store.record(observation(PUZZLE, "a2"))
    assert [item.observations for item in confirmed_both.candidates] == [2, 2]
    # With equal status/count, the first-seen A variant returns first.
    assert confirmed_both.candidates[0].fingerprint == circuit_puzzle_fingerprint(
        PUZZLE
    )


def test_digest_mismatch_keeps_original_observation_and_candidates(
    store: PostgresCircuitCatalogStore,
) -> None:
    original, _ = store.record(observation(PUZZLE, "same"))
    mismatch, disposition = store.record(observation(VERTICAL_PUZZLE, "same"))
    assert disposition == "digest_mismatch"
    assert mismatch == original
    assert len(mismatch.candidates) == 1
    assert mismatch.candidates[0].observations == 1
    with psycopg.connect(DSN) as connection:
        observed = connection.execute(
            "SELECT fingerprint FROM circuit_catalog_observation "
            "WHERE code = 'V40020' AND image_sha256 = %s",
            (digest("same"),),
        ).fetchone()[0]
    assert observed == circuit_puzzle_fingerprint(PUZZLE)


def test_ten_concurrent_identical_observations_count_once(
    store: PostgresCircuitCatalogStore,
) -> None:
    dispositions: list[str] = []
    lock = threading.Lock()

    def record() -> None:
        _, disposition = store.record(observation(PUZZLE, "concurrent"))
        with lock:
            dispositions.append(disposition)

    threads = [threading.Thread(target=record) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert dispositions.count("recorded") == 1
    assert dispositions.count("duplicate") == 9
    entry = store.get("V40020")
    assert entry is not None and entry.candidates[0].observations == 1
