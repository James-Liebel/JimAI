/** Persist which Agent Space markdown skills are active for Chat (Claude-style toggles). */

const SLUGS_KEY = 'jimai_chat_skill_slugs_v1';
const AUTO_KEY = 'jimai_chat_auto_skills_v1';

export const CHAT_SKILLS_CHANGED = 'jimai-chat-skills-changed';

export function loadChatSkillSlugs(): string[] {
    if (typeof window === 'undefined') return [];
    try {
        const raw = window.localStorage.getItem(SLUGS_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string' && x.trim().length > 0) : [];
    } catch {
        return [];
    }
}

export function saveChatSkillSlugs(slugs: string[]): void {
    if (typeof window === 'undefined') return;
    const unique = [...new Set(slugs.map((s) => s.trim()).filter(Boolean))];
    window.localStorage.setItem(SLUGS_KEY, JSON.stringify(unique));
    window.dispatchEvent(new CustomEvent(CHAT_SKILLS_CHANGED));
}

export function toggleChatSkillSlug(slug: string, enabled: boolean): void {
    const s = slug.trim();
    if (!s) return;
    const cur = loadChatSkillSlugs();
    if (enabled) {
        saveChatSkillSlugs([...cur, s]);
    } else {
        saveChatSkillSlugs(cur.filter((x) => x !== s));
    }
}

export function loadChatAutoSkills(): boolean {
    if (typeof window === 'undefined') return true;
    const v = window.localStorage.getItem(AUTO_KEY);
    if (v === '0' || v === 'false') return false;
    return true;
}

export function saveChatAutoSkills(on: boolean): void {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(AUTO_KEY, on ? '1' : '0');
    window.dispatchEvent(new CustomEvent(CHAT_SKILLS_CHANGED));
}
