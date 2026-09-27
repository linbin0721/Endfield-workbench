"""Pure boundary tests for the strict inventory derivation rules.

No image or OCR dependency: these tests describe exactly when a missing value
may be recovered from the target total lift and when it must stay empty.
"""

from app.puzzles.balloon.derive import TARGET_MIN_CONFIDENCE, derive_missing_entry, lift_from_lift_text


def test_missing_count_is_recovered_by_residual() -> None:
    # 5x2 + 3x1 + (2x?) = 19, usable 8, so the only completion is 2x3.
    derived = derive_missing_entry([(5, 2), (3, 1), (2, None)], 19, 8, target_confidence=.99)
    assert derived is not None
    assert (derived.index, derived.lift, derived.count) == (2, 2, 3)
    assert "第 3 行" in derived.message and "推导" in derived.message and "19" in derived.message


def test_missing_row_is_recovered_from_the_unique_factor_pair() -> None:
    # 6x1 + 3x1 + 2x3 = 15, target 18, usable 8. Lift 3 is already used and the
    # remaining capacity is 3, so 1x3 is the only valid factor pair.
    derived = derive_missing_entry([(6, 1), (3, 1), (2, 3), (None, None)], 18, 8, target_confidence=.99)
    assert derived is not None
    assert (derived.index, derived.lift, derived.count) == (3, 1, 3)
    assert "第 4 行" in derived.message and "推导" in derived.message and "18" in derived.message


def test_low_target_confidence_keeps_the_field_empty() -> None:
    entries = [(6, 1), (3, 1), (2, 3), (None, None)]
    assert derive_missing_entry(entries, 18, 8, target_confidence=TARGET_MIN_CONFIDENCE - .01) is None
    assert derive_missing_entry(entries, 18, 8, target_confidence=None) is None
    assert derive_missing_entry(entries, 18, 8, target_confidence=TARGET_MIN_CONFIDENCE) is not None


def test_ambiguous_factor_pairs_stay_empty() -> None:
    # residual 6 with no used lifts matches 2x3, 3x2 and 6x1 (1x6 is blocked by lift 1).
    assert derive_missing_entry([(1, 1), (None, None)], 7, 8, target_confidence=.99) is None


def test_no_candidate_stays_empty() -> None:
    # residual 1 has no lift left: 1 is already used and every other lift is too large.
    assert derive_missing_entry([(1, 1), (3, 1), (None, None)], 5, 8, target_confidence=.99) is None


def test_non_divisible_residual_stays_empty() -> None:
    # residual 7 is not divisible by the known lift 2.
    assert derive_missing_entry([(5, 2), (3, 1), (2, None)], 20, 8, target_confidence=.99) is None


def test_over_capacity_stays_empty() -> None:
    # 2x6 would fit the target but the total count 9 exceeds the 8 usable cells.
    assert derive_missing_entry([(5, 2), (3, 1), (2, None)], 25, 8, target_confidence=.99) is None
    # 1x3 fits the target but the total count 8 exceeds the 7 recognized usable cells.
    assert derive_missing_entry([(6, 1), (3, 1), (2, 3), (None, None)], 18, 7, target_confidence=.99) is None
    # A single count above the 18-balloon limit is never accepted.
    assert derive_missing_entry([(2, 5), (3, 1), (1, None)], 33, 18, target_confidence=.99) is None


def test_conflict_blocks_derivation_completely() -> None:
    # The count cleared by a total-lift conflict must not be filled again from
    # the same target, and no other entry may be derived after such a conflict.
    assert derive_missing_entry([(5, 2), (3, 1), (2, None)], 19, 8,
                                target_confidence=.99, conflict_index=2) is None
    assert derive_missing_entry([(6, 1), (3, 1), (2, 3), (None, None)], 18, 8,
                                target_confidence=.99, conflict_index=0) is None


def test_complete_or_unusable_inventory_is_never_touched() -> None:
    assert derive_missing_entry([(6, 3), (3, 3), (2, 3), (1, 3)], 36, 16, target_confidence=.99) is None
    assert derive_missing_entry([(6, None), (None, 3)], 18, 8, target_confidence=.99) is None
    assert derive_missing_entry([(6, 1), (None, None), (None, None)], 18, 8, target_confidence=.99) is None
    assert derive_missing_entry([(6, 1), (3, 1), (3, None)], 18, 8, target_confidence=.99) is None
    assert derive_missing_entry([(6, 1), (None, None)], 18, 0, target_confidence=.99) is None
    assert derive_missing_entry([], 18, 8, target_confidence=.99) is None
    assert derive_missing_entry([(6, 1), (None, None)], None, 8, target_confidence=.99) is None
    assert derive_missing_entry([(6, 1), (None, None)], 0, 8, target_confidence=.99) is None


def test_lift_text_evidence_ignores_levels_and_the_arrow_digit() -> None:
    assert lift_from_lift_text("[升力...6]") == 6
    assert lift_from_lift_text("[升力：.3]") == 3
    assert lift_from_lift_text("升力1↑") == 1
    assert lift_from_lift_text("[升力..11]") is None  # "1" plus the ↑ arrow read as another digit
    assert lift_from_lift_text("升力 10") is None  # multi-digit text is ambiguous, so it stays unread
    assert lift_from_lift_text("升力 0") is None
    assert lift_from_lift_text("[升力") is None
    assert lift_from_lift_text("4级回收气球") is None  # the level is not a lift
    assert lift_from_lift_text("回收需使用全部气球") is None
