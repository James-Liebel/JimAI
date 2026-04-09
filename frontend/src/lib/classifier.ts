const MATH_SIGNALS = [
    /\bintegral\b/i, /\bderivative\b/i, /\bmatrix\b/i, /\beigenvalue\b/i,
    /\bproof\b/i, /\btheorem\b/i, /\bprobability\b/i, /\bhypothesis\b/i,
    /\bp-value\b/i, /\bregression\b/i, /\bsolve\b/i, /\bcalculate\b/i,
    /\bgradient\b/i, /\bbayes\b/i, /\bvariance\b/i, /\bstatistic\b/i,
    /\bt-test\b/i, /\banova\b/i, /\bconfidence interval\b/i,
    /\boptimiz/i, /\bconvex\b/i, /\blinear algebra\b/i, /\bcalculus\b/i,
    /\bsvd\b/i, /\bpca\b/i, /\bchi-square\b/i, /\bentropy\b/i,
    /\$\$.*\$\$/s, /\$[^$]+\$/,
];

const CODE_SIGNALS = [
    /\bwrite\b.{0,20}\b(code|function|class|script)\b/i,
    /\b(debug|fix|refactor|implement|build)\b/i,
    /\b(pandas|numpy|sklearn|pytorch|tensorflow)\b/i,
    /\b(import|def |class |async def)\b/, /\btraceback\b/i,
    /\b(pytest|unittest|jest)\b/i, /\b(API|endpoint|router)\b/i,
    /\b(SQL|query|dataframe|pipeline)\b/i,
];

const DS_SIGNALS = [
    /\b(dataset|dataframe|csv)\b/i, /\b(EDA|feature engineering)\b/i,
    /\b(cross.?validation|train.?test.?split)\b/i,
    /\b(accuracy|precision|recall|f1|roc|auc)\b/i,
    /\b(neural network|deep learning|transformer)\b/i,
    /\b(time series|forecasting|arima)\b/i,
    /\b(clustering|classification|regression problem)\b/i,
];

// Browser intent: user wants to open a URL / take a screenshot
const BROWSER_SIGNALS = [
    /\bscreenshot\b/i,
    /\bscreen\s*shot\b/i,
    /\b(open|visit|browse\s+to?|check\s+out?|look\s+at|pull\s+up|load|display)\b.{0,40}(https?:\/\/|www\.|\.(com|org|net|io|co|app|dev|ai))/i,
    /\b(open|visit|browse|check|go\s+to|navigate\s+to)\s+(https?:\/\/\S+|www\.\S+)/i,
    /https?:\/\/\S+/i,
    /\bwhat\s+does\s+\S+\.(com|org|net|io|co|app|dev|ai)\b/i,
    /\b(show\s+me\s+|open\s+up\s+)?(the\s+)?\S+\.(com|org|net|io|co|app|dev|ai)\b/i,
    /\bnavigat(e|ing)\s+to\b/i,
    /\bcapture\s+(a\s+)?(page|site|website|screenshot)\b/i,
];

// Builder intent: user wants to build / create an app or feature
const BUILDER_SIGNALS = [
    /\b(build|create|make|generate|scaffold|bootstrap)\b.{0,40}\b(app|application|website|site|tool|dashboard|ui|interface|widget|component|page|feature|project)\b/i,
    /\b(build\s+me|create\s+me|make\s+me|write\s+me)\b/i,
    /\b(new\s+)(app|project|website|tool|dashboard|api|service|script)\b/i,
    /\b(start|begin|kick\s+off)\b.{0,30}\b(project|app|application|website)\b/i,
    /\bfull.?stack\b/i,
    /\b(react|vue|svelte|nextjs|next\.js)\s+(app|project|component)\b/i,
];

export function classifyLocally(text: string, hasImage: boolean): string {
    if (hasImage) return 'vision model';

    // Browser intent check (high confidence — show routing hint)
    if (BROWSER_SIGNALS.some((p) => p.test(text))) return 'browser';

    // Builder intent check
    if (BUILDER_SIGNALS.some((p) => p.test(text))) return 'builder';

    const mathScore = MATH_SIGNALS.filter((p) => p.test(text)).length;
    const codeScore = CODE_SIGNALS.filter((p) => p.test(text)).length;
    const dsScore = DS_SIGNALS.filter((p) => p.test(text)).length;

    const isHybrid = dsScore >= 2 || (mathScore >= 2 && codeScore >= 2);
    if (isHybrid) return 'math + code pipeline';

    if (mathScore > codeScore && mathScore >= 2) return 'math model';
    if (codeScore >= 2 || dsScore >= 2) return 'code model';
    if (mathScore === 1) return 'math model';
    if (codeScore === 1) return 'code model';

    return 'chat model';
}
