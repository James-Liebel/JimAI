"""SecretScanner — regex-based detector for credentials in any string.

Designed for two layers:

    * Pre-tool-call: scan outgoing tool arguments and outbound HTTP bodies.
      If the agent is about to send an AWS key to a public web endpoint, we
      block before the request leaves the process.

    * Post-generation: scan model output before it lands in committed code,
      review_store entries, or chat history.

Patterns are conservative — based on standard prefixes and entropy-friendly
shapes used by Gitleaks, TruffleHog, and ggshield. We don't try to catch
*everything*; we try to catch the common, high-confidence shapes with low
false-positive rate.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


@dataclass
class SecretFinding:
    rule: str
    description: str
    match: str  # always redacted
    severity: str = "high"
    line: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# (rule_id, description, regex)
PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("aws_access_key", "AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws_secret", "AWS secret access key (40-char base64)",
     re.compile(r"(?<![A-Za-z0-9+/=])(?:aws[_\-]?secret[_\-]?access[_\-]?key|aws[_\-]?secret)[^a-zA-Z0-9]{0,5}([A-Za-z0-9+/]{40})", re.I)),
    ("github_token", "GitHub token (ghp/gho/ghu/ghs)", re.compile(r"\bghp_[A-Za-z0-9]{36,}\b|\bgho_[A-Za-z0-9]{36,}\b|\bghu_[A-Za-z0-9]{36,}\b|\bghs_[A-Za-z0-9]{36,}\b|\bghr_[A-Za-z0-9]{36,}\b")),
    ("github_oauth", "GitHub OAuth (gist/personal)", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
    ("openai_key", "OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9]{20,}T3BlbkFJ[A-Za-z0-9]{20,}\b|\bsk-proj-[A-Za-z0-9_-]{40,}\b")),
    ("google_api_key", "Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("slack_token", "Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("slack_webhook", "Slack incoming webhook", re.compile(r"https://hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]{20,}")),
    ("stripe_key", "Stripe live key", re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b|\brk_live_[A-Za-z0-9]{24,}\b")),
    ("twilio_sid", "Twilio account SID", re.compile(r"\bAC[a-z0-9]{32}\b", re.I)),
    ("twilio_auth", "Twilio auth token (paired with SID nearby)", re.compile(r"(?<![A-Za-z0-9])(?:twilio[_\-]?auth(?:[_\-]?token)?)[^A-Za-z0-9]{0,5}([A-Fa-f0-9]{32})", re.I)),
    ("private_key_block", "Private key PEM block", re.compile(r"-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP|ENCRYPTED) PRIVATE KEY-----")),
    ("jwt_token", "JWT token (header.payload.signature)", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("generic_api_key", "Generic api/key/token assignment",
     re.compile(r"(?<![A-Za-z0-9_])(?:api[_\-]?key|access[_\-]?key|secret[_\-]?key|private[_\-]?key|auth[_\-]?token|bearer[_\-]?token)[^A-Za-z0-9]{0,5}[\"']([A-Za-z0-9_\-+=/]{20,})[\"']", re.I)),
    ("generic_password", "Plaintext password assignment",
     re.compile(r"(?<![A-Za-z0-9_])(?:password|passwd|pwd)[^A-Za-z0-9]{0,5}[\"']([^\"'\s]{8,})[\"']", re.I)),
    ("connection_string", "DB / service connection string",
     re.compile(r"\b(?:postgres|postgresql|mysql|mongodb|redis|amqp)://[^\s\"']{6,}:[^\s\"'@]+@[^\s\"']{4,}", re.I)),
]


def _redact(value: str, *, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"


class SecretScanner:
    """Synchronous regex scanner. Cheap to call on every tool arg."""

    def __init__(self, *, allow_rules: Iterable[str] | None = None) -> None:
        self._allow = {r.strip() for r in (allow_rules or []) if r and isinstance(r, str)}
        self._stats = {"scanned": 0, "findings": 0}

    def scan(self, text: str) -> list[SecretFinding]:
        self._stats["scanned"] += 1
        body = str(text or "")
        if not body:
            return []
        findings: list[SecretFinding] = []
        for rule_id, description, pattern in PATTERNS:
            if rule_id in self._allow:
                continue
            for m in pattern.finditer(body):
                # Capture group 1 if present (assignment patterns), else full match.
                value = m.group(1) if m.lastindex else m.group(0)
                line_no = body.count("\n", 0, m.start()) + 1
                findings.append(
                    SecretFinding(
                        rule=rule_id,
                        description=description,
                        match=_redact(value),
                        severity="high",
                        line=line_no,
                    )
                )
        if findings:
            self._stats["findings"] += len(findings)
        return findings

    def scan_dict(self, payload: dict[str, Any]) -> list[SecretFinding]:
        """Walk a dict (e.g. tool args) and scan all string values."""
        out: list[SecretFinding] = []
        if not isinstance(payload, dict):
            return out
        for key, value in payload.items():
            if isinstance(value, str):
                hits = self.scan(value)
                for h in hits:
                    h.metadata.setdefault("path", str(key))
                    out.append(h)
            elif isinstance(value, dict):
                inner = self.scan_dict(value)
                for h in inner:
                    h.metadata.setdefault("path", str(key) + "." + str(h.metadata.get("path", "")))
                    out.append(h)
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    if isinstance(item, str):
                        hits = self.scan(item)
                        for h in hits:
                            h.metadata.setdefault("path", f"{key}[{idx}]")
                            out.append(h)
                    elif isinstance(item, dict):
                        inner = self.scan_dict(item)
                        for h in inner:
                            h.metadata.setdefault("path", f"{key}[{idx}]." + str(h.metadata.get("path", "")))
                            out.append(h)
        return out

    @staticmethod
    def redact_text(text: str, findings: list[SecretFinding]) -> str:
        """Replace each finding's match (in the original text) with redacted form."""
        if not findings or not text:
            return text
        # Re-run patterns and replace.
        out = text
        for rule_id, _description, pattern in PATTERNS:
            out = pattern.sub(
                lambda m: m.group(0)[: 4] + "*" * max(4, len(m.group(0)) - 8) + m.group(0)[-4:],
                out,
            )
        return out

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)
