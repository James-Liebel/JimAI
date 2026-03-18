"""SymPy math tool — symbolic computation with LaTeX output."""

import logging

import sympy
from sympy import (
    Symbol, symbols, sympify, latex,
    integrate as sym_integrate,
    diff as sym_diff,
    solve as sym_solve,
    simplify as sym_simplify,
    Matrix,
)
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)

logger = logging.getLogger(__name__)

_transformations = standard_transformations + (implicit_multiplication_application,)


def _safe_parse(expr_str: str) -> sympy.Expr:
    """Parse a string expression into a SymPy expression."""
    return parse_expr(expr_str, transformations=_transformations)


async def solve_equation(expr: str, var: str = "x") -> dict:
    """Solve an equation (expression = 0) for the given variable."""
    try:
        v = Symbol(var)
        parsed = _safe_parse(expr)
        solutions = sym_solve(parsed, v)
        result_str = str(solutions)
        latex_str = latex(solutions)
        return {"result": result_str, "latex": latex_str, "verified": True}
    except Exception as exc:
        return {"result": str(exc), "latex": "", "verified": False}


async def integrate(
    expr: str, var: str = "x", lower: str | None = None, upper: str | None = None
) -> dict:
    """Compute indefinite or definite integral."""
    try:
        v = Symbol(var)
        parsed = _safe_parse(expr)
        if lower is not None and upper is not None:
            result = sym_integrate(parsed, (v, sympify(lower), sympify(upper)))
        else:
            result = sym_integrate(parsed, v)
        return {"result": str(result), "latex": latex(result), "verified": True}
    except Exception as exc:
        return {"result": str(exc), "latex": "", "verified": False}


async def differentiate(expr: str, var: str = "x", order: int = 1) -> dict:
    """Compute the nth derivative."""
    try:
        v = Symbol(var)
        parsed = _safe_parse(expr)
        result = sym_diff(parsed, v, order)
        return {"result": str(result), "latex": latex(result), "verified": True}
    except Exception as exc:
        return {"result": str(exc), "latex": "", "verified": False}


async def eigenvalues(matrix_str: str) -> dict:
    """Compute eigenvalues of a matrix (input as nested list string)."""
    try:
        import ast
        nested = ast.literal_eval(matrix_str)
        m = Matrix(nested)
        eigs = m.eigenvals()
        result_str = str(eigs)
        latex_str = latex(eigs)
        return {"result": result_str, "latex": latex_str, "verified": True}
    except Exception as exc:
        return {"result": str(exc), "latex": "", "verified": False}


async def simplify_expr(expr: str) -> dict:
    """Simplify a mathematical expression."""
    try:
        parsed = _safe_parse(expr)
        result = sym_simplify(parsed)
        return {"result": str(result), "latex": latex(result), "verified": True}
    except Exception as exc:
        return {"result": str(exc), "latex": "", "verified": False}


async def numerical_eval(expr: str) -> dict:
    """Evaluate an expression numerically."""
    try:
        parsed = _safe_parse(expr)
        result = parsed.evalf()
        return {"result": str(result), "latex": latex(result), "verified": True}
    except Exception as exc:
        return {"result": str(exc), "latex": "", "verified": False}
