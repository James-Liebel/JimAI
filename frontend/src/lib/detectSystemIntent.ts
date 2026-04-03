/**
 * Heuristic: user wants real host filesystem / OS actions (System panel), not chat+RAG only.
 */

const PATTERNS: RegExp[] = [
    /\b(my|the)\s+(documents|downloads|desktop|pictures|music|videos)\s+folder\b/i,
    /\b(in|under|from|on)\s+(my\s+)?(documents|downloads|desktop|pictures)\b/i,
    /\b(organize|sort|rename|move|copy|delete)\s+(all\s+)?(the\s+)?files\b/i,
    /\blist\s+(all\s+)?files\b.*\b(in|under|folder|directory)\b/i,
    /\b(find|search)\s+.*\b(files?|folders?)\b.*\b(on|in|under|drive|folder|directory|disk)\b/i,
    /\b(list|show|kill|terminate)\s+(running\s+)?process(es)?\b/i,
    /\b(taskkill|powershell\s+-|cmd\.exe|run\s+as\s+admin)\b/i,
    /\b(free|disk|drive)\s+space\b|\bhow\s+much\s+space\b/i,
    /\b(screenshot|screen\s+capture)\b.*\b(my\s+)?(screen|desktop|window)\b/i,
    /\b(open|show)\s+(in\s+)?(file\s+explorer|windows\s+explorer|finder)\b/i,
    /\bprogram\s+files\b|\bappdata\b|\brecycle\s+bin\b/i,
    /[a-zA-Z]:\\(?:Users|users|Program Files|Windows|Desktop|Documents)/i,
    /\\Users\\\w+\\/i,
    /\/Users\/\w+\//i,
    /(^|\s)~\/|\b\/home\/\w+\//i,
];

const MIN_LEN = 14;

export function detectLikelySystemTask(message: string): boolean {
    const t = message.trim();
    if (t.length < MIN_LEN) return false;
    if (PATTERNS.some((p) => p.test(t))) return true;
    // Windows drive letter at start or after space
    if (/\b[a-zA-Z]:\\/.test(t)) return true;
    return false;
}
