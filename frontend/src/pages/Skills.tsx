import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Plus, RefreshCw, Save, Sparkles, Trash2, Wand2 } from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import * as agentApi from '../lib/agentSpaceApi';
import {
    loadChatAutoSkills,
    loadChatSkillSlugs,
    saveChatAutoSkills,
    saveChatSkillSlugs,
    toggleChatSkillSlug,
    CHAT_SKILLS_CHANGED,
} from '../lib/chatSkillSelection';
import { cn } from '../lib/utils';

const EMPTY_TEMPLATE = `---
name: New skill
description: One-line purpose
tags: custom, chat
complexity: 3
source: custom
---

# New skill

Short description of when to use this skill.

## Workflow
1. Step one
2. Step two
3. Verify outcome

## Quality gates
- Be specific and reversible.
`;

export default function Skills() {
    const [list, setList] = useState<agentApi.AgentSkillSummary[]>([]);
    const [loadingList, setLoadingList] = useState(true);
    const [listError, setListError] = useState('');
    const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
    const [detail, setDetail] = useState<agentApi.AgentSkillRecord | null>(null);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [rawMarkdown, setRawMarkdown] = useState('');
    const [saving, setSaving] = useState(false);
    const [search, setSearch] = useState('');
    const [chatSlugs, setChatSlugs] = useState<string[]>(() => loadChatSkillSlugs());
    const [autoChatSkills, setAutoChatSkills] = useState(() => loadChatAutoSkills());
    const [matchObjective, setMatchObjective] = useState('');
    const [matchBusy, setMatchBusy] = useState(false);
    const [matchSuggestions, setMatchSuggestions] = useState<agentApi.AgentSkillSummary[]>([]);
    const [autoAddObjective, setAutoAddObjective] = useState('');
    const [autoAddBusy, setAutoAddBusy] = useState(false);
    const [notice, setNotice] = useState('');

    const refreshList = useCallback(async () => {
        setLoadingList(true);
        setListError('');
        try {
            const rows = await agentApi.listSkills(500);
            setList(rows);
        } catch (e) {
            setListError(e instanceof Error ? e.message : 'Failed to load skills.');
        } finally {
            setLoadingList(false);
        }
    }, []);

    useEffect(() => {
        refreshList().catch(() => undefined);
    }, [refreshList]);

    useEffect(() => {
        const onSkills = () => setChatSlugs(loadChatSkillSlugs());
        window.addEventListener(CHAT_SKILLS_CHANGED, onSkills);
        window.addEventListener('storage', onSkills);
        return () => {
            window.removeEventListener(CHAT_SKILLS_CHANGED, onSkills);
            window.removeEventListener('storage', onSkills);
        };
    }, []);

    const loadDetail = useCallback(async (slug: string) => {
        setLoadingDetail(true);
        setNotice('');
        try {
            const row = await agentApi.getSkill(slug);
            setDetail(row);
            setRawMarkdown(row.raw_markdown || '');
            setSelectedSlug(slug);
        } catch (e) {
            setNotice(e instanceof Error ? e.message : 'Failed to load skill.');
            setDetail(null);
        } finally {
            setLoadingDetail(false);
        }
    }, []);

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return list;
        return list.filter(
            (s) =>
                s.slug.toLowerCase().includes(q) ||
                s.name.toLowerCase().includes(q) ||
                s.description.toLowerCase().includes(q) ||
                s.tags.some((t) => t.toLowerCase().includes(q)),
        );
    }, [list, search]);

    const newSkill = useCallback(() => {
        setSelectedSlug(null);
        setDetail(null);
        setRawMarkdown(EMPTY_TEMPLATE);
        setNotice('New skill — edit markdown, then Save. Slug is derived from the name in frontmatter unless you edit folder after save.');
    }, []);

    const handleSave = useCallback(async () => {
        const md = rawMarkdown.trim();
        if (!md) {
            setNotice('Nothing to save.');
            return;
        }
        setSaving(true);
        setNotice('');
        try {
            const frontName = md.match(/^name:\s*(.+)$/m)?.[1]?.trim() || 'Untitled skill';
            const frontDesc = md.match(/^description:\s*(.+)$/m)?.[1]?.trim() || '';
            const tagsLine = md.match(/^tags:\s*(.+)$/m)?.[1]?.trim() || '';
            const tags = tagsLine
                ? tagsLine.split(',').map((t) => t.trim()).filter(Boolean)
                : [];
            const cx = md.match(/^complexity:\s*(\d+)/m)?.[1];
            const complexity = cx ? Math.min(5, Math.max(1, parseInt(cx, 10) || 3)) : 3;
            const saved = await agentApi.upsertSkill({
                name: frontName,
                description: frontDesc,
                content: md,
                tags,
                complexity,
                source: detail?.source === 'system-default' ? 'custom' : detail?.source || 'custom',
                slug: selectedSlug || undefined,
            });
            setNotice(`Saved “${saved.name}”.`);
            await refreshList();
            setSelectedSlug(saved.slug);
            setDetail(saved);
            setRawMarkdown(saved.raw_markdown || md);
        } catch (e) {
            setNotice(e instanceof Error ? e.message : 'Save failed.');
        } finally {
            setSaving(false);
        }
    }, [detail?.source, rawMarkdown, refreshList, selectedSlug]);

    const handleDelete = useCallback(async () => {
        if (!selectedSlug || !detail) return;
        if (!window.confirm(`Delete skill “${detail.name}” (${selectedSlug})? This removes the folder on disk.`)) return;
        setSaving(true);
        setNotice('');
        try {
            await agentApi.deleteSkill(selectedSlug);
            const nextChat = loadChatSkillSlugs().filter((s) => s !== selectedSlug);
            saveChatSkillSlugs(nextChat);
            setNotice('Deleted.');
            setSelectedSlug(null);
            setDetail(null);
            setRawMarkdown('');
            await refreshList();
        } catch (e) {
            setNotice(e instanceof Error ? e.message : 'Delete failed.');
        } finally {
            setSaving(false);
        }
    }, [detail, refreshList, selectedSlug]);

    const runMatch = useCallback(async () => {
        const o = matchObjective.trim();
        if (o.length < 4) {
            setNotice('Enter at least a few words to match skills.');
            return;
        }
        setMatchBusy(true);
        setNotice('');
        try {
            const res = await agentApi.selectSkills({ objective: o, limit: 12, include_context: false });
            setMatchSuggestions(res.selected || []);
            setNotice(`Matched ${res.selected_count} skills — toggle “In chat” or open to edit.`);
        } catch (e) {
            setNotice(e instanceof Error ? e.message : 'Match failed.');
        } finally {
            setMatchBusy(false);
        }
    }, [matchObjective]);

    const runAutoAdd = useCallback(async () => {
        const o = autoAddObjective.trim();
        if (o.length < 4) {
            setNotice('Enter an objective to generate new skills.');
            return;
        }
        setAutoAddBusy(true);
        setNotice('');
        try {
            const res = await agentApi.autoAddSkills({ objective: o, max_new_skills: 3 });
            setNotice(`Created ${res.created_count} new skills. Refreshing list.`);
            await refreshList();
            setMatchSuggestions(res.selected || []);
        } catch (e) {
            setNotice(e instanceof Error ? e.message : 'Auto-add failed.');
        } finally {
            setAutoAddBusy(false);
        }
    }, [autoAddObjective, refreshList]);

    const installDefaults = useCallback(async () => {
        setSaving(true);
        setNotice('');
        try {
            const res = await agentApi.installDefaultSkills();
            setNotice(`Defaults ensured (${res.installed_count} entries).`);
            await refreshList();
        } catch (e) {
            setNotice(e instanceof Error ? e.message : 'Install failed.');
        } finally {
            setSaving(false);
        }
    }, [refreshList]);

    const chatSet = useMemo(() => new Set(chatSlugs), [chatSlugs]);

    return (
        <div className="flex h-full min-h-0 flex-col bg-surface-0">
            <PageHeader
                title="Skills"
                description="Markdown SKILL packs for Chat and agents — toggle skills for chat, edit full files, auto-create and rank from any objective."
            />
            <div className="min-h-0 flex flex-1 flex-col gap-3 overflow-hidden p-4 md:flex-row md:gap-4">
                <aside className="flex w-full shrink-0 flex-col border border-surface-5 bg-surface-1 md:w-[min(100%,320px)] md:rounded-xl">
                    <div className="border-b border-surface-5 p-3">
                        <div className="flex items-center gap-2">
                            <BookOpen className="h-4 w-4 text-accent" aria-hidden />
                            <span className="text-sm font-semibold text-text-primary">Library</span>
                        </div>
                        <p className="mt-1 text-[11px] text-text-muted">
                            <Link to="/chat" className="text-accent hover:underline">
                                Chat
                            </Link>{' '}
                            uses checked skills + optional auto-match each message.
                        </p>
                        <input
                            type="search"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Filter…"
                            className="mt-2 w-full rounded-lg border border-surface-5 bg-surface-0 px-2.5 py-1.5 text-sm text-text-primary outline-none focus:border-accent/50"
                        />
                        <label className="mt-2 flex cursor-pointer items-center gap-2 text-[12px] text-text-secondary">
                            <input
                                type="checkbox"
                                className="rounded border-surface-5"
                                checked={autoChatSkills}
                                onChange={(e) => {
                                    saveChatAutoSkills(e.target.checked);
                                    setAutoChatSkills(e.target.checked);
                                }}
                            />
                            Auto-match skills to each chat message
                        </label>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                            <button
                                type="button"
                                onClick={() => refreshList().catch(() => undefined)}
                                className="inline-flex items-center gap-1 rounded-lg border border-surface-5 px-2 py-1 text-[11px] text-text-secondary hover:bg-surface-2"
                            >
                                <RefreshCw className={cn('h-3 w-3', loadingList && 'animate-spin')} />
                                Refresh
                            </button>
                            <button
                                type="button"
                                onClick={newSkill}
                                className="inline-flex items-center gap-1 rounded-lg border border-accent/40 px-2 py-1 text-[11px] text-accent hover:bg-accent/10"
                            >
                                <Plus className="h-3 w-3" />
                                New
                            </button>
                            <button
                                type="button"
                                onClick={() => installDefaults().catch(() => undefined)}
                                className="inline-flex items-center gap-1 rounded-lg border border-surface-5 px-2 py-1 text-[11px] text-text-secondary hover:bg-surface-2"
                            >
                                <Sparkles className="h-3 w-3" />
                                Install defaults
                            </button>
                        </div>
                    </div>
                    <div className="min-h-0 flex-1 overflow-y-auto p-2">
                        {listError ? <p className="px-2 py-2 text-xs text-accent-red">{listError}</p> : null}
                        {loadingList && !list.length ? (
                            <p className="px-2 py-4 text-xs text-text-muted">Loading…</p>
                        ) : (
                            <ul className="space-y-1">
                                {filtered.map((s) => (
                                    <li key={s.slug}>
                                        <div
                                            className={cn(
                                                'rounded-lg border px-2 py-1.5 transition-colors',
                                                selectedSlug === s.slug
                                                    ? 'border-accent/40 bg-accent/10'
                                                    : 'border-transparent hover:bg-surface-2',
                                            )}
                                        >
                                            <div className="flex items-start gap-2">
                                                <input
                                                    type="checkbox"
                                                    title="Use in Chat"
                                                    checked={chatSet.has(s.slug)}
                                                    onChange={(e) => {
                                                        toggleChatSkillSlug(s.slug, e.target.checked);
                                                        setChatSlugs(loadChatSkillSlugs());
                                                    }}
                                                    className="mt-0.5 rounded border-surface-5"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => loadDetail(s.slug).catch(() => undefined)}
                                                    className="min-w-0 flex-1 text-left"
                                                >
                                                    <p className="truncate text-xs font-medium text-text-primary">{s.name}</p>
                                                    <p className="truncate text-[10px] text-text-muted">{s.slug}</p>
                                                </button>
                                            </div>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                    <div className="border-t border-surface-5 p-3">
                        <p className="text-[10px] font-medium uppercase tracking-wide text-text-muted">Auto-create</p>
                        <textarea
                            rows={2}
                            value={autoAddObjective}
                            onChange={(e) => setAutoAddObjective(e.target.value)}
                            placeholder="Objective → new markdown skills (LLM + heuristics)"
                            className="mt-1 w-full rounded-lg border border-surface-5 bg-surface-0 px-2 py-1.5 text-[11px] text-text-primary outline-none focus:border-accent/50"
                        />
                        <button
                            type="button"
                            disabled={autoAddBusy}
                            onClick={() => runAutoAdd().catch(() => undefined)}
                            className="mt-1 inline-flex w-full items-center justify-center gap-1 rounded-lg bg-surface-2 py-1.5 text-[11px] font-medium text-text-primary hover:bg-surface-3 disabled:opacity-50"
                        >
                            <Wand2 className="h-3 w-3" />
                            {autoAddBusy ? 'Working…' : 'Generate & add skills'}
                        </button>
                    </div>
                </aside>

                <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border border-surface-5 bg-surface-1 md:rounded-xl">
                    <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-surface-5 px-3 py-2">
                        <div className="min-w-0">
                            <h2 className="truncate text-sm font-semibold text-text-primary">
                                {detail?.name || (selectedSlug ? selectedSlug : 'New skill')}
                            </h2>
                            <p className="text-[11px] text-text-muted">
                                Edit full markdown (frontmatter + body). Saved to Agent Space <code className="font-mono text-[10px]">SKILL.md</code>.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                            <button
                                type="button"
                                disabled={saving || !rawMarkdown.trim()}
                                onClick={() => handleSave().catch(() => undefined)}
                                className="inline-flex items-center gap-1 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent/90 disabled:opacity-50"
                            >
                                <Save className="h-3.5 w-3.5" />
                                Save
                            </button>
                            <button
                                type="button"
                                disabled={saving || !selectedSlug}
                                onClick={() => handleDelete().catch(() => undefined)}
                                className="inline-flex items-center gap-1 rounded-lg border border-accent-red/40 px-3 py-1.5 text-xs text-accent-red hover:bg-accent-red/10 disabled:opacity-40"
                            >
                                <Trash2 className="h-3.5 w-3.5" />
                                Delete
                            </button>
                        </div>
                    </div>
                    {notice ? (
                        <div className="shrink-0 border-b border-surface-5 bg-surface-0 px-3 py-2 text-[11px] text-text-secondary">{notice}</div>
                    ) : null}
                    <div className="min-h-0 flex flex-1 flex-col gap-3 overflow-hidden p-3 md:flex-row">
                        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                            <label className="text-[10px] font-medium uppercase text-text-muted">Markdown</label>
                            {loadingDetail ? (
                                <p className="mt-2 text-xs text-text-muted">Loading…</p>
                            ) : (
                                <textarea
                                    value={rawMarkdown}
                                    onChange={(e) => setRawMarkdown(e.target.value)}
                                    spellCheck={false}
                                    className="mt-1 min-h-[240px] flex-1 resize-none rounded-lg border border-surface-5 bg-surface-0 p-3 font-mono text-[12px] leading-relaxed text-text-primary outline-none focus:border-accent/50 md:min-h-0"
                                    placeholder="---\nname: …\n---\n\n# …"
                                />
                            )}
                        </div>
                        <div className="flex w-full shrink-0 flex-col border-t border-surface-5 pt-3 md:w-56 md:border-l md:border-t-0 md:pl-3 md:pt-0">
                            <p className="text-[10px] font-medium uppercase text-text-muted">Match for chat</p>
                            <textarea
                                rows={3}
                                value={matchObjective}
                                onChange={(e) => setMatchObjective(e.target.value)}
                                placeholder="Paste a question or goal…"
                                className="mt-1 w-full rounded-lg border border-surface-5 bg-surface-0 px-2 py-1.5 text-[11px] text-text-primary outline-none focus:border-accent/50"
                            />
                            <button
                                type="button"
                                disabled={matchBusy}
                                onClick={() => runMatch().catch(() => undefined)}
                                className="mt-1 rounded-lg border border-surface-5 py-1.5 text-[11px] font-medium text-text-secondary hover:bg-surface-2 disabled:opacity-50"
                            >
                                {matchBusy ? 'Matching…' : 'Rank skills'}
                            </button>
                            {matchSuggestions.length > 0 ? (
                                <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto text-[11px]">
                                    {matchSuggestions.map((s) => (
                                        <li key={s.slug} className="flex items-center justify-between gap-1 rounded border border-surface-5 bg-surface-0 px-1.5 py-1">
                                            <span className="min-w-0 truncate">{s.name}</span>
                                            <button
                                                type="button"
                                                className="shrink-0 text-accent hover:underline"
                                                onClick={() => {
                                                    toggleChatSkillSlug(s.slug, true);
                                                    setChatSlugs(loadChatSkillSlugs());
                                                }}
                                            >
                                                +Chat
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            ) : null}
                            <p className="mt-3 text-[10px] text-text-muted">
                                Active in chat: <span className="font-mono text-text-secondary">{chatSlugs.length}</span>
                            </p>
                            {chatSlugs.length > 0 ? (
                                <button
                                    type="button"
                                    className="mt-1 text-[11px] text-accent hover:underline"
                                    onClick={() => {
                                        saveChatSkillSlugs([]);
                                        setChatSlugs([]);
                                    }}
                                >
                                    Clear all chat skills
                                </button>
                            ) : null}
                        </div>
                    </div>
                </main>
            </div>
        </div>
    );
}
