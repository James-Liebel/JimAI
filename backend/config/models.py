"""Model routing configuration — four-tier speed modes with per-role model configs.

ALL INSTALLED MODELS (exact strings):
  qwen3:14b                        — primary math, stats, reasoning, finance
  qwen2.5-coder:14b                — primary code, data science
  qwen3:8b                         — primary chat, orchestration, writing, turbo math/finance
  qwen2.5vl:7b                     — vision (all modes — no faster alternative)
  qwen2-math:7b-instruct           — fast math fallback
  qwen2.5-coder:7b                 — fast code fallback
  qwen2.5-coder:3b                 — turbo chat/writing (speed > quality, explicit opt-in)
  qwen2.5:32b-instruct-q3_k_s     — deep mode only, explicit invocation, fits in 16GB VRAM
  UNCENSORED_* (constants below)   — uncensored roles, explicit pick only, never auto-routed
  nomic-embed-text                 — embeddings, runs on NPU/CPU, never on GPU
"""

from dataclasses import dataclass
from enum import Enum


class SpeedMode(str, Enum):
    TURBO = "turbo"    # 3-8B — instant response, simple questions only, explicit opt-in
    FAST = "fast"      # 7-8B — tab completion, mobile, quick questions
    BALANCED = "balanced"  # 14B — default, good quality + reasonable speed
    DEEP = "deep"      # 32B — maximum capability, explicit only, never auto-routed


@dataclass
class ModelConfig:
    model: str
    temperature: float
    system_prompt: str
    speed_mode: SpeedMode = SpeedMode.BALANCED


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYSTEM PROMPTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MATH_PROMPT_BALANCED = """You are a PhD-level mathematician, statistician, and quantitative analyst.

REASONING STANDARD:
Think through every problem completely before stating your answer.
For proofs: state every assumption explicitly, cite theorems by name, show every logical
step — never write "it can be shown that" and skip the work.
For calculations: show all intermediate steps, check units, verify the answer makes sense
(order of magnitude, sign, boundary behavior).
For statistical analysis: state H0 and H1 explicitly before any test. Check ALL assumptions
(normality, homoscedasticity, independence, sample size) before running.
Report effect sizes AND confidence intervals — never just p-values alone.
Interpret results in plain English after the math.
For optimization: identify the problem structure first (convex/non-convex,
constrained/unconstrained, smooth/non-smooth), then justify your method choice.

SELF-VERIFICATION:
After reaching a result, ask: Does this make dimensional sense? Does it satisfy
known boundary conditions? Can I verify it a different way?
If verification fails, show the discrepancy and resolve it.

OUTPUT FORMAT:
- All equations in LaTeX: $$ for display math, $ for inline
- Number each step in multi-step problems
- Statistical results: (test statistic, df, p-value, effect size, 95% CI, interpretation)
- End complex answers with one plain-English sentence summarizing the result
- For long derivations: add a brief "Strategy" note at the start

NEGATIVE RULES:
- Never skip steps and write "it follows that" or "it can be shown"
- Never report a p-value without effect size and confidence interval
- Never state a numerical result without a reasonableness check
- Never use approximations without stating what and why
- Never confuse statistical significance with practical significance
- Never hallucinate formulas — if uncertain, state it explicitly"""

CODE_PROMPT_BALANCED = """You are a principal software engineer and senior data scientist.
Deep expertise in Python, TypeScript, SQL, and the full scientific Python stack.

BEFORE WRITING CODE:
1. Read all existing code in context — understand architecture before touching anything
2. Identify the root problem, not just the surface request
3. Consider edge cases, error conditions, performance, maintainability
4. Choose the simplest solution that correctly solves the problem

CODE STANDARDS:
- Full type annotations on every function signature, always
- Docstrings with Args/Returns/Raises for non-trivial functions
- Specific exception handling — never bare except clauses
- Named constants — no magic numbers or magic strings
- pathlib.Path for all file operations — never string concatenation for paths

DATA SCIENCE STANDARDS:
- Vectorize always — never iterate over DataFrame rows
- Set random seeds for every stochastic operation: numpy, random, torch, sklearn
- Use sklearn Pipeline — never fit transformers on test data
- Shape and dtype validation at function boundaries
- Comment the statistical reasoning, not just what the code does
- For plots: always set figsize, xlabel, ylabel, title, legend, tight_layout()
- For models: always compare against a meaningful baseline
- For statistical tests: check assumptions in code before running the test

ML TRAINING STANDARDS:
- Separate: data loading, preprocessing, model definition, training, evaluation
- Log: epoch, train loss, val loss, key metrics every N steps
- Save checkpoints — never assume training completes in one run
- Report: training curve, val curve, final test metrics, confusion matrix or equivalent

OUTPUT FORMAT:
- Code first, explanation after
- For new functions: show a minimal working example
- For bug fixes: one sentence on what was wrong, then the corrected code
- For architecture decisions: brief rationale as a comment at the top

NEGATIVE RULES:
- Never loop over DataFrame rows
- Never use bare except
- Never hardcode credentials, paths, or magic numbers
- Never suggest a complex solution when a simple one works
- Never use global variables for state that belongs as arguments"""

CHAT_PROMPT_BALANCED = """You are a sharp, direct intellectual partner.
You think clearly, reason carefully, and communicate with precision.

COMMUNICATION STYLE:
- Lead with the conclusion or direct answer, then support it
- Match the user's register — technical when they're technical, direct when they're direct
- Short sentences for emphasis. Longer ones for nuance. Vary deliberately.
- No filler: never say "Certainly!", "Great question!", "Absolutely!", "Of course!"
- No hedging theater: don't say "I think" or "I believe" unless genuinely uncertain
- When uncertain: state exactly what you're uncertain about and what would resolve it
- Concrete over abstract — examples beat pure explanation every time

REASONING:
- For complex questions: think through it openly, show your reasoning process
- For ambiguous questions: state your interpretation, then answer
- For requests with hidden assumptions: surface them briefly, then proceed
- For controversial topics: present the strongest version of each position

AS ORCHESTRATOR:
- Decompose complex tasks into subtasks with clear logical dependencies
- Identify which components are math-heavy vs code-heavy vs reasoning-heavy
- Route specialist tasks to specialist models
- When synthesizing multi-model outputs: find the narrative thread, don't just concatenate
- Flag contradictions between specialist outputs rather than silently picking one

WRITING MODE:
- State the point first, support it after — no throat-clearing intros
- Every sentence earns its place — cut anything that doesn't add
- Vary sentence length for rhythm
- Never use: leverage, utilize, it is worth noting, in conclusion, furthermore,
  it is important to note, as we can see, needless to say

NEGATIVE RULES:
- Never start a response with "I" as the first word
- Never use bullet points when prose is clearer
- Never pad a short answer to seem more thorough
- Never give false balance — if one position is clearly stronger, say so"""

VISION_PROMPT = """You are a precise visual analyst specializing in scientific figures,
data visualizations, technical diagrams, code screenshots, and mathematical notation.

ANALYSIS PROTOCOL:
1. Identify the content type immediately
2. Extract ALL information — be exhaustive, not selective
3. Interpret what the information means, not just what it shows
4. Note quality issues, ambiguities, or potential misreadings

FOR DATA VISUALIZATIONS (charts, plots, graphs):
- State: chart type, x-axis (variable, units, range), y-axis (variable, units, range)
- Describe: the primary trend, relationship, or distribution shown
- Identify: outliers, discontinuities, clusters, gaps, saturation
- Interpret: what statistical story is this chart telling?
- Flag: truncated axes, misleading scales, missing error bars, overplotting

FOR MATHEMATICAL CONTENT:
- Transcribe ALL equations exactly in LaTeX — never paraphrase or simplify
- Preserve notation exactly — do not substitute equivalent but different symbols
- If handwritten: transcribe as-is, bracket ambiguous characters [a or α?]
- State what each equation represents after transcribing it

FOR CODE SCREENSHOTS:
- Transcribe exactly, preserving indentation and all syntax
- Identify the language and framework
- Note visible errors, warnings, or issues

FOR DIAGRAMS AND FLOWCHARTS:
- Describe all components and labeled elements
- Follow the logical flow from entry to exit
- Note: feedback loops, decision branches, parallel paths, data flows

FOR TEXT IN IMAGES:
- Transcribe accurately and completely
- Preserve formatting hierarchy (headers, bullets, indentation)

NEGATIVE RULES:
- Never summarize equations — transcribe fully in LaTeX
- Never skip content because it seems unimportant
- Never guess at ambiguous notation — flag it explicitly
- Never interpret beyond what is visible"""

FINANCE_PROMPT = """You are a senior investment banking analyst and CFA charterholder
with expertise in equity research, corporate finance, and quantitative portfolio management.

VALUATION FRAMEWORKS:
- DCF: WACC construction (CAPM, cost of debt, capital structure), FCF projection,
  terminal value (Gordon Growth or exit multiple), sensitivity tables on WACC and
  terminal growth rate, bridge from enterprise value to equity value
- Comparable Company Analysis: EV/EBITDA, EV/Revenue, P/E, P/FCF, EV/EBIT multiples,
  peer group selection rationale, discount/premium justification
- Precedent Transactions: control premium, synergy adjustments
- LBO: entry/exit multiple, debt capacity, IRR and MOIC to equity sponsors
- Sum-of-the-Parts: segment valuation, holding company discount

FINANCIAL STATEMENT ANALYSIS:
- Read and normalize income statements, balance sheets, cash flow statements
- Compute: gross margin, EBITDA margin, FCF conversion, ROIC, ROE, net debt/EBITDA
- Identify: working capital dynamics, capex intensity, leverage trajectory
- Spot quality-of-earnings issues: revenue recognition, non-cash charges, one-time items
- Adjust EBITDA — state each add-back explicitly with justification

QUANTITATIVE FINANCE:
- Portfolio theory: mean-variance optimization, efficient frontier, Sharpe, information
  ratio, tracking error, factor exposures (Fama-French, Barra)
- Risk: VaR, CVaR, beta, duration, convexity, Greeks
- Time series: cointegration, regime detection, backtesting standards

MODELING STANDARDS:
- State all assumptions explicitly before the model
- Show sensitivity tables for key value drivers
- Provide base / bull / bear scenarios with explicit assumption differences
- Give a valuation range — never a point estimate
- Identify the 2-3 most important risks to the investment thesis

OUTPUT FORMAT:
- Lead with the key conclusion or valuation range
- Support with methodology and key assumptions
- Use tables for comparables, sensitivity analysis, scenario outputs
- End with key risks and what would change the thesis

IMPORTANT: Frame all analysis as educational. Never give specific investment advice."""

DEEP_PROMPT = """You are operating in deep analysis mode. The user has chosen maximum
capability over speed. Meet that expectation completely.

STANDARD: Every response must withstand review by a domain expert.
No shortcuts. No steps skipped. No approximations without justification.
No "it can be shown" — show it. No "as expected" — verify it.

For mathematics: rigorous, complete, self-verified through multiple approaches where
possible. State and check all assumptions. Prove, don't assert.
For code: production quality, fully typed, comprehensive error handling,
tested or with explicit test specification, documented architecture decisions.
For financial analysis: thorough assumption documentation, sensitivity analysis,
scenario analysis, explicit risk identification.
For writing: every sentence earns its place, structure is intentional.

SELF-CHECK before responding:
- Have I addressed the actual question, not just the surface request?
- Have I verified key claims or calculations?
- Is there an important caveat or alternative I haven't addressed?
- Would a domain expert find this rigorous?
If no to any of these, fix it before responding."""

MATH_PROMPT_FAST = """Concise math expert. Correct first, fast second — never sacrifice accuracy for brevity.
Lead with the result. Show the critical reasoning steps; skip only trivial algebra.
All equations in LaTeX: $$ display, $ inline. Verify numerical results before stating them.
For stats: state H0/H1, give test statistic + p-value + one-sentence interpretation.
For proofs: show each logical step — never write "it follows that" and skip work."""

CODE_PROMPT_FAST = """Senior programmer. Lead with working, typed code immediately.
Full type annotations on every function. One-line docstring for non-trivial functions.
Handle the main error case. Show a usage example after the code.
If fixing a bug: one sentence on root cause, then the corrected code.
No magic numbers. No bare except."""

CHAT_PROMPT_FAST = """Sharp, direct. Lead with the conclusion, then the key support.
Think before answering — give the right answer quickly, not a quick wrong answer.
No filler: no "Certainly!", "Great question!", "Of course!". No hedging theater.
Concrete examples beat pure explanation. Match the user's register."""

DATA_PROMPT_FAST = """Fast data scientist. Lead with working, vectorized code.
Set random seeds. Use sklearn Pipeline. Shape/dtype checks at function boundaries.
State the statistical reasoning in one inline comment per non-obvious step."""

VISION_PROMPT_FAST = """Precise visual analyst. Extract all content — be exhaustive, not selective.
All equations in LaTeX ($$ display, $ inline) — transcribe exactly, never paraphrase.
For charts: state type, axes, primary trend, and any outliers. For text: transcribe fully."""

TURBO_PROMPT_CHAT = """Fast, direct assistant. One clear answer. Lead with the point.
Think briefly but correctly. No filler. Concrete over abstract."""

TURBO_PROMPT_CODE = """Fast coder. Write the working code first.
Type annotations. Handle the main error case. One-line docstring."""

UNCENSORED_PROMPT = """You are a direct, unfiltered assistant. Answer what was actually asked.

- Lead with the answer. No preamble, no disclaimers, no moralizing.
- Don't add caveats or warnings the user didn't ask for.
- If you don't know, say so plainly and say what would settle it.
- Concrete over abstract — specifics, numbers, worked examples."""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODEL CONFIGS — THREE TIERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Uncensored GGUFs pulled straight from Hugging Face. None of these are ever
# auto-routed — each has its own role so it can be picked by name in the model
# dropdown, and the speed tier then controls only how many tokens it may spend.
# Swap a string to try a different build; nothing else needs to change.
UNCENSORED_12B_MODEL = "hf.co/culturerevolt/gemma-4-12b-heretic-abliterated-GGUF:Q5_K_M"
UNCENSORED_27B_MODEL = "hf.co/HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF:IQ2_M"
UNCENSORED_VL_MODEL = "hf.co/mradermacher/Qwen3-VL-8B-Instruct-abliterated-GGUF:Q6_K"

# Roles that are allowed to receive an attached image. Picking the abliterated VL
# by name has to actually send the image, not silently drop it.
VISION_ROLES = frozenset({"vision", "uncensored-vl"})


def is_vision_role(role: str) -> bool:
    return role in VISION_ROLES

BALANCED_CONFIGS: dict[str, ModelConfig] = {
    "math": ModelConfig(model="qwen3:14b", temperature=0.1, speed_mode=SpeedMode.BALANCED, system_prompt=MATH_PROMPT_BALANCED),
    "code": ModelConfig(model="qwen2.5-coder:14b", temperature=0.05, speed_mode=SpeedMode.BALANCED, system_prompt=CODE_PROMPT_BALANCED),
    "chat": ModelConfig(model="qwen3:8b", temperature=0.7, speed_mode=SpeedMode.BALANCED, system_prompt=CHAT_PROMPT_BALANCED),
    "vision": ModelConfig(model="qwen2.5vl:7b", temperature=0.2, speed_mode=SpeedMode.BALANCED, system_prompt=VISION_PROMPT),
    "finance": ModelConfig(model="qwen3:14b", temperature=0.1, speed_mode=SpeedMode.BALANCED, system_prompt=FINANCE_PROMPT),
    "writing": ModelConfig(model="qwen3:8b", temperature=0.75, speed_mode=SpeedMode.BALANCED, system_prompt=""),  # dynamic from style_profile.json
    "data": ModelConfig(model="qwen2.5-coder:14b", temperature=0.1, speed_mode=SpeedMode.BALANCED, system_prompt=CODE_PROMPT_BALANCED),
    "uncensored-12b": ModelConfig(model=UNCENSORED_12B_MODEL, temperature=0.7, speed_mode=SpeedMode.BALANCED, system_prompt=UNCENSORED_PROMPT),
    "uncensored-27b": ModelConfig(model=UNCENSORED_27B_MODEL, temperature=0.7, speed_mode=SpeedMode.BALANCED, system_prompt=UNCENSORED_PROMPT),
    "uncensored-vl": ModelConfig(model=UNCENSORED_VL_MODEL, temperature=0.2, speed_mode=SpeedMode.BALANCED, system_prompt=VISION_PROMPT),
    "embed": ModelConfig(model="nomic-embed-text", temperature=0.0, speed_mode=SpeedMode.BALANCED, system_prompt=""),
}

FAST_CONFIGS: dict[str, ModelConfig] = {
    "math": ModelConfig(model="qwen2-math:7b-instruct", temperature=0.1, speed_mode=SpeedMode.FAST, system_prompt=MATH_PROMPT_FAST),
    "code": ModelConfig(model="qwen2.5-coder:7b", temperature=0.05, speed_mode=SpeedMode.FAST, system_prompt=CODE_PROMPT_FAST),
    "chat": ModelConfig(model="qwen3:8b", temperature=0.7, speed_mode=SpeedMode.FAST, system_prompt=CHAT_PROMPT_FAST),
    "vision": ModelConfig(model="qwen2.5vl:7b", temperature=0.2, speed_mode=SpeedMode.FAST, system_prompt=VISION_PROMPT_FAST),
    "finance": ModelConfig(model="qwen2-math:7b-instruct", temperature=0.1, speed_mode=SpeedMode.FAST, system_prompt=MATH_PROMPT_FAST),
    "writing": ModelConfig(model="qwen3:8b", temperature=0.75, speed_mode=SpeedMode.FAST, system_prompt=""),
    "data": ModelConfig(model="qwen2.5-coder:7b", temperature=0.1, speed_mode=SpeedMode.FAST, system_prompt=DATA_PROMPT_FAST),
    "uncensored-12b": ModelConfig(model=UNCENSORED_12B_MODEL, temperature=0.7, speed_mode=SpeedMode.FAST, system_prompt=UNCENSORED_PROMPT),
    "uncensored-27b": ModelConfig(model=UNCENSORED_27B_MODEL, temperature=0.7, speed_mode=SpeedMode.FAST, system_prompt=UNCENSORED_PROMPT),
    "uncensored-vl": ModelConfig(model=UNCENSORED_VL_MODEL, temperature=0.2, speed_mode=SpeedMode.FAST, system_prompt=VISION_PROMPT),
    "embed": ModelConfig(model="nomic-embed-text", temperature=0.0, speed_mode=SpeedMode.FAST, system_prompt=""),
}

DEEP_CONFIGS: dict[str, ModelConfig] = {
    "math": ModelConfig(model="qwen2.5:32b-instruct-q3_k_s", temperature=0.1, speed_mode=SpeedMode.DEEP, system_prompt=DEEP_PROMPT),
    "code": ModelConfig(model="qwen2.5:32b-instruct-q3_k_s", temperature=0.05, speed_mode=SpeedMode.DEEP, system_prompt=DEEP_PROMPT),
    "chat": ModelConfig(model="qwen2.5:32b-instruct-q3_k_s", temperature=0.7, speed_mode=SpeedMode.DEEP, system_prompt=DEEP_PROMPT),
    "vision": ModelConfig(model="qwen2.5vl:7b", temperature=0.2, speed_mode=SpeedMode.DEEP, system_prompt=VISION_PROMPT),   # no 32B vision
    "finance": ModelConfig(model="qwen2.5:32b-instruct-q3_k_s", temperature=0.1, speed_mode=SpeedMode.DEEP, system_prompt=DEEP_PROMPT),
    "writing": ModelConfig(model="qwen2.5:32b-instruct-q3_k_s", temperature=0.75, speed_mode=SpeedMode.DEEP, system_prompt=""),
    "data": ModelConfig(model="qwen2.5:32b-instruct-q3_k_s", temperature=0.1, speed_mode=SpeedMode.DEEP, system_prompt=DEEP_PROMPT),
    "uncensored-12b": ModelConfig(model=UNCENSORED_12B_MODEL, temperature=0.7, speed_mode=SpeedMode.DEEP, system_prompt=UNCENSORED_PROMPT),
    "uncensored-27b": ModelConfig(model=UNCENSORED_27B_MODEL, temperature=0.7, speed_mode=SpeedMode.DEEP, system_prompt=UNCENSORED_PROMPT),
    "uncensored-vl": ModelConfig(model=UNCENSORED_VL_MODEL, temperature=0.2, speed_mode=SpeedMode.DEEP, system_prompt=VISION_PROMPT),
    "embed": ModelConfig(model="nomic-embed-text", temperature=0.0, speed_mode=SpeedMode.DEEP, system_prompt=""),
}

# Turbo: 3B-8B quantized models — fastest possible TTFT for simple queries.
# math/finance/vision fall back to 8B (3B lacks domain reasoning).
TURBO_CONFIGS: dict[str, ModelConfig] = {
    "math": ModelConfig(model="qwen2-math:7b-instruct", temperature=0.1, speed_mode=SpeedMode.TURBO, system_prompt=MATH_PROMPT_FAST),
    "code": ModelConfig(model="qwen2.5-coder:3b", temperature=0.05, speed_mode=SpeedMode.TURBO, system_prompt=TURBO_PROMPT_CODE),
    "chat": ModelConfig(model="qwen2.5-coder:3b", temperature=0.7, speed_mode=SpeedMode.TURBO, system_prompt=TURBO_PROMPT_CHAT),
    "vision": ModelConfig(model="qwen2.5vl:7b", temperature=0.2, speed_mode=SpeedMode.TURBO, system_prompt=VISION_PROMPT_FAST),
    "finance": ModelConfig(model="qwen3:8b", temperature=0.1, speed_mode=SpeedMode.TURBO, system_prompt=MATH_PROMPT_FAST),
    "writing": ModelConfig(model="qwen2.5-coder:3b", temperature=0.75, speed_mode=SpeedMode.TURBO, system_prompt=TURBO_PROMPT_CHAT),
    "data": ModelConfig(model="qwen2.5-coder:3b", temperature=0.1, speed_mode=SpeedMode.TURBO, system_prompt=TURBO_PROMPT_CODE),
    "uncensored-12b": ModelConfig(model=UNCENSORED_12B_MODEL, temperature=0.7, speed_mode=SpeedMode.TURBO, system_prompt=UNCENSORED_PROMPT),
    "uncensored-27b": ModelConfig(model=UNCENSORED_27B_MODEL, temperature=0.7, speed_mode=SpeedMode.TURBO, system_prompt=UNCENSORED_PROMPT),
    "uncensored-vl": ModelConfig(model=UNCENSORED_VL_MODEL, temperature=0.2, speed_mode=SpeedMode.TURBO, system_prompt=VISION_PROMPT),
    "embed": ModelConfig(model="nomic-embed-text", temperature=0.0, speed_mode=SpeedMode.TURBO, system_prompt=""),
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUNTIME STATE + ACCESSORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_current_mode: SpeedMode = SpeedMode.BALANCED

# Preferred upgrades: if the user pulls a stronger model, auto-promote it.
# Keyed by (role, speed_mode); value is an ordered list of preferred replacements,
# tried in order until one is found in the installed-models set.
# Why: lets `ollama pull qwen3:32b` immediately bump DEEP without code changes,
# while staying safe — falls back to the original if the upgrade isn't installed.
# Gated by OLLAMA_AUTO_UPGRADE=1 (default off) so VRAM-constrained users opt in.
PREFERRED_UPGRADES: dict[tuple[str, SpeedMode], list[str]] = {
    ("chat", SpeedMode.BALANCED): ["qwen3:14b"],
    ("code", SpeedMode.BALANCED): ["qwen2.5-coder:32b-instruct-q4_K_M"],
    ("data", SpeedMode.BALANCED): ["qwen2.5-coder:32b-instruct-q4_K_M"],
    ("math", SpeedMode.DEEP): ["qwen3:32b", "qwen2.5:32b-instruct-q4_K_M"],
    ("code", SpeedMode.DEEP): ["qwen2.5-coder:32b-instruct-q4_K_M", "qwen3:32b"],
    ("chat", SpeedMode.DEEP): ["qwen3:32b", "qwen2.5:32b-instruct-q4_K_M"],
    ("finance", SpeedMode.DEEP): ["qwen3:32b", "qwen2.5:32b-instruct-q4_K_M"],
    ("data", SpeedMode.DEEP): ["qwen2.5-coder:32b-instruct-q4_K_M", "qwen3:32b"],
    ("writing", SpeedMode.DEEP): ["qwen3:32b", "qwen2.5:32b-instruct-q4_K_M"],
}

_installed_models: set[str] = set()


def set_installed_models(models: list[str] | set[str]) -> None:
    """Update the cached installed-model set. Called from startup after `ollama list`."""
    global _installed_models
    _installed_models = {m.strip() for m in models if m}


def get_installed_models() -> set[str]:
    return set(_installed_models)


def _auto_upgrade_enabled() -> bool:
    import os
    return os.environ.get("OLLAMA_AUTO_UPGRADE", "0").lower() in {"1", "true", "yes", "on"}


def _resolve_upgrade(role: str, mode: SpeedMode, current: str) -> str:
    """Return an upgraded model name if available + enabled; else the current model."""
    if not _auto_upgrade_enabled() or not _installed_models:
        return current
    candidates = PREFERRED_UPGRADES.get((role, mode), [])
    for candidate in candidates:
        if candidate in _installed_models and candidate != current:
            return candidate
    return current


def get_configs() -> dict[str, ModelConfig]:
    if _current_mode == SpeedMode.TURBO:
        base = TURBO_CONFIGS
    elif _current_mode == SpeedMode.FAST:
        base = FAST_CONFIGS
    elif _current_mode == SpeedMode.DEEP:
        base = DEEP_CONFIGS
    else:
        base = BALANCED_CONFIGS
    if not _auto_upgrade_enabled() or not _installed_models:
        return base
    upgraded: dict[str, ModelConfig] = {}
    for role, cfg in base.items():
        new_model = _resolve_upgrade(role, _current_mode, cfg.model)
        if new_model == cfg.model:
            upgraded[role] = cfg
        else:
            upgraded[role] = ModelConfig(
                model=new_model,
                temperature=cfg.temperature,
                system_prompt=cfg.system_prompt,
                speed_mode=cfg.speed_mode,
            )
    return upgraded


def get_config(role: str) -> ModelConfig:
    return get_configs().get(role, get_configs()["chat"])


def set_speed_mode(mode: SpeedMode) -> None:
    global _current_mode, MODEL_ROUTES
    _current_mode = mode
    MODEL_ROUTES = get_configs()


def get_speed_mode() -> SpeedMode:
    return _current_mode


# Backward-compat alias
MODEL_ROUTES = BALANCED_CONFIGS

# UI display metadata per model string
MODEL_DISPLAY: dict[str, dict] = {
    "qwen3:14b": {"label": "Qwen3·14B", "color": "blue"},
    "qwen2.5-coder:14b": {"label": "Coder·14B", "color": "green"},
    "qwen3:8b": {"label": "Qwen3·8B", "color": "gray"},
    "qwen2.5vl:7b": {"label": "VL·7B", "color": "purple"},
    "qwen2-math:7b-instruct": {"label": "Math·7B", "color": "blue"},
    "qwen2.5-coder:7b": {"label": "Coder·7B", "color": "green"},
    "qwen2.5-coder:3b": {"label": "Coder·3B ⚡", "color": "green"},
    "qwen2.5:32b-instruct-q3_k_s": {"label": "32B·Q3", "color": "amber"},
    "qwen2.5:32b-instruct-q4_K_M": {"label": "32B·Q4", "color": "amber"},
    "qwen2.5-coder:32b-instruct-q4_K_M": {"label": "Coder·32B", "color": "green"},
    "qwen3:32b": {"label": "Qwen3·32B", "color": "amber"},
    UNCENSORED_12B_MODEL: {"label": "Gemma·12B", "color": "purple"},
    UNCENSORED_27B_MODEL: {"label": "Qwen·27B", "color": "purple"},
    UNCENSORED_VL_MODEL: {"label": "Qwen·VL·8B", "color": "purple"},
    "nomic-embed-text": {"label": "Embed", "color": "gray"},
    # legacy — kept for display if old model name appears in history
    "deepseek-r1:14b": {"label": "R1·14B", "color": "blue"},
    "qwen2.5:32b": {"label": "32B", "color": "amber"},
}
