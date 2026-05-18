import pytest
from dashboard.dashboard_data import _safe_float

def test_safe_float_happy_paths():
    assert _safe_float(1.0) == 1.0
    assert _safe_float(1) == 1.0
    assert _safe_float("1.5") == 1.5
    assert _safe_float("2") == 2.0
    assert _safe_float("-3.14") == -3.14
    assert _safe_float(0) == 0.0

def test_safe_float_null_paths():
    assert _safe_float(None) is None

def test_safe_float_value_error():
    assert _safe_float("invalid") is None
    assert _safe_float("") is None
    assert _safe_float("1.2.3") is None

def test_safe_float_type_error():
    assert _safe_float([1, 2]) is None
    assert _safe_float({"a": 1}) is None
    assert _safe_float(set([1, 2])) is None
