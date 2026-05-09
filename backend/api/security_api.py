"""Security agents API.

REST surface for the six defensive agents. Read-mostly. Mutations are
limited to:
    * triggering a supply-chain scan
    * updating the supply-chain baseline
    * configuring the prompt-shield guardrail model
    * adding/removing egress allowlist domains
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from agent_space.security import runtime as security_runtime
from agent_space.security.tool_gate import ToolGateError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security", tags=["security"])


# ---------------------------------------------------------------- aggregate


@router.get("/overview")
async def overview() -> dict[str, Any]:
    return security_runtime.all_stats()


# ---------------------------------------------------------------- prompt shield


@router.get("/shield/stats")
async def shield_stats() -> dict[str, Any]:
    return security_runtime.get_prompt_shield().stats()


@router.post("/shield/check")
async def shield_check(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    source = str(payload.get("source") or "user_input")
    use_guardrail = payload.get("use_guardrail")
    if use_guardrail is not None and not isinstance(use_guardrail, bool):
        use_guardrail = bool(use_guardrail)
    verdict = await security_runtime.get_prompt_shield().evaluate(
        text, source=source, use_guardrail=use_guardrail
    )
    return verdict.to_dict()


@router.post("/shield/guardrail-model")
async def shield_set_guardrail(payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model")
    shield = security_runtime.get_prompt_shield()
    shield.use_guardrail_model(str(model) if model else None)
    return {"guardrail_model": shield.guardrail_model or ""}


# ---------------------------------------------------------------- secret scan


@router.get("/secrets/stats")
async def secrets_stats() -> dict[str, Any]:
    return security_runtime.get_secret_scanner().stats()


@router.post("/secrets/scan")
async def secrets_scan(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text")
    rows = payload.get("payload")
    scanner = security_runtime.get_secret_scanner()
    findings: list[Any] = []
    if isinstance(text, str):
        findings.extend(scanner.scan(text))
    if isinstance(rows, dict):
        findings.extend(scanner.scan_dict(rows))
    return {"count": len(findings), "findings": [f.to_dict() for f in findings]}


# ---------------------------------------------------------------- tool gate


@router.get("/tool-gate/stats")
async def gate_stats() -> dict[str, Any]:
    return security_runtime.get_tool_gate().stats()


@router.get("/tool-gate/policies")
async def gate_policies() -> dict[str, Any]:
    return {"policies": security_runtime.get_tool_gate().list_policies()}


@router.get("/tool-gate/audit")
async def gate_audit(limit: int = 200) -> dict[str, Any]:
    return {"items": security_runtime.get_tool_gate().recent_audit(limit=limit)}


@router.post("/tool-gate/check")
async def gate_check(payload: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(payload.get("agent_id") or "").strip() or "unknown"
    tool = str(payload.get("tool") or "").strip()
    args = dict(payload.get("args") or {})
    if not tool:
        raise HTTPException(status_code=400, detail="tool is required")
    try:
        record = await security_runtime.get_tool_gate().check(
            agent_id=agent_id, tool=tool, args=args
        )
        return {"decision": "allow", **record}
    except ToolGateError as exc:
        return {"decision": "deny", "reason": str(exc), "tool": tool, "agent_id": agent_id}


# ---------------------------------------------------------------- egress


@router.get("/egress/stats")
async def egress_stats() -> dict[str, Any]:
    return security_runtime.get_egress_guardian().stats()


@router.post("/egress/check")
async def egress_check(payload: dict[str, Any]) -> dict[str, Any]:
    url = str(payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    return security_runtime.get_egress_guardian().check_url(url).to_dict()


@router.post("/egress/redact")
async def egress_redact(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    redacted, counts = security_runtime.get_egress_guardian().redact(text)
    return {"redacted": redacted, "counts": counts}


@router.post("/egress/allow")
async def egress_allow(payload: dict[str, Any]) -> dict[str, Any]:
    domain = str(payload.get("domain") or "").strip()
    if not domain:
        raise HTTPException(status_code=400, detail="domain is required")
    security_runtime.get_egress_guardian().add_domain(domain)
    return {"ok": True, "domain": domain}


@router.get("/egress/audit")
async def egress_audit(limit: int = 200) -> dict[str, Any]:
    return {"items": security_runtime.get_egress_guardian().recent_audit(limit=limit)}


# ---------------------------------------------------------------- behavior


@router.get("/behavior/stats")
async def behavior_stats() -> dict[str, Any]:
    return security_runtime.get_behavior_monitor().stats()


@router.get("/behavior/run/{run_id}")
async def behavior_run(run_id: str) -> dict[str, Any]:
    report = security_runtime.get_behavior_monitor().report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="run not found in behavior monitor")
    return report


# ---------------------------------------------------------------- supply chain


@router.get("/supply-chain/stats")
async def supply_chain_stats() -> dict[str, Any]:
    return security_runtime.get_supply_chain_sentinel().stats()


@router.get("/supply-chain/latest")
async def supply_chain_latest() -> dict[str, Any]:
    return security_runtime.get_supply_chain_sentinel().latest()


@router.get("/supply-chain/diff")
async def supply_chain_diff() -> dict[str, Any]:
    return security_runtime.get_supply_chain_sentinel().diff_vs_baseline()


@router.post("/supply-chain/scan")
async def supply_chain_scan() -> dict[str, Any]:
    return await security_runtime.get_supply_chain_sentinel().scan_now()


@router.post("/supply-chain/baseline")
async def supply_chain_set_baseline() -> dict[str, Any]:
    return security_runtime.get_supply_chain_sentinel().update_baseline()
