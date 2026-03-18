"""CLI launcher for Agent Space backend with key runtime flags."""

from __future__ import annotations

import argparse
import os

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Agent Space backend.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--model", default="qwen2.5-coder:14b")
    parser.add_argument("--command-profile", default="safe", choices=["safe", "dev", "unrestricted"])
    parser.add_argument("--review-gate", action="store_true", default=False)
    parser.add_argument("--no-review-gate", action="store_true", default=False)
    parser.add_argument("--allow-shell", action="store_true", default=False)
    parser.add_argument("--max-actions", type=int, default=40)
    parser.add_argument("--max-seconds", type=int, default=1200)
    parser.add_argument("--desktop-mode", action="store_true", default=False)
    parser.add_argument("--create-git-checkpoint", action="store_true", default=False)
    parser.add_argument("--run-budget-tokens", type=int, default=16000)
    parser.add_argument("--proactive-enabled", action="store_true", default=False)
    parser.add_argument("--proactive-tick-seconds", type=int, default=5)
    parser.add_argument("--reload", action="store_true", default=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    review_gate = True
    if args.no_review_gate:
        review_gate = False
    elif args.review_gate:
        review_gate = True

    os.environ["BACKEND_PORT"] = str(args.port)
    os.environ["FRONTEND_PORT"] = str(args.frontend_port)
    os.environ["AGENT_SPACE_MODEL"] = args.model
    os.environ["AGENT_SPACE_COMMAND_PROFILE"] = args.command_profile
    os.environ["AGENT_SPACE_REVIEW_GATE"] = "true" if review_gate else "false"
    os.environ["AGENT_SPACE_ALLOW_SHELL"] = "true" if args.allow_shell else "false"
    os.environ["AGENT_SPACE_MAX_ACTIONS"] = str(args.max_actions)
    os.environ["AGENT_SPACE_MAX_SECONDS"] = str(args.max_seconds)
    os.environ["AGENT_SPACE_DESKTOP_MODE"] = "true" if args.desktop_mode else "false"
    os.environ["AGENT_SPACE_GIT_CHECKPOINT"] = "true" if args.create_git_checkpoint else "false"
    os.environ["AGENT_SPACE_RUN_BUDGET_TOKENS"] = str(args.run_budget_tokens)
    os.environ["AGENT_SPACE_PROACTIVE_ENABLED"] = "true" if args.proactive_enabled else "false"
    os.environ["AGENT_SPACE_PROACTIVE_TICK_SECONDS"] = str(args.proactive_tick_seconds)

    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
