import pytest
from garmin_parser import get_first

def test_get_first_basic():
    """Test retrieving the first available key."""
    d = {"a": 1, "b": 2}
    assert get_first(d, ["a", "b"]) == 1
    assert get_first(d, ["b", "a"]) == 2
    assert get_first(d, ["c", "b"]) == 2

def test_get_first_none_values():
    """Test that None values are skipped."""
    d = {"a": None, "b": 2, "c": None}
    assert get_first(d, ["a", "b"]) == 2
    assert get_first(d, ["c", "a"]) is None
    assert get_first(d, ["a", "c", "b"]) == 2

def test_get_first_falsy_values():
    """Test that valid falsy values (0, False, "") are not skipped."""
    d = {"a": 0, "b": False, "c": "", "d": 2}
    assert get_first(d, ["a", "d"]) == 0
    assert get_first(d, ["b", "d"]) is False
    assert get_first(d, ["c", "d"]) == ""

def test_get_first_missing_keys():
    """Test behavior when keys are not in the dictionary."""
    d = {"a": 1, "b": 2}
    assert get_first(d, ["c", "d"]) is None

def test_get_first_empty_inputs():
    """Test with empty dictionary and/or empty keys list."""
    assert get_first({}, ["a", "b"]) is None
    assert get_first({"a": 1}, []) is None
    assert get_first({}, []) is None
