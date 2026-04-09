"""Auto tool dispatch for the chat pipeline.

Detects what tool(s) a message needs, runs them before the LLM call, and
returns structured results that get injected into the prompt as context.
The LLM then produces its response with real computed data already in hand.
"""

from __future__ import annotations

import asyncio
import base64 as _b64
import datetime
import hashlib
import json
import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)


# ── Detection patterns ────────────────────────────────────────────────────

_CODE_RUN_TRIGGERS = re.compile(
    r"\b(run|execute|eval|test|check|try)\b.{0,40}\b(this|the|my|following)?\b.{0,20}\b(code|script|snippet|function|program)\b"
    r"|\bwhat\s+(does\s+this|would\s+this|will\s+this)\s+(output|print|return|produce)\b"
    r"|\brun\s+it\b|\bexecute\s+it\b|\btest\s+it\b"
    r"|\bdoes\s+this\s+work\b|\bwill\s+this\s+(work|run|compile)\b",
    re.IGNORECASE,
)
_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

_MATH_EXPR_TRIGGERS = re.compile(
    r"\b(solve|simplify|expand|factor|integrate|differentiate|derivative|compute|calculate|evaluate)\b.{0,60}"
    r"[\d\+\-\*\/\^\(\)x-z]"
    r"|\bwhat\s+is\s+[\d\(\+\-]"
    r"|\bsimplify\s+\S|\bsolve\s+for\b",
    re.IGNORECASE,
)
_MATH_INLINE = re.compile(
    r"(?:solve|simplify|expand|factor|integrate|diff(?:erentiate)?|calculate|evaluate|compute)\s*[:\s]+([^\n]{3,120})",
    re.IGNORECASE,
)

_SYSINFO_TRIGGERS = re.compile(
    r"\b(cpu|processor)\s*(usage|load|percent|utilization|temp|temperature)\b"
    r"|\b(ram|memory)\s*(usage|free|available|used)\b"
    r"|\bdisk\s*(space|usage|free)\b"
    r"|\bsystem\s*(info|status|stats|health)\b"
    r"|\bhow\s+much\s+(ram|memory|disk|cpu)\b"
    r"|\bmy\s+(cpu|ram|memory|disk|machine|computer)\b",
    re.IGNORECASE,
)
_DATETIME_TRIGGERS = re.compile(
    r"\b(what(?:'s|\s+is)\s+(?:today(?:'s)?|the\s+current|the\s+date|the\s+time|today))"
    r"|\bcurrent\s+(date|time|datetime|day)\b"
    r"|\bwhat\s+day\s+is\s+(it|today)\b|\bwhat\s+time\s+is\s+it\b",
    re.IGNORECASE,
)
_CALC_EXPR = re.compile(r"(?:^|\s)([\d\s\+\-\*\/\%\^\(\)\.]{4,80})\s*(?:=\s*\?|$|\?)")

_GIT_TRIGGERS = re.compile(
    r"\bgit\s+(status|log|diff|show|blame|branch|stash)\b"
    r"|\b(what\s+changed|recent\s+commits?|show\s+(me\s+)?the?\s+diff|uncommitted|staged\s+changes)\b"
    r"|\b(git\s+history|commit\s+history|what('s|\s+is)\s+staged)\b",
    re.IGNORECASE,
)
_GIT_SUBCMD = re.compile(
    r"\bgit\s+(status|log|diff|blame)\b"
    r"|\b(status|log|diff)\b.{0,30}\b(repo|repository|project|branch|git)\b",
    re.IGNORECASE,
)

_FILE_READ_TRIGGERS = re.compile(
    r"\b(read|show|open|display|print|cat|look\s+at)\b.{0,30}([\w/\\.-]+\.\w{1,6})"
    r"|\bcontents?\s+of\s+([\w/\\.-]+\.\w{1,6})"
    r"|\bwhat(?:'s|\s+is)\s+in\s+([\w/\\.-]+\.\w{1,6})",
    re.IGNORECASE,
)

_TIMEZONE_TRIGGERS = re.compile(
    r"\bconvert\b.{0,40}\b(time|timezone|tz)\b"
    r"|\bwhat\s+time\s+is\s+it\s+in\b"
    r"|\b(\d{1,2}:\d{2})\s*(am|pm)?\s*(in|to|at)\s+\w+"
    r"|\btimezone\s+convert"
    r"|\b(PST|EST|CST|MST|GMT|UTC|IST|JST|AEST|CET|BST)\b.{0,20}\b(to|in)\b",
    re.IGNORECASE,
)

_UNIT_TRIGGERS = re.compile(
    r"\bconvert\b.{0,60}\b(km|miles?|kg|pounds?|lbs?|celsius|fahrenheit|meters?|feet|inches|gallons?|liters?|oz|ounces?|cm|mm|mph|kph)\b"
    r"|\b\d+\s*(km|miles?|kg|lbs?|°?[CF]|meters?|feet|ft|inches?|in|gallons?|liters?|l|oz|cm|mm|mph|kph)\s+(to|in|into)\b",
    re.IGNORECASE,
)
_UNIT_EXPR = re.compile(
    r"(\d+(?:\.\d+)?)\s*(km|miles?|kg|lbs?|pounds?|°?C|°?F|celsius|fahrenheit|meters?|feet|ft|inches?|gallons?|liters?|l|oz|ounces?|cm|mm|mph|kph)\s+(?:to|in|into)\s+(km|miles?|kg|lbs?|pounds?|°?C|°?F|celsius|fahrenheit|meters?|feet|ft|inches?|gallons?|liters?|l|oz|ounces?|cm|mm|mph|kph)",
    re.IGNORECASE,
)

_HASH_TRIGGERS = re.compile(
    r"\b(md5|sha1|sha256|sha512|hash)\b.{0,30}(of|for|this|the|following|:)"
    r"|\bhash\s+this\b|\bgenerate\s+a?\s*(md5|sha|hash)\b",
    re.IGNORECASE,
)
_HASH_TEXT = re.compile(
    r'(?:md5|sha\d*|hash)\s+(?:of\s+)?["\']?(.{3,200}?)["\']?\s*$',
    re.IGNORECASE,
)

_BASE64_TRIGGERS = re.compile(
    r"\b(encode|decode)\b.{0,20}\b(base64|b64)\b"
    r"|\bbase64\s+(encode|decode)\b"
    r"|\bdecode\s+this\s+base64\b",
    re.IGNORECASE,
)
_BASE64_TEXT = re.compile(
    r"(?:base64\s+(?:encode|decode)\s*:?\s*|(?:encode|decode)\s+(?:this\s+)?(?:in\s+)?base64\s*:?\s*)(.+)",
    re.IGNORECASE | re.DOTALL,
)

_JSON_TRIGGERS = re.compile(
    r"\b(format|pretty.?print|validate|parse|lint)\b.{0,20}\b(json|JSON)\b"
    r"|\bjson\s+(format|validate|parse|check|lint)\b"
    r"|\bis\s+this\s+(valid\s+)?json\b",
    re.IGNORECASE,
)
_JSON_BLOCK = re.compile(r"```(?:json)?\s*\n(\{.*?\}|\[.*?\])\s*```", re.DOTALL)
_JSON_INLINE = re.compile(r"(\{[^{}]{10,}?\}|\[[^\[\]]{10,}?\])", re.DOTALL)

_REGEX_TRIGGERS = re.compile(
    r"\btest\s+(this\s+)?regex\b|\bregex\s+(test|match|check)\b"
    r"|\bdoes\s+(this\s+)?regex\s+match\b"
    r"|\bwill\s+(this\s+)?pattern\s+match\b",
    re.IGNORECASE,
)
_REGEX_PATTERN = re.compile(r"[/`'\"]([^/`'\"]{2,80})[/`'\"]")

_TEXT_STATS_TRIGGERS = re.compile(
    r"\b(word\s+count|character\s+count|reading\s+time|how\s+(many|long)\s+(words?|chars?|characters?))\b"
    r"|\bcount\s+(the\s+)?(words?|characters?)\b",
    re.IGNORECASE,
)

_UUID_TRIGGERS = re.compile(
    r"\b(generate|create|make|new)\b.{0,15}\b(uuid|guid)\b"
    r"|\buuid\s+(generator|gen|v4)\b",
    re.IGNORECASE,
)

_COLOR_TRIGGERS = re.compile(
    r"\bconvert\b.{0,30}\b(hex|rgb|hsl|color)\b"
    r"|\b#[0-9A-Fa-f]{3,8}\b.{0,20}\b(to|in)\b"
    r"|\brgb\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\).{0,20}\b(to|in)\b",
    re.IGNORECASE,
)
_HEX_COLOR = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
_RGB_COLOR = re.compile(r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")


# ── Tool runners ─────────────────────────────────────────────────────────

async def _run_python(code: str, timeout: int = 15) -> dict[str, Any]:
    try:
        from tools.python_exec import execute
        result = await asyncio.wait_for(execute(code, timeout=timeout), timeout=timeout + 2)
        return {"tool": "code_exec", "label": "Code executed", "success": result.get("success", False),
                "stdout": (result.get("stdout") or "").strip()[:2000],
                "stderr": (result.get("stderr") or "").strip()[:500],
                "returncode": result.get("returncode", -1)}
    except asyncio.TimeoutError:
        return {"tool": "code_exec", "label": "Code executed", "success": False,
                "stdout": "", "stderr": "Execution timed out.", "returncode": -1}
    except Exception as exc:
        return {"tool": "code_exec", "label": "Code executed", "success": False,
                "stdout": "", "stderr": str(exc), "returncode": -1}


async def _run_math(expr_str: str) -> dict[str, Any]:
    try:
        from tools.math_tool import numerical_eval, simplify_expr
        result = await numerical_eval(expr_str)
        if not result.get("verified"):
            result = await simplify_expr(expr_str)
        return {"tool": "math", "label": "Math computed", "success": result.get("verified", False),
                "result": result.get("result", ""), "latex": result.get("latex", ""), "expr": expr_str}
    except Exception as exc:
        logger.warning("math_tool failed: %s", exc)
        return {"tool": "math", "label": "Math computed", "success": False,
                "result": "", "latex": "", "expr": expr_str}


async def _run_sysinfo() -> dict[str, Any]:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {"tool": "sysinfo", "label": "System info", "success": True,
                "cpu_percent": cpu, "ram_total_gb": round(mem.total / 1e9, 1),
                "ram_used_gb": round(mem.used / 1e9, 1), "ram_percent": mem.percent,
                "disk_total_gb": round(disk.total / 1e9, 1),
                "disk_used_gb": round(disk.used / 1e9, 1), "disk_percent": disk.percent}
    except Exception as exc:
        return {"tool": "sysinfo", "label": "System info", "success": False}


async def _run_datetime() -> dict[str, Any]:
    now = datetime.datetime.now()
    utc = datetime.datetime.utcnow()
    return {"tool": "datetime", "label": "Date/time", "success": True,
            "local": now.strftime("%A, %B %d %Y %H:%M:%S"),
            "iso": now.isoformat(), "utc_iso": utc.isoformat() + "Z",
            "day_of_week": now.strftime("%A"),
            "timezone": str(datetime.datetime.now(datetime.timezone.utc).astimezone().tzname())}


async def _run_calculator(expr: str) -> dict[str, Any]:
    import ast, operator as op
    _OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
            ast.Pow: op.pow, ast.Mod: op.mod, ast.USub: op.neg, ast.UAdd: op.pos}
    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported: {type(node)}")
    try:
        result = _eval(ast.parse(expr.replace("^", "**").strip(), mode="eval").body)
        return {"tool": "calculator", "label": "Calculator", "success": True,
                "expr": expr, "result": result}
    except Exception as exc:
        return {"tool": "calculator", "label": "Calculator", "success": False,
                "expr": expr, "result": None, "error": str(exc)}


async def _run_git(message: str) -> dict[str, Any]:
    try:
        from tools.git_tool import status, log, diff
        import os
        cwd = os.environ.get("JIMAI_WORKSPACE_ROOT") or str(
            __import__("pathlib").Path(__file__).resolve().parent.parent.parent
        )
        wants_diff = bool(re.search(r"\bdiff\b|\bchanged\b|\bwhat.{0,10}changed\b", message, re.I))
        wants_log = bool(re.search(r"\blog\b|\bcommit\s+histor|\brecent\s+commit", message, re.I))

        tasks = {"status": asyncio.create_task(asyncio.to_thread(lambda: __import__("asyncio").run(status(cwd))))}
        if wants_log:
            tasks["log"] = asyncio.create_task(asyncio.to_thread(lambda: __import__("asyncio").run(log(10, cwd))))
        if wants_diff:
            tasks["diff"] = asyncio.create_task(asyncio.to_thread(lambda: __import__("asyncio").run(diff(cwd=cwd))))

        git_status = await status(cwd)
        git_log = await log(8, cwd) if wants_log else []
        git_diff = (await diff(cwd=cwd))[:3000] if wants_diff else ""

        return {"tool": "git", "label": "Git", "success": True,
                "status": git_status[:2000], "log": git_log, "diff": git_diff}
    except Exception as exc:
        logger.warning("git_tool failed: %s", exc)
        return {"tool": "git", "label": "Git", "success": False, "error": str(exc)}


async def _run_file_read(message: str) -> dict[str, Any]:
    try:
        from tools.file_tool import read
        m = _FILE_READ_TRIGGERS.search(message)
        if not m:
            return {"tool": "file_read", "success": False, "error": "No path detected"}
        path = next((g for g in m.groups() if g and "." in g), None)
        if not path:
            return {"tool": "file_read", "success": False, "error": "No path detected"}
        content = await read(path)
        return {"tool": "file_read", "label": "File read", "success": "Access denied" not in content,
                "path": path, "content": content[:4000]}
    except Exception as exc:
        return {"tool": "file_read", "label": "File read", "success": False, "error": str(exc)}


async def _run_unit_convert(message: str) -> dict[str, Any]:
    m = _UNIT_EXPR.search(message)
    if not m:
        return {"tool": "unit_convert", "success": False}
    value, from_unit, to_unit = float(m.group(1)), m.group(2).lower(), m.group(3).lower()

    # Conversion table: (from_unit, to_unit): lambda value -> result
    _norm = {"kilometre": "km", "kilometer": "km", "kilometres": "km", "kilometers": "km",
             "mile": "miles", "pound": "lbs", "pounds": "lbs", "lb": "lbs",
             "metre": "meters", "meter": "meters", "foot": "feet", "inch": "inches",
             "gallon": "gallons", "litre": "liters", "liter": "liters",
             "ounce": "oz", "ounces": "oz", "°c": "celsius", "°f": "fahrenheit"}
    fu = _norm.get(from_unit, from_unit)
    tu = _norm.get(to_unit, to_unit)

    _TABLE: dict[tuple[str, str], Any] = {
        ("km", "miles"): lambda v: v * 0.621371,
        ("miles", "km"): lambda v: v * 1.60934,
        ("kg", "lbs"): lambda v: v * 2.20462,
        ("lbs", "kg"): lambda v: v / 2.20462,
        ("celsius", "fahrenheit"): lambda v: v * 9 / 5 + 32,
        ("fahrenheit", "celsius"): lambda v: (v - 32) * 5 / 9,
        ("meters", "feet"): lambda v: v * 3.28084,
        ("feet", "meters"): lambda v: v * 0.3048,
        ("cm", "inches"): lambda v: v / 2.54,
        ("inches", "cm"): lambda v: v * 2.54,
        ("mm", "inches"): lambda v: v / 25.4,
        ("inches", "mm"): lambda v: v * 25.4,
        ("km", "meters"): lambda v: v * 1000,
        ("meters", "km"): lambda v: v / 1000,
        ("gallons", "liters"): lambda v: v * 3.78541,
        ("liters", "gallons"): lambda v: v / 3.78541,
        ("oz", "kg"): lambda v: v * 0.0283495,
        ("kg", "oz"): lambda v: v / 0.0283495,
        ("mph", "kph"): lambda v: v * 1.60934,
        ("kph", "mph"): lambda v: v * 0.621371,
    }
    fn = _TABLE.get((fu, tu))
    if fn:
        result = round(fn(value), 6)
        return {"tool": "unit_convert", "label": "Unit conversion", "success": True,
                "from_value": value, "from_unit": fu, "to_unit": tu, "result": result}
    return {"tool": "unit_convert", "label": "Unit conversion", "success": False,
            "error": f"No conversion for {fu} → {tu}"}


async def _run_hash(message: str) -> dict[str, Any]:
    m = _HASH_TEXT.search(message)
    text = m.group(1).strip().strip("\"'") if m else ""
    if not text:
        return {"tool": "hash", "success": False}
    enc = text.encode()
    alg = "sha256"
    if re.search(r"\bmd5\b", message, re.I):
        alg = "md5"
    elif re.search(r"\bsha1\b|\bsha-1\b", message, re.I):
        alg = "sha1"
    elif re.search(r"\bsha512\b|\bsha-512\b", message, re.I):
        alg = "sha512"
    result = hashlib.new(alg, enc).hexdigest()
    return {"tool": "hash", "label": "Hash", "success": True,
            "algorithm": alg, "input": text[:80], "result": result}


async def _run_base64(message: str) -> dict[str, Any]:
    is_decode = bool(re.search(r"\bdecode\b", message, re.I))
    m = _BASE64_TEXT.search(message)
    text = m.group(1).strip().strip("\"'`") if m else ""
    if not text:
        return {"tool": "base64", "success": False}
    try:
        if is_decode:
            result = _b64.b64decode(text.encode()).decode("utf-8", errors="replace")
            return {"tool": "base64", "label": "Base64", "success": True,
                    "operation": "decode", "input": text[:80], "result": result[:500]}
        else:
            result = _b64.b64encode(text.encode()).decode()
            return {"tool": "base64", "label": "Base64", "success": True,
                    "operation": "encode", "input": text[:80], "result": result}
    except Exception as exc:
        return {"tool": "base64", "label": "Base64", "success": False, "error": str(exc)}


async def _run_json_format(message: str) -> dict[str, Any]:
    # Try code block first, then inline
    m = _JSON_BLOCK.search(message) or _JSON_INLINE.search(message)
    raw = m.group(1).strip() if m else ""
    if not raw:
        return {"tool": "json_format", "success": False}
    try:
        parsed = json.loads(raw)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
        return {"tool": "json_format", "label": "JSON", "success": True,
                "valid": True, "formatted": pretty[:3000]}
    except json.JSONDecodeError as exc:
        return {"tool": "json_format", "label": "JSON", "success": True,
                "valid": False, "error": str(exc), "formatted": ""}


async def _run_regex_test(message: str) -> dict[str, Any]:
    # Extract pattern and test string from message
    patterns = _REGEX_PATTERN.findall(message)
    if len(patterns) < 2:
        return {"tool": "regex_test", "success": False}
    pattern, test_str = patterns[0], patterns[1]
    try:
        compiled = re.compile(pattern)
        match = compiled.search(test_str)
        all_matches = compiled.findall(test_str)
        return {"tool": "regex_test", "label": "Regex", "success": True,
                "pattern": pattern, "test_string": test_str,
                "matched": bool(match), "all_matches": all_matches[:20],
                "match_at": (match.start(), match.end()) if match else None}
    except re.error as exc:
        return {"tool": "regex_test", "label": "Regex", "success": False,
                "pattern": pattern, "error": str(exc)}


async def _run_text_stats(message: str) -> dict[str, Any]:
    # Find quoted or code-block text to analyze; fall back to rest of message
    m = re.search(r'["\'](.{20,}?)["\']|```[^\n]*\n(.*?)```', message, re.DOTALL)
    text = (m.group(1) or m.group(2) or "").strip() if m else ""
    if len(text) < 10:
        # Strip the trigger phrase and use remaining message
        text = re.sub(r"\b(word\s+count|count\s+(words?|chars?)|reading\s+time)\b", "", message, flags=re.I).strip()
    words = len(text.split())
    chars = len(text)
    sentences = len(re.findall(r"[.!?]+", text)) or 1
    reading_secs = max(1, round(words / 200 * 60))  # avg 200 wpm
    return {"tool": "text_stats", "label": "Text stats", "success": True,
            "words": words, "characters": chars, "sentences": sentences,
            "paragraphs": len([p for p in text.split("\n\n") if p.strip()]),
            "reading_time_seconds": reading_secs,
            "avg_word_length": round(sum(len(w) for w in text.split()) / max(1, words), 1)}


async def _run_uuid() -> dict[str, Any]:
    u = str(uuid.uuid4())
    return {"tool": "uuid", "label": "UUID", "success": True, "uuid": u}


async def _run_color(message: str) -> dict[str, Any]:
    # Hex → RGB
    hex_m = _HEX_COLOR.search(message)
    if hex_m:
        h = hex_m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        hsl = _rgb_to_hsl(r, g, b)
        return {"tool": "color", "label": "Color", "success": True,
                "input": f"#{h}", "rgb": f"rgb({r},{g},{b})",
                "hsl": f"hsl({hsl[0]},{hsl[1]}%,{hsl[2]}%)",
                "r": r, "g": g, "b": b}
    # RGB → Hex
    rgb_m = _RGB_COLOR.search(message)
    if rgb_m:
        r, g, b = int(rgb_m.group(1)), int(rgb_m.group(2)), int(rgb_m.group(3))
        h = f"#{r:02x}{g:02x}{b:02x}"
        hsl = _rgb_to_hsl(r, g, b)
        return {"tool": "color", "label": "Color", "success": True,
                "input": f"rgb({r},{g},{b})", "hex": h,
                "hsl": f"hsl({hsl[0]},{hsl[1]}%,{hsl[2]}%)",
                "r": r, "g": g, "b": b}
    return {"tool": "color", "success": False}


def _rgb_to_hsl(r: int, g: int, b: int) -> tuple[int, int, int]:
    rf, gf, bf = r / 255, g / 255, b / 255
    cmax, cmin = max(rf, gf, bf), min(rf, gf, bf)
    delta = cmax - cmin
    l = (cmax + cmin) / 2
    s = 0 if delta == 0 else delta / (1 - abs(2 * l - 1))
    if delta == 0:
        h = 0
    elif cmax == rf:
        h = 60 * (((gf - bf) / delta) % 6)
    elif cmax == gf:
        h = 60 * ((bf - rf) / delta + 2)
    else:
        h = 60 * ((rf - gf) / delta + 4)
    return round(h), round(s * 100), round(l * 100)


# ── Dispatcher ────────────────────────────────────────────────────────────

def detect_needed_tools(message: str) -> list[str]:
    """Return ordered list of tool names needed for this message."""
    tools: list[str] = []
    has_code_block = bool(_CODE_BLOCK.search(message))

    if _DATETIME_TRIGGERS.search(message):
        tools.append("datetime")
    if _SYSINFO_TRIGGERS.search(message):
        tools.append("sysinfo")
    if _GIT_TRIGGERS.search(message):
        tools.append("git")
    if _FILE_READ_TRIGGERS.search(message) and re.search(r"\.(py|ts|js|tsx|jsx|json|yaml|yml|txt|md|toml|env|csv|html|css|sh|bat|rs|go|java|cpp|c|h|sql|r|rb|php|swift|kt|dart)(\b|$)", message, re.I):
        tools.append("file_read")
    if has_code_block and _CODE_RUN_TRIGGERS.search(message):
        tools.append("code_exec")
    if _UNIT_TRIGGERS.search(message):
        tools.append("unit_convert")
    if _HASH_TRIGGERS.search(message):
        tools.append("hash")
    if _BASE64_TRIGGERS.search(message):
        tools.append("base64")
    if _JSON_TRIGGERS.search(message):
        tools.append("json_format")
    if _REGEX_TRIGGERS.search(message):
        tools.append("regex_test")
    if _TEXT_STATS_TRIGGERS.search(message):
        tools.append("text_stats")
    if _UUID_TRIGGERS.search(message):
        tools.append("uuid")
    if _COLOR_TRIGGERS.search(message):
        tools.append("color")
    if _MATH_EXPR_TRIGGERS.search(message):
        tools.append("math")
    elif not tools:
        m = _CALC_EXPR.search(message)
        if m:
            tools.append("calculator")

    return tools


async def run_tools(message: str) -> list[dict[str, Any]]:
    """Run all detected tools concurrently. Returns results list."""
    needed = detect_needed_tools(message)
    if not needed:
        return []

    tasks: list[asyncio.Task] = []
    for name in needed:
        if name == "datetime":
            tasks.append(asyncio.create_task(_run_datetime()))
        elif name == "sysinfo":
            tasks.append(asyncio.create_task(_run_sysinfo()))
        elif name == "git":
            tasks.append(asyncio.create_task(_run_git(message)))
        elif name == "file_read":
            tasks.append(asyncio.create_task(_run_file_read(message)))
        elif name == "code_exec":
            m = _CODE_BLOCK.search(message)
            code = m.group(1).strip() if m else ""
            if code:
                tasks.append(asyncio.create_task(_run_python(code)))
        elif name == "unit_convert":
            tasks.append(asyncio.create_task(_run_unit_convert(message)))
        elif name == "hash":
            tasks.append(asyncio.create_task(_run_hash(message)))
        elif name == "base64":
            tasks.append(asyncio.create_task(_run_base64(message)))
        elif name == "json_format":
            tasks.append(asyncio.create_task(_run_json_format(message)))
        elif name == "regex_test":
            tasks.append(asyncio.create_task(_run_regex_test(message)))
        elif name == "text_stats":
            tasks.append(asyncio.create_task(_run_text_stats(message)))
        elif name == "uuid":
            tasks.append(asyncio.create_task(_run_uuid()))
        elif name == "color":
            tasks.append(asyncio.create_task(_run_color(message)))
        elif name == "math":
            m = _MATH_INLINE.search(message)
            expr = m.group(1).strip() if m else ""
            if expr:
                tasks.append(asyncio.create_task(_run_math(expr)))
        elif name == "calculator":
            m = _CALC_EXPR.search(message)
            expr = m.group(1).strip() if m else ""
            if expr:
                tasks.append(asyncio.create_task(_run_calculator(expr)))

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]


def build_tool_context(tool_results: list[dict[str, Any]]) -> str:
    """Convert tool results into a context block prepended to the prompt."""
    if not tool_results:
        return ""
    parts = ["[Tool results — treat as ground truth]"]
    for r in tool_results:
        t = r.get("tool", "")
        if t == "datetime" and r.get("success"):
            parts.append(f"Current date/time: {r['local']} | UTC: {r['utc_iso']}")
        elif t == "sysinfo" and r.get("success"):
            parts.append(
                f"Live system: CPU {r['cpu_percent']}% | "
                f"RAM {r['ram_used_gb']}/{r['ram_total_gb']} GB ({r['ram_percent']}%) | "
                f"Disk {r['disk_used_gb']}/{r['disk_total_gb']} GB ({r['disk_percent']}%)"
            )
        elif t == "git" and r.get("success"):
            lines = [f"Git status:\n{r['status']}"]
            if r.get("log"):
                log_lines = "\n".join(f"  {e['hash'][:8]} {e['date'][:10]} {e['message']}" for e in r["log"][:8])
                lines.append(f"Recent commits:\n{log_lines}")
            if r.get("diff"):
                lines.append(f"Diff (truncated):\n{r['diff'][:1500]}")
            parts.append("\n".join(lines))
        elif t == "file_read":
            if r.get("success"):
                parts.append(f"File `{r['path']}`:\n```\n{r['content']}\n```")
            else:
                parts.append(f"Could not read file: {r.get('error', 'unknown error')}")
        elif t == "code_exec":
            if r.get("success"):
                parts.append(f"Code output:\n```\n{r['stdout']}\n```")
            else:
                parts.append(f"Code error:\n```\n{r['stderr']}\n```")
        elif t == "unit_convert" and r.get("success"):
            parts.append(f"Unit conversion: {r['from_value']} {r['from_unit']} = {r['result']} {r['to_unit']}")
        elif t == "hash" and r.get("success"):
            parts.append(f"{r['algorithm'].upper()} of \"{r['input']}\": `{r['result']}`")
        elif t == "base64" and r.get("success"):
            parts.append(f"Base64 {r['operation']}: `{r['result']}`")
        elif t == "json_format" and r.get("success"):
            if r["valid"]:
                parts.append(f"Formatted JSON:\n```json\n{r['formatted']}\n```")
            else:
                parts.append(f"Invalid JSON: {r['error']}")
        elif t == "regex_test" and r.get("success"):
            matched = "✓ matched" if r["matched"] else "✗ no match"
            parts.append(
                f"Regex `{r['pattern']}` against `{r['test_string']}`: {matched}"
                + (f" | all matches: {r['all_matches']}" if r.get("all_matches") else "")
            )
        elif t == "text_stats" and r.get("success"):
            mins = r["reading_time_seconds"] // 60
            secs = r["reading_time_seconds"] % 60
            rt = f"{mins}m {secs}s" if mins else f"{secs}s"
            parts.append(
                f"Text stats: {r['words']} words | {r['characters']} chars | "
                f"{r['sentences']} sentences | reading time ≈ {rt}"
            )
        elif t == "uuid" and r.get("success"):
            parts.append(f"Generated UUID: `{r['uuid']}`")
        elif t == "color" and r.get("success"):
            fields = {k: v for k, v in r.items() if k not in ("tool", "label", "success", "input", "r", "g", "b")}
            parts.append(f"Color {r['input']} → " + " | ".join(f"{k}: {v}" for k, v in fields.items()))
        elif t == "math" and r.get("success") and r.get("result"):
            parts.append(f"Math `{r['expr']}` = {r['result']}" + (f" (LaTeX: `{r['latex']}`)" if r.get("latex") else ""))
        elif t == "calculator" and r.get("success") and r.get("result") is not None:
            parts.append(f"Calculator: {r['expr']} = {r['result']}")
    return "\n".join(parts)
