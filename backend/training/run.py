"""CLI for the fine-tuning subsystem.

    python -m training.run list                 # show every model + train method
    python -m training.run build-all            # prep datasets/scripts for all models
    python -m training.run build --model qwen3:8b
    python -m training.run create --tag jimai-qwen3:8b --modelfile <path>

`build*` only prepares artifacts; run the emitted train.py on a GPU/WSL2 box,
then `create` registers the trained adapter with Ollama.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from config.settings import PROJECT_ROOT

from .catalog import all_models
from .modelfile import create_model
from .pipeline import BuildResult, prepare_all, prepare_model
from . import dataset as ds

DEFAULT_OUT = PROJECT_ROOT / "data" / "training"


def _print_result(result: BuildResult) -> None:
    if result.skipped:
        print(f"  - {result.model:<32} SKIPPED: {result.skipped}")
        return
    print(
        f"  - {result.model:<32} sft={result.sft_count:<5} dpo={result.dpo_count:<4} "
        f"-> {result.script_path}"
    )


def _cmd_list(_: argparse.Namespace) -> int:
    print("Models in the stack:")
    for entry in all_models():
        roles = ",".join(entry.roles)
        print(f"  - {entry.model:<32} [{entry.method.value:<11}] roles={roles}")
        if entry.note:
            print(f"      note: {entry.note}")
    return 0


def _cmd_build_all(args: argparse.Namespace) -> int:
    out = Path(args.out)
    print(f"Preparing all trainable models -> {out}")
    for result in prepare_all(out):
        _print_result(result)
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    entry = next((e for e in all_models() if e.model == args.model), None)
    if entry is None:
        print(f"Unknown model: {args.model}")
        return 1
    out = Path(args.out)
    result = prepare_model(
        entry, out,
        sft_examples=ds.build_sft_examples(),
        dpo_pairs=ds.build_dpo_pairs(),
    )
    _print_result(result)
    return 0


def _cmd_create(args: argparse.Namespace) -> int:
    proc = create_model(args.tag, Path(args.modelfile))
    print(proc.stdout or "")
    if proc.returncode != 0:
        print(proc.stderr or "")
        return proc.returncode
    print(f"Registered {args.tag} with Ollama.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="training.run", description="JimAI local fine-tuning.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List models and their training method.").set_defaults(func=_cmd_list)

    p_all = sub.add_parser("build-all", help="Prepare artifacts for all trainable models.")
    p_all.add_argument("--out", default=str(DEFAULT_OUT))
    p_all.set_defaults(func=_cmd_build_all)

    p_one = sub.add_parser("build", help="Prepare artifacts for one model.")
    p_one.add_argument("--model", required=True)
    p_one.add_argument("--out", default=str(DEFAULT_OUT))
    p_one.set_defaults(func=_cmd_build)

    p_create = sub.add_parser("create", help="Register a trained Modelfile with Ollama.")
    p_create.add_argument("--tag", required=True)
    p_create.add_argument("--modelfile", required=True)
    p_create.set_defaults(func=_cmd_create)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
