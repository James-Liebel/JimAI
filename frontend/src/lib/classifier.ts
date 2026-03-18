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

export function classifyLocally(text: string, hasImage: boolean): string {
    if (hasImage) return 'vision model';

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
