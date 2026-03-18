"""Test script — verifies all Ollama models across speed modes are present and working."""

import sys
import time
import httpx

OLLAMA_URL = "http://localhost:11434"

MODELS_TO_TEST = {
    "balanced": {
        "math":   ("deepseek-r1:14b",      "What is 2+2? Answer briefly."),
        "code":   ("qwen2.5-coder:14b",     "Write a Python hello world. Be brief."),
        "chat":   ("qwen3:8b",              "Say hello in one sentence."),
        "vision": ("qwen2.5vl:7b",          "Describe what you can do in one sentence."),
        "embed":  ("nomic-embed-text",       None),
    },
    "fast": {
        "math":   ("qwen2-math:7b-instruct", "What is 3+3? Answer briefly."),
        "code":   ("qwen2.5-coder:7b",       "Write a Python hello world. Be brief."),
    },
    "deep": {
        "all":    ("qwen2.5:32b",            "Say hello in one sentence."),
    },
}


def check_models():
    print("=" * 60)
    print("  Private AI — Model Verification (3-tier)")
    print("=" * 60)
    print()

    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        available = {m["name"] for m in data.get("models", [])}
        print(f"  Ollama running at {OLLAMA_URL}")
        print(f"  {len(available)} model(s) installed")
        print()
    except httpx.ConnectError:
        print(f"  Ollama is NOT running at {OLLAMA_URL}")
        print("  Start it with: ollama serve")
        sys.exit(1)
    except Exception as e:
        print(f"  Error connecting to Ollama: {e}")
        sys.exit(1)

    results = []

    for tier, models in MODELS_TO_TEST.items():
        print(f"── {tier.upper()} mode {'─' * (50 - len(tier))}")
        optional = tier == "deep"

        for role, (model_name, prompt) in models.items():
            found = any(model_name in m for m in available)

            if not found:
                label = "(optional)" if optional else "MISSING"
                color = "" if optional else "  → Run: ollama pull " + model_name
                print(f"  ✗ {model_name:<30} [{role}] {label}")
                if color:
                    print(f"    {color}")
                results.append((model_name, False, 0, optional))
                continue

            start = time.time()
            if prompt is None:
                try:
                    resp = httpx.post(
                        f"{OLLAMA_URL}/api/embeddings",
                        json={"model": model_name, "prompt": "test"},
                        timeout=30.0,
                    )
                    resp.raise_for_status()
                    emb = resp.json().get("embedding", [])
                    latency = int((time.time() - start) * 1000)
                    print(f"  ✓ {model_name:<30} [{role}] dim={len(emb)}, {latency}ms")
                    results.append((model_name, True, latency, optional))
                except Exception as e:
                    latency = int((time.time() - start) * 1000)
                    print(f"  ✗ {model_name:<30} [{role}] embed failed: {e}")
                    results.append((model_name, False, latency, optional))
            else:
                try:
                    resp = httpx.post(
                        f"{OLLAMA_URL}/api/generate",
                        json={"model": model_name, "prompt": prompt, "stream": False},
                        timeout=120.0,
                    )
                    resp.raise_for_status()
                    text = resp.json().get("response", "")
                    latency = int((time.time() - start) * 1000)
                    preview = text.replace("\n", " ").strip()[:80]
                    print(f"  ✓ {model_name:<30} [{role}] {latency}ms")
                    print(f"    \"{preview}\"")
                    results.append((model_name, True, latency, optional))
                except Exception as e:
                    latency = int((time.time() - start) * 1000)
                    print(f"  ✗ {model_name:<30} [{role}] failed: {e}")
                    results.append((model_name, False, latency, optional))

        print()

    passed = sum(1 for _, ok, _, opt in results if ok)
    failed_required = sum(1 for _, ok, _, opt in results if not ok and not opt)
    failed_optional = sum(1 for _, ok, _, opt in results if not ok and opt)

    print("=" * 60)
    if failed_required == 0:
        print(f"  PASS — {passed} models verified ✓")
        if failed_optional > 0:
            print(f"  ({failed_optional} optional model(s) not installed — Deep mode unavailable)")
    else:
        print(f"  FAIL — {passed} passed, {failed_required} required missing")
        missing = [name for name, ok, _, opt in results if not ok and not opt]
        print()
        print("  To install missing models:")
        for m in missing:
            print(f"    ollama pull {m}")
    print("=" * 60)

    return failed_required == 0


if __name__ == "__main__":
    success = check_models()
    sys.exit(0 if success else 1)
