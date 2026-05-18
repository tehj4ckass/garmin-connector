import pytest
from garmin_parser import to_float

def test_to_float_none():
    assert to_float(None) is None

def test_to_float_bool():
    assert to_float(True) is True
    assert to_float(False) is False

def test_to_float_int():
    assert to_float(10) == 10.0
    assert isinstance(to_float(10), float)

def test_to_float_float():
    assert to_float(10.5) == 10.5

def test_to_float_numeric_string():
    assert to_float("123.45") == 123.45
    assert to_float("10") == 10.0

def test_to_float_invalid_string():
    assert to_float("abc") is None

def test_to_float_list():
    assert to_float([1, 2]) is None

def test_to_float_dict():
    assert to_float({"key": "value"}) is None

def test_to_float_complex_object():
    class TestObj:
        pass
    assert to_float(TestObj()) is None
