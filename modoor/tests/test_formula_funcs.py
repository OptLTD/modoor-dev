import pytest

from modoor.engine.formula import eval_formula


def test_round_supports_optional_digits():
    assert eval_formula("ROUND(12.345)", {}) == 12
    assert eval_formula("ROUND(12.345, 2)", {}) == 12.35


def test_floor_supports_optional_step():
    assert eval_formula("FLOOR(12.9)", {}) == 12.0
    assert eval_formula("FLOOR(12.345, 0.01)", {}) == 12.34
    assert eval_formula("floor(0.3, 0.1)", {}) == 0.3


def test_ceil_supports_optional_step():
    assert eval_formula("CEIL(12.1)", {}) == 13.0
    assert eval_formula("CEIL(12.345, 0.01)", {}) == 12.35
    assert eval_formula("ceiling(0.3, 0.1)", {}) == 0.3


def test_floor_and_ceil_follow_negative_direction():
    assert eval_formula("FLOOR(-1.1)", {}) == -2.0
    assert eval_formula("CEIL(-1.1)", {}) == -1.0


def test_floor_and_ceil_zero_step_returns_zero():
    assert eval_formula("FLOOR(12.9, 0)", {}) == 0.0
    assert eval_formula("CEIL(12.1, 0)", {}) == 0.0


def test_floor_and_ceil_read_field_values():
    objects = {"items": {"price": "12.345"}, "basic": {"qty": 2}}
    assert eval_formula("FLOOR(items.price, 0.01)", objects) == 12.34
    assert eval_formula("CEIL(items.price * basic.qty, 0.1)", objects) == 24.7


def test_unknown_formula_function_still_rejected():
    with pytest.raises(ValueError, match="unsupported function"):
        eval_formula("ROUNDUP(12.345, 2)", {})
