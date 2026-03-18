"""Message classification and model routing."""

import re
import logging
from dataclasses import dataclass, field

from config.models import ModelConfig, get_config, get_speed_mode

logger = logging.getLogger(__name__)

_current_model: str | None = None


@dataclass
class RoutingDecision:
    primary_model: str
    primary_role: str
    pipeline: list[str]
    pipeline_roles: list[str]
    is_hybrid: bool
    confidence: float
    reasoning: str
    detected_domains: list[str]
    speed_mode: str = ""
    manual_override: str | None = None


MATH_PATTERNS = [
    r'\bintegral\b', r'\bderivative\b', r'\bmatrix\b', r'\beigenvalue\b',
    r'\bproof\b', r'\btheorem\b', r'\bprobability\b', r'\bdistribution\b',
    r'\bhypothesis\b', r'\bp-value\b', r'\bregression\b', r'\bsolve\b',
    r'\bcalculate\b', r'\bdifferentiate\b', r'\bgradient\b', r'\bhessian\b',
    r'\bbayes\b', r'\blikelihood\b', r'\bexpectation\b', r'\bvariance\b',
    r'\bcovariance\b', r'\bstatistic\b', r'\bnormal distribution\b',
    r'\bt-test\b', r'\banova\b', r'\bmarkov\b', r'\bmonte carlo\b',
    r'\boptimiz\b', r'\bconvex\b', r'\blinear algebra\b', r'\bcalculus\b',
    r'\bdifferential equation\b', r'\beigen\b', r'\bsvd\b', r'\bpca\b',
    r'\bchi-square\b', r'\bconfidence interval\b', r'\bpower analysis\b',
    r'\bkl divergence\b', r'\bentropy\b', r'\bmle\b', r'\bmap estimate\b',
    r'\bmcmc\b', r'\bstochastic\b', r'\bfourier\b', r'\blaplace\b',
]

CODE_PATTERNS = [
    r'\bwrite\b.{0,20}\b(code|function|class|script)\b',
    r'\b(debug|fix|refactor|implement|build)\b',
    r'\b(pandas|numpy|sklearn|pytorch|tensorflow|keras|matplotlib|seaborn|plotly)\b',
    r'\b(import|def |class |async def)\b',
    r'\btraceback\b', r'\bsyntax error\b', r'\bgit\b', r'\bdocker\b',
    r'\b(pytest|unittest|jest)\b', r'\b(API|endpoint|router|server)\b',
    r'\b(SQL|query|dataframe|pipeline|etl)\b',
    r'\b(train|model\.fit|model\.predict|DataLoader)\b',
    r'\b(conda|pip install|requirements)\b',
]

DATA_SCIENCE_PATTERNS = [
    r'\b(dataset|dataframe|csv|parquet)\b',
    r'\b(EDA|exploratory data analysis|feature engineering|feature selection)\b',
    r'\b(cross.?validation|train.?test.?split|overfitting|underfitting)\b',
    r'\b(accuracy|precision|recall|f1|roc|auc|confusion matrix)\b',
    r'\b(hyperparameter|grid search|random search|optuna)\b',
    r'\b(neural network|deep learning|transformer|attention|embedding)\b',
    r'\b(time series|forecasting|arima|prophet|lstm)\b',
    r'\b(clustering|classification|regression problem)\b',
    r'\b(missing values|imputation|normalization|standardization)\b',
    r'\b(SHAP|feature importance|interpretability)\b',
]

FINANCE_PATTERNS = [
    r'\b(DCF|discounted cash flow|WACC|terminal value|free cash flow|FCF)\b',
    r'\b(EV/EBITDA|EV/Revenue|P/E ratio|enterprise value|market cap|equity value)\b',
    r'\b(investment banking|M&A|merger|acquisition|IPO|LBO|leveraged buyout)\b',
    r'\b(EBITDA|earnings per share|revenue growth|margin|working capital)\b',
    r'\b(equity research|pitch book|CIM|buy.?side|sell.?side|information memo)\b',
    r'\b(portfolio|diversification|Sharpe ratio|alpha|beta|factor exposure)\b',
    r'\b(10-K|10-Q|annual report|balance sheet|income statement|cash flow statement)\b',
    r'\b(yield curve|credit spread|duration|convexity|options pricing|Greeks)\b',
    r'\b(VaR|value at risk|drawdown|volatility|Sortino|information ratio)\b',
    r'\b(comparable company|comps|precedent transaction|trading multiple|valuation)\b',
]


def _make_decision(
    role: str,
    roles_pipeline: list[str],
    is_hybrid: bool,
    confidence: float,
    reasoning: str,
    detected_domains: list[str],
) -> RoutingDecision:
    """Build a RoutingDecision resolving roles to actual model strings."""
    cfg = get_config(role)
    pipeline_models = [get_config(r).model for r in roles_pipeline]
    return RoutingDecision(
        primary_model=cfg.model,
        primary_role=role,
        pipeline=pipeline_models,
        pipeline_roles=roles_pipeline,
        is_hybrid=is_hybrid,
        confidence=confidence,
        reasoning=reasoning,
        detected_domains=detected_domains,
        speed_mode=get_speed_mode().value,
    )


def classify_message(message: str, has_image: bool = False) -> RoutingDecision:
    msg_lower = message.lower()

    if has_image:
        has_math = any(re.search(p, msg_lower) for p in MATH_PATTERNS)
        has_code = any(re.search(p, msg_lower) for p in CODE_PATTERNS)
        if has_math or has_code:
            second = "math" if has_math else "code"
            return _make_decision(
                "vision", ["vision", second], True, 0.95,
                "Image with analytical content — extract via vision then analyze",
                ["vision"] + [second],
            )
        return _make_decision("vision", ["vision"], False, 0.99, "Image content", ["vision"])

    math_score = sum(1 for p in MATH_PATTERNS if re.search(p, msg_lower))
    code_score = sum(1 for p in CODE_PATTERNS if re.search(p, msg_lower))
    ds_score = sum(1 for p in DATA_SCIENCE_PATTERNS if re.search(p, msg_lower))
    finance_score = sum(1 for p in FINANCE_PATTERNS if re.search(p, msg_lower))

    is_ds_hybrid = ds_score >= 2 or (math_score >= 2 and code_score >= 2)

    if is_ds_hybrid:
        return _make_decision(
            "math", ["math", "code"], True, 0.85,
            f"Data science task: math theory ({math_score} signals) + code ({code_score} signals)",
            ["math", "code", "data_science"],
        )

    if math_score > code_score and math_score >= 2:
        return _make_decision(
            "math", ["math"], False, min(0.95, 0.6 + math_score * 0.05),
            f"Math/stats content ({math_score} signals)", ["math"],
        )

    if code_score >= 2 or ds_score >= 2:
        return _make_decision(
            "code", ["code"], False, min(0.95, 0.6 + code_score * 0.05),
            f"Code/data science content ({code_score} signals)", ["code"],
        )

    if math_score == 1:
        return _make_decision("math", ["math"], False, 0.7, "Possible math content", ["math"])

    if code_score == 1:
        return _make_decision("code", ["code"], False, 0.7, "Possible code content", ["code"])

    if finance_score >= 2:
        return _make_decision(
            "finance",
            ["finance"],
            False,
            min(0.95, 0.6 + finance_score * 0.05),
            f"Finance/investment content ({finance_score} signals)",
            ["finance"],
        )

    return _make_decision("chat", ["chat"], False, 0.8, "General conversation/reasoning", ["general"])


def get_compare_pipeline(routing: RoutingDecision) -> tuple[str, str, str]:
    """Choose which two models to compare and which judges, based on prompt context.

    Returns (role_a, role_b, judge_role). Pipeline is chosen from detected domains
    so comparison is relevant to the user's problem (e.g. math vs code for DS, chat vs math for reasoning).
    """
    domains = routing.detected_domains or []
    # Hybrid (math + code / data_science): compare specialist perspectives, chat synthesizes
    if routing.is_hybrid and "math" in domains and "code" in domains:
        return ("math", "code", "chat")
    if "data_science" in domains:
        return ("math", "code", "chat")
    # Vision: compare vision extraction vs chat interpretation
    if "vision" in domains:
        return ("vision", "chat", "chat")
    # Math-heavy: compare math specialist vs generalist
    if "math" in domains:
        return ("math", "chat", "chat")
    # Code-heavy: compare code specialist vs generalist
    if "code" in domains:
        return ("code", "chat", "chat")
    # Writing: compare writing-tuned vs default chat
    if "writing" in domains or routing.primary_role == "writing":
        return ("writing", "chat", "chat")
    # Finance: compare finance specialist vs math
    if "finance" in domains:
        return ("finance", "math", "chat")
    # General: diverse perspectives (reasoning vs concise)
    return ("chat", "math", "chat")


def get_model_config(mode: str) -> ModelConfig:
    return get_config(mode)


def get_current_model() -> str | None:
    return _current_model


def set_current_model(model: str) -> None:
    global _current_model
    _current_model = model
