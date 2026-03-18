"""LaTeX rendering tool — renders LaTeX expressions to base64 PNG."""

import base64
import io
import logging

logger = logging.getLogger(__name__)


async def render(latex_expr: str) -> str:
    """Render a LaTeX expression to a base64-encoded PNG image.

    Returns empty string on failure.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # Clean up the expression
        expr = latex_expr.strip()
        if expr.startswith("$$"):
            expr = expr[2:]
        if expr.endswith("$$"):
            expr = expr[:-2]
        if expr.startswith("$"):
            expr = expr[1:]
        if expr.endswith("$"):
            expr = expr[:-1]

        fig, ax = plt.subplots(figsize=(6, 1.5))
        ax.set_axis_off()
        ax.text(
            0.5, 0.5,
            f"${expr}$",
            fontsize=18,
            ha="center", va="center",
            transform=ax.transAxes,
        )

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150, pad_inches=0.1)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    except Exception as exc:
        logger.warning("LaTeX render failed: %s", exc)
        return ""
