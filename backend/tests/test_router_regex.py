import re

from models.router import (
    classify_message,
    MATH_RES, CODE_RES, DATA_SCIENCE_RES, FINANCE_RES,
)


def test_math_routes_to_math():
    d = classify_message("compute the derivative of sin(x) and find the integral")
    assert d.primary_role == "math"


def test_code_routes_to_code():
    d = classify_message("write a python function to debug this traceback")
    assert d.primary_role == "code"


def test_regexes_are_precompiled():
    for group in (MATH_RES, CODE_RES, DATA_SCIENCE_RES, FINANCE_RES):
        assert group, "regex group should not be empty"
        assert all(isinstance(r, re.Pattern) for r in group)
