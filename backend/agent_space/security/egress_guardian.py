"""EgressGuardian — domain allowlist + PII scrub for outbound payloads.

The job is small but high value: any tool that makes outbound network calls
(web_fetch, browser_open, etc.) goes through ``check_url`` first, and any
text being sent in a body goes through ``redact``.

Two deliberate simplifications:

    * Domain allowlist is configurable but defaults to "loopback +
      RFC1918 + a small set of well-known package mirrors and search
      engines used by the existing research_agent". Production users
      can tighten or relax via runtime config.

    * PII redaction is a regex-only pass (email, phone, credit card,
      SSN, IBAN). No NER. The 2026 best practice is Microsoft Presidio,
      but that's a heavier dependency we don't pull in by default.
      Users can replace ``redact`` with a Presidio-backed implementation
      when needed.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class EgressVerdict:
    allowed: bool
    url: str
    host: str
    reason: str = ""
    matched_rule: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Conservative defaults — extend in runtime config as needed.
DEFAULT_ALLOWLIST_HOSTS: set[str] = {
    "localhost",
    "127.0.0.1",
    "::1",
}
DEFAULT_ALLOWLIST_DOMAINS: set[str] = {
    # Search providers
    "duckduckgo.com",
    "html.duckduckgo.com",
    "lite.duckduckgo.com",
    "wikipedia.org",
    "en.wikipedia.org",
    # Package mirrors
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "huggingface.co",
    "ollama.com",
    "ollama.ai",
    # Common research / docs sites the platform already fetches
    "arxiv.org",
    "stackoverflow.com",
    "docs.python.org",
    "developer.mozilla.org",
    "openai.com",
}

PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("phone_us", re.compile(r"\b(?:\+?1[\s\-.])?\(?\d{3}\)?[\s\-.]\d{3}[\s\-.]\d{4}\b")),
    ("ssn_us", re.compile(r"\b(?!000|666)(?:[0-6]\d{2}|7(?:[0-6]\d|7[012]))-(?!00)\d{2}-(?!0000)\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13}|6(?:011|5\d{2})\d{12})\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("ipv4_private", re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
]


def _is_private_ip(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


def _strip_port(host: str) -> str:
    if not host:
        return ""
    if host.startswith("["):
        # IPv6 in URL form [::1]:80
        end = host.find("]")
        return host[1:end] if end > 0 else host
    if ":" in host and host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def _suffix_match(host: str, allow_domains: set[str]) -> str:
    """Return the matching suffix if host ends with allowed domain, else ''."""
    h = host.lower().rstrip(".")
    for domain in sorted(allow_domains, key=len, reverse=True):
        d = domain.lower().rstrip(".")
        if not d:
            continue
        if h == d or h.endswith("." + d):
            return d
    return ""


class EgressGuardian:
    """Allowlist outbound traffic and redact PII in outbound payloads."""

    def __init__(
        self,
        *,
        allow_hosts: set[str] | None = None,
        allow_domains: set[str] | None = None,
        block_private_ips: bool = False,
    ) -> None:
        self.allow_hosts: set[str] = set(allow_hosts) if allow_hosts is not None else set(DEFAULT_ALLOWLIST_HOSTS)
        self.allow_domains: set[str] = set(allow_domains) if allow_domains is not None else set(DEFAULT_ALLOWLIST_DOMAINS)
        self.block_private_ips = bool(block_private_ips)
        self._stats = {
            "checked": 0,
            "allowed": 0,
            "blocked": 0,
            "pii_redactions": 0,
        }
        self._audit: list[EgressVerdict] = []

    def add_domain(self, domain: str) -> None:
        domain = (domain or "").strip().lower().lstrip(".")
        if domain:
            self.allow_domains.add(domain)

    def remove_domain(self, domain: str) -> bool:
        return self.allow_domains.discard((domain or "").strip().lower().lstrip(".")) is None and False or True

    def check_url(self, url: str) -> EgressVerdict:
        self._stats["checked"] += 1
        raw = (url or "").strip()
        if not raw:
            v = EgressVerdict(allowed=False, url=raw, host="", reason="empty url")
            self._record(v)
            return v
        try:
            parsed = urlparse(raw if "://" in raw else "https://" + raw)
        except Exception as exc:
            v = EgressVerdict(allowed=False, url=raw, host="", reason=f"parse error: {exc}")
            self._record(v)
            return v
        host = _strip_port(parsed.hostname or "")
        if not host:
            v = EgressVerdict(allowed=False, url=raw, host="", reason="no host")
            self._record(v)
            return v

        if host in self.allow_hosts:
            v = EgressVerdict(allowed=True, url=raw, host=host, matched_rule=f"host:{host}")
            self._record(v)
            return v

        if _is_private_ip(host):
            if self.block_private_ips:
                v = EgressVerdict(allowed=False, url=raw, host=host, reason="private IP blocked by policy")
                self._record(v)
                return v
            v = EgressVerdict(allowed=True, url=raw, host=host, matched_rule="private_ip")
            self._record(v)
            return v

        suffix = _suffix_match(host, self.allow_domains)
        if suffix:
            v = EgressVerdict(allowed=True, url=raw, host=host, matched_rule=f"domain:{suffix}")
            self._record(v)
            return v

        v = EgressVerdict(
            allowed=False,
            url=raw,
            host=host,
            reason=f"host '{host}' not in allowlist",
        )
        self._record(v)
        return v

    def _record(self, verdict: EgressVerdict) -> None:
        if verdict.allowed:
            self._stats["allowed"] += 1
        else:
            self._stats["blocked"] += 1
            logger.info("EgressGuardian BLOCK %s reason=%s", verdict.host, verdict.reason)
        self._audit.append(verdict)
        if len(self._audit) > 5000:
            self._audit = self._audit[-2500:]

    def redact(self, text: str) -> tuple[str, dict[str, int]]:
        """Apply PII redaction. Returns (redacted_text, count_by_rule)."""
        if not text:
            return text, {}
        out = text
        counts: dict[str, int] = {}
        for rule, pattern in PII_PATTERNS:
            n = 0
            def _sub(m: re.Match[str]) -> str:
                nonlocal n
                n += 1
                value = m.group(0)
                if len(value) <= 6:
                    return "[REDACTED]"
                return f"[REDACTED:{rule}]"
            out = pattern.sub(_sub, out)
            if n:
                counts[rule] = n
                self._stats["pii_redactions"] += n
        return out, counts

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "allow_hosts": sorted(self.allow_hosts),
            "allow_domains_count": len(self.allow_domains),
            "block_private_ips": self.block_private_ips,
        }

    def recent_audit(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return [v.to_dict() for v in self._audit[-max(1, int(limit)):]]
