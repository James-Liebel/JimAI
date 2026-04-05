import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
    Bot,
    Plus,
    Send,
    Trash2,
    MoreVertical,
    Sparkles,
    Users,
    Loader2,
    X,
    ChevronUp,
    ChevronDown,
} from 'lucide-react';
import { cn } from '../lib/utils';
import * as api from '../lib/workspaceAgentsApi';
import type { WorkspaceAgent, WorkspaceTeam, SkillFileMeta } from '../lib/workspaceAgentsApi';

const ROLE_DEFAULTS: Record<string, string> = {
    Planner:
        'You are a strategic planning agent. Your job is to decompose complex tasks into clear, ordered steps. You think carefully before acting, consider dependencies and risks, and always produce a structured plan before any execution begins.',
    'Code Agent':
        'You are an expert software engineer. You write clean, well-tested, idiomatic code. You read the existing codebase carefully before making changes, prefer small focused edits over rewrites, and always explain your reasoning.',
    Researcher:
        'You are a rigorous research agent. You search multiple sources, cross-reference claims, and synthesize findings into clear grounded summaries with source attribution. You never confabulate.',
    Verifier:
        'You are a critical reviewer. Your job is to check the work of other agents for errors, inconsistencies, missing edge cases, and quality issues. You are constructive but exacting.',
    Orchestrator:
        'You are the lead orchestrator. You coordinate a team of specialized agents, delegate tasks based on each agent skills and role, monitor progress, and synthesize outputs into final deliverables.',
};

type ChatMsg = { role: 'user' | 'assistant'; content: string };

export default function Agents() {
    const [agents, setAgents] = useState<WorkspaceAgent[]>([]);
    const [teams, setTeams] = useState<WorkspaceTeam[]>([]);
    const [models, setModels] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
    const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
    const [agentDetail, setAgentDetail] = useState<WorkspaceAgent | null>(null);
    const [skills, setSkills] = useState<SkillFileMeta[]>([]);
    const [skillFilter, setSkillFilter] = useState('');
    const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
    const [chatInput, setChatInput] = useState('');
    const [streaming, setStreaming] = useState(false);
    const [teamTask, setTeamTask] = useState('');
    const [teamLog, setTeamLog] = useState<string>('');
    const [teamRunning, setTeamRunning] = useState(false);
    const [menuOpen, setMenuOpen] = useState<string | null>(null);
    const [modal, setModal] = useState<
        | null
        | { type: 'newAgent' }
        | { type: 'newTeam' }
        | { type: 'generateSkill' }
        | { type: 'editSkill'; slug: string; content: string }
        | { type: 'previewSkill'; markdown: string; slug: string }
    >(null);
    const [newAgentForm, setNewAgentForm] = useState({
        name: '',
        role: 'Planner',
        model: 'qwen3:8b',
        avatar: '🤖',
    });
    const [newTeamForm, setNewTeamForm] = useState({
        name: '',
        description: '',
        workflow: 'orchestrated' as WorkspaceTeam['workflow'],
        agent_ids: [] as string[],
    });
    const [genSkillForm, setGenSkillForm] = useState({
        name: '',
        description: '',
        example: '',
    });
    const chatEndRef = useRef<HTMLDivElement>(null);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const [a, t, m] = await Promise.all([
                api.listWorkspaceAgents(),
                api.listTeams(),
                api.listOllamaModels().catch(() => []),
            ]);
            setAgents(a);
            setTeams(t);
            setModels(m.length ? m : ['qwen3:8b', 'qwen2.5-coder:14b', 'deepseek-r1:14b']);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void refresh();
    }, [refresh]);

    useEffect(() => {
        if (!selectedAgentId || selectedTeamId) return;
        void (async () => {
            try {
                const d = await api.getWorkspaceAgent(selectedAgentId);
                setAgentDetail(d);
                setSkills(d.skill_files || []);
            } catch {
                setAgentDetail(null);
                setSkills([]);
            }
        })();
    }, [selectedAgentId, selectedTeamId]);

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatMessages, streaming]);

    const selectAgent = (id: string) => {
        setSelectedTeamId(null);
        setSelectedAgentId(id);
        setChatMessages([]);
        setTeamLog('');
    };

    const selectTeam = (id: string) => {
        setSelectedAgentId(null);
        setAgentDetail(null);
        setSkills([]);
        setSelectedTeamId(id);
        setChatMessages([]);
        setTeamLog('');
    };

    const saveAgentFields = async (patch: Partial<WorkspaceAgent>) => {
        if (!agentDetail) return;
        const updated = await api.updateWorkspaceAgent(agentDetail.id, patch);
        setAgentDetail(updated);
        setAgents((prev) => prev.map((x) => (x.id === updated.id ? { ...x, ...updated } : x)));
    };

    const sendChat = async () => {
        if (!agentDetail || !chatInput.trim() || streaming) return;
        const userMsg = chatInput.trim();
        setChatInput('');
        setChatMessages((m) => [...m, { role: 'user', content: userMsg }, { role: 'assistant', content: '' }]);
        setStreaming(true);
        const history = chatMessages.map((c) => ({ role: c.role, content: c.content }));
        try {
            await api.streamAgentChat(
                agentDetail.id,
                userMsg,
                history,
                (text) => {
                    setChatMessages((m) => {
                        const copy = [...m];
                        const last = copy[copy.length - 1];
                        if (last?.role === 'assistant') {
                            copy[copy.length - 1] = { ...last, content: last.content + text };
                        }
                        return copy;
                    });
                },
                () => setStreaming(false),
            );
        } catch (e) {
            setChatMessages((m) => {
                const copy = [...m];
                const last = copy[copy.length - 1];
                if (last?.role === 'assistant') {
                    copy[copy.length - 1] = {
                        ...last,
                        content: last.content + `\n\n**Error:** ${e instanceof Error ? e.message : e}`,
                    };
                }
                return copy;
            });
            setStreaming(false);
        }
    };

    const runTeam = async () => {
        if (!selectedTeamId || !teamTask.trim() || teamRunning) return;
        setTeamRunning(true);
        setTeamLog('');
        try {
            await api.streamTeamRun(selectedTeamId, teamTask.trim(), (ev) => {
                if (ev.type === 'chunk' && typeof ev.text === 'string') {
                    setTeamLog((l) => l + ev.text);
                } else if (ev.type === 'log' && typeof ev.message === 'string') {
                    setTeamLog((l) => l + `\n[log] ${ev.message}\n`);
                } else if (ev.type === 'agent_done') {
                    setTeamLog((l) => l + `\n--- agent ${String(ev.agent)} done ---\n`);
                } else if (ev.type === 'error' && typeof ev.message === 'string') {
                    setTeamLog((l) => l + `\n[error] ${ev.message}\n`);
                } else if (ev.type === 'done') {
                    const fin = typeof ev.final === 'string' ? ev.final : '';
                    if (fin) setTeamLog((l) => l + `\n\n${fin}`);
                    else setTeamLog((l) => l + '\n--- run complete ---\n');
                }
            });
        } catch (e) {
            setTeamLog((l) => l + `\nError: ${e instanceof Error ? e.message : e}`);
        } finally {
            setTeamRunning(false);
        }
    };

    const filteredSkills = skills.filter(
        (s) =>
            !skillFilter ||
            s.name.toLowerCase().includes(skillFilter.toLowerCase()) ||
            s.preview.toLowerCase().includes(skillFilter.toLowerCase()),
    );

    const onKeyDownChat = (e: React.KeyboardEvent) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault();
            void sendChat();
        }
    };

    return (
        <div className="flex flex-col h-full min-h-0 bg-surface-0 text-text-primary">
            <header className="flex-shrink-0 border-b border-surface-5 bg-surface-1 px-5 py-3 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2.5">
                    <Bot className="w-4 h-4 text-accent" />
                    <h1 className="text-base font-semibold tracking-tight text-text-primary">Agents</h1>
                    <span className="hidden text-xs text-text-muted sm:inline">
                        Personas, skills &amp; teams — local Ollama
                    </span>
                </div>
                <Link
                    to="/agent-studio"
                    className="rounded-btn border border-surface-4 px-2.5 py-1.5 text-xs font-medium text-text-muted transition-colors hover:border-surface-3 hover:bg-surface-3 hover:text-text-secondary"
                >
                    Agent Studio (flow)
                </Link>
            </header>

            {loading ? (
                <div className="flex-1 flex items-center justify-center text-text-muted">
                    <Loader2 className="w-8 h-8 animate-spin" />
                </div>
            ) : (
                <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-0 border-t border-surface-4">
                    {/* Left roster */}
                    <aside className="lg:col-span-3 border-r border-surface-5 flex flex-col min-h-0 overflow-hidden bg-surface-1">
                        <div className="p-3 border-b border-surface-5">
                            <button
                                type="button"
                                onClick={() => {
                                    setModal({ type: 'newAgent' });
                                    setNewAgentForm((f) => ({
                                        ...f,
                                        model: models[0] || 'qwen3:8b',
                                    }));
                                }}
                                className="w-full flex items-center justify-center gap-1.5 py-2 rounded-btn bg-accent text-white text-xs font-medium transition-colors hover:bg-accent-hover"
                            >
                                <Plus className="w-3.5 h-3.5" /> New Agent
                            </button>
                        </div>

                        {/* Agents section */}
                        <div className="flex-1 overflow-y-auto py-2">
                            <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                                Agents
                            </p>
                            {agents.length === 0 ? (
                                <p className="px-3 py-3 text-xs text-text-muted">No agents yet — create one above.</p>
                            ) : (
                                <div className="space-y-px px-1.5">
                                    {agents.map((a) => (
                                        <div
                                            key={a.id}
                                            className={cn(
                                                'group relative rounded-btn border px-2.5 py-2 flex items-center gap-2.5 cursor-pointer transition-colors duration-150',
                                                selectedAgentId === a.id && !selectedTeamId
                                                    ? 'border-accent/40 bg-accent/8'
                                                    : 'border-transparent hover:border-surface-4 hover:bg-surface-2',
                                            )}
                                            onClick={() => selectAgent(a.id)}
                                        >
                                            <span className="text-base leading-none shrink-0">{a.avatar}</span>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm font-medium text-text-primary truncate leading-tight">{a.name}</div>
                                                <div className="text-[11px] text-text-muted truncate mt-0.5">{a.role}</div>
                                                <span className="mt-1 inline-block rounded-badge border border-surface-4 bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-text-muted">
                                                    {a.model}
                                                </span>
                                            </div>
                                            <div className="flex shrink-0 items-center gap-1.5">
                                                <span
                                                    className={cn(
                                                        'h-1.5 w-1.5 rounded-full',
                                                        a.status === 'running'
                                                            ? 'bg-accent-amber'
                                                            : a.status === 'error'
                                                              ? 'bg-accent-red'
                                                              : 'bg-accent-green',
                                                    )}
                                                />
                                                <button
                                                    type="button"
                                                    className="rounded p-1 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-surface-3"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setMenuOpen(menuOpen === a.id ? null : a.id);
                                                    }}
                                                >
                                                    <MoreVertical className="w-3.5 h-3.5 text-text-muted" />
                                                </button>
                                            </div>
                                            {menuOpen === a.id && (
                                                <div
                                                    className="absolute right-1 top-10 z-20 min-w-[130px] rounded-btn border border-surface-4 bg-surface-2 py-1 text-xs shadow-lg"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    <button
                                                        type="button"
                                                        className="w-full text-left px-3 py-1.5 text-accent-red transition-colors hover:bg-surface-3"
                                                        onClick={async () => {
                                                            setMenuOpen(null);
                                                            if (!confirm(`Delete agent "${a.name}"?`)) return;
                                                            await api.deleteWorkspaceAgent(a.id);
                                                            if (selectedAgentId === a.id) {
                                                                setSelectedAgentId(null);
                                                                setAgentDetail(null);
                                                            }
                                                            void refresh();
                                                        }}
                                                    >
                                                        Delete agent
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Teams section */}
                        <div className="border-t border-surface-5 p-3 space-y-2">
                            <p className="px-0.5 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                                Teams
                            </p>
                            <button
                                type="button"
                                onClick={() => {
                                    setModal({ type: 'newTeam' });
                                    setNewTeamForm({
                                        name: '',
                                        description: '',
                                        workflow: 'orchestrated',
                                        agent_ids: agents[0] ? [agents[0].id] : [],
                                    });
                                }}
                                className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-btn border border-surface-4 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-3"
                            >
                                <Users className="w-3.5 h-3.5" /> New Team
                            </button>
                            {teams.map((t) => (
                                <button
                                    key={t.id}
                                    type="button"
                                    onClick={() => selectTeam(t.id)}
                                    className={cn(
                                        'w-full text-left rounded-btn border px-2.5 py-2 text-sm transition-colors',
                                        selectedTeamId === t.id
                                            ? 'border-accent/40 bg-accent/8'
                                            : 'border-surface-4 hover:bg-surface-3',
                                    )}
                                >
                                    <div className="font-medium text-text-primary truncate">{t.name}</div>
                                    <div className="mt-0.5 text-[10px] uppercase tracking-wide text-text-muted">{t.workflow}</div>
                                </button>
                            ))}
                        </div>
                    </aside>

                    {/* Center */}
                    <main className="lg:col-span-6 flex flex-col min-h-0 border-r border-surface-5">
                        {selectedTeamId ? (
                            <TeamCenter
                                team={teams.find((t) => t.id === selectedTeamId)}
                                agents={agents}
                                teamTask={teamTask}
                                setTeamTask={setTeamTask}
                                teamLog={teamLog}
                                teamRunning={teamRunning}
                                onRun={() => void runTeam()}
                            />
                        ) : agentDetail ? (
                            <>
                                <div className="border-b border-surface-5 p-4 space-y-3 max-h-[45vh] overflow-y-auto">
                                    <input
                                        className="w-full border-b border-transparent bg-transparent pb-1 text-lg font-semibold text-text-primary outline-none focus:border-accent transition-colors"
                                        value={agentDetail.name}
                                        onChange={(e) => setAgentDetail({ ...agentDetail, name: e.target.value })}
                                        onBlur={() => void saveAgentFields({ name: agentDetail.name })}
                                    />
                                    <div className="grid grid-cols-2 gap-2">
                                        <input
                                            className="rounded-btn border border-surface-4 bg-surface-2 px-2.5 py-1.5 text-sm text-text-primary"
                                            value={agentDetail.role}
                                            onChange={(e) => setAgentDetail({ ...agentDetail, role: e.target.value })}
                                            onBlur={() => void saveAgentFields({ role: agentDetail.role })}
                                            placeholder="Role"
                                        />
                                        <select
                                            className="rounded-btn border border-surface-4 bg-surface-2 px-2.5 py-1.5 text-sm text-text-primary"
                                            value={agentDetail.model}
                                            onChange={(e) => {
                                                const m = e.target.value;
                                                setAgentDetail({ ...agentDetail, model: m });
                                                void saveAgentFields({ model: m });
                                            }}
                                        >
                                            {models.map((m) => (
                                                <option key={m} value={m}>{m}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <textarea
                                        className="w-full min-h-[100px] rounded-btn border border-surface-4 bg-surface-0 p-2.5 font-mono text-xs text-text-primary resize-y"
                                        placeholder="System prompt / persona…"
                                        value={agentDetail.system_prompt}
                                        onChange={(e) => setAgentDetail({ ...agentDetail, system_prompt: e.target.value })}
                                        onBlur={() => void saveAgentFields({ system_prompt: agentDetail.system_prompt })}
                                    />
                                    <div className="flex flex-wrap items-center gap-2 text-xs">
                                        <button
                                            type="button"
                                            className="rounded-btn border border-surface-4 px-2.5 py-1 text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary"
                                            onClick={() => setChatMessages([])}
                                        >
                                            Clear chat
                                        </button>
                                        <button
                                            type="button"
                                            className="rounded-btn border border-surface-4 px-2.5 py-1 text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary"
                                            onClick={() => {
                                                const blob = new Blob([JSON.stringify(agentDetail, null, 2)], { type: 'application/json' });
                                                const u = URL.createObjectURL(blob);
                                                const a = document.createElement('a');
                                                a.href = u;
                                                a.download = `${agentDetail.slug}.json`;
                                                a.click();
                                                URL.revokeObjectURL(u);
                                            }}
                                        >
                                            Export
                                        </button>
                                        <label className="flex cursor-pointer items-center gap-1.5 text-text-secondary">
                                            <input
                                                type="checkbox"
                                                checked={agentDetail.memory_enabled}
                                                onChange={(e) => {
                                                    const v = e.target.checked;
                                                    setAgentDetail({ ...agentDetail, memory_enabled: v });
                                                    void saveAgentFields({ memory_enabled: v });
                                                }}
                                                className="h-3 w-3"
                                            />
                                            Memory
                                        </label>
                                    </div>
                                </div>
                                <div className="flex flex-1 flex-col min-h-0 p-4">
                                    <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">Test chat</p>
                                    <div className="flex-1 overflow-y-auto space-y-2 mb-3 rounded-btn border border-surface-4 bg-surface-0 p-2">
                                        {chatMessages.map((msg, i) => (
                                            <div
                                                key={i}
                                                className={cn(
                                                    'rounded-btn px-3 py-2 text-sm',
                                                    msg.role === 'user'
                                                        ? 'ml-6 bg-accent/15 text-text-primary'
                                                        : 'mr-6 bg-surface-2 text-text-primary',
                                                )}
                                            >
                                                <span className="mb-0.5 block font-mono text-[10px] uppercase tracking-wide text-text-muted">
                                                    {msg.role}
                                                </span>
                                                <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                                            </div>
                                        ))}
                                        {streaming && (
                                            <div className="flex items-center gap-1.5 px-2 text-xs text-text-muted">
                                                <span className="inline-flex gap-0.5">
                                                    <span className="h-1 w-1 rounded-full bg-accent animate-pulse" />
                                                    <span className="h-1 w-1 rounded-full bg-accent animate-pulse delay-75" />
                                                    <span className="h-1 w-1 rounded-full bg-accent animate-pulse delay-150" />
                                                </span>
                                                Generating…
                                            </div>
                                        )}
                                        <div ref={chatEndRef} />
                                    </div>
                                    <div className="flex gap-2">
                                        <textarea
                                            className="flex-1 min-h-[44px] max-h-32 rounded-btn border border-surface-4 bg-surface-2 px-3 py-2 text-sm text-text-primary resize-y"
                                            placeholder="Message… (Ctrl+Enter to send)"
                                            value={chatInput}
                                            onChange={(e) => setChatInput(e.target.value)}
                                            onKeyDown={onKeyDownChat}
                                        />
                                        <button
                                            type="button"
                                            disabled={streaming}
                                            onClick={() => void sendChat()}
                                            className="rounded-btn bg-accent px-4 text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
                                        >
                                            <Send className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-text-muted">
                                <Bot className="mb-4 h-10 w-10 opacity-25" />
                                <p className="text-sm font-medium text-text-secondary">Select an agent or team</p>
                                <p className="mt-1 text-xs text-text-muted">Choose from the left panel to begin</p>
                            </div>
                        )}
                    </main>

                    {/* Skills */}
                    <aside className="lg:col-span-3 flex flex-col min-h-0 bg-surface-1">
                        <div className="border-b border-surface-5 p-3">
                            <p className="mb-2.5 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                                Skills
                            </p>
                            {agentDetail ? (
                                <div className="space-y-2">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setGenSkillForm({ name: '', description: '', example: '' });
                                            setModal({ type: 'generateSkill' });
                                        }}
                                        className="w-full flex items-center justify-center gap-1.5 rounded-btn border border-accent/40 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
                                    >
                                        <Sparkles className="w-3.5 h-3.5" /> Generate skill
                                    </button>
                                    <input
                                        type="search"
                                        placeholder="Filter skills…"
                                        className="w-full rounded-btn border border-surface-4 bg-surface-2 px-2.5 py-1.5 text-xs text-text-primary"
                                        value={skillFilter}
                                        onChange={(e) => setSkillFilter(e.target.value)}
                                    />
                                </div>
                            ) : null}
                        </div>
                        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
                            {!agentDetail ? (
                                <div className="flex flex-col items-center justify-center h-full min-h-[200px] p-6 text-center">
                                    <Sparkles className="mb-3 h-8 w-8 opacity-20 text-text-muted" />
                                    <p className="text-sm font-medium text-text-secondary">No agent selected</p>
                                    <p className="mt-1 text-xs text-text-muted">
                                        Select an agent from the left to view and manage its skills.
                                    </p>
                                </div>
                            ) : filteredSkills.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-8 text-center">
                                    <p className="text-xs text-text-muted">
                                        {skillFilter ? 'No skills match filter.' : 'No skills yet — generate one above.'}
                                    </p>
                                </div>
                            ) : (
                                filteredSkills.map((s) => (
                                    <div
                                        key={s.slug}
                                        className="rounded-btn border border-surface-4 bg-surface-0 p-2.5 text-xs"
                                    >
                                        <div className="font-medium text-text-primary">{s.name}</div>
                                        <p className="mt-1 line-clamp-2 text-text-muted">{s.preview}</p>
                                        <p className="mt-1 font-mono text-[10px] text-text-muted">{s.modified_at}</p>
                                        <div className="mt-2 flex gap-1">
                                            <button
                                                type="button"
                                                className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-0.5 text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary"
                                                onClick={async () => {
                                                    const content = await api.getSkillRaw(agentDetail.id, s.slug);
                                                    setModal({ type: 'editSkill', slug: s.slug, content });
                                                }}
                                            >
                                                Edit
                                            </button>
                                            <button
                                                type="button"
                                                className="rounded-badge border border-accent-red/30 px-2 py-0.5 text-accent-red transition-colors hover:bg-accent-red/10"
                                                onClick={async () => {
                                                    if (!confirm(`Delete skill ${s.slug}?`)) return;
                                                    await api.deleteSkillFile(agentDetail.id, s.slug);
                                                    const d = await api.getWorkspaceAgent(agentDetail.id);
                                                    setSkills(d.skill_files || []);
                                                }}
                                            >
                                                <Trash2 className="w-3 h-3" />
                                            </button>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </aside>
                </div>
            )}

            {/* Modals */}
            {modal?.type === 'newAgent' && (
                <Modal onClose={() => setModal(null)} title="New agent">
                    <div className="space-y-3">
                        <div>
                            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-text-muted">Name</label>
                            <input
                                className="w-full rounded-btn border border-surface-4 bg-surface-2 px-3 py-2 text-sm text-text-primary"
                                value={newAgentForm.name}
                                onChange={(e) => setNewAgentForm({ ...newAgentForm, name: e.target.value })}
                            />
                        </div>
                        <div>
                            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-text-muted">Role template</label>
                            <select
                                className="w-full rounded-btn border border-surface-4 bg-surface-2 px-3 py-2 text-sm text-text-primary"
                                value={newAgentForm.role}
                                onChange={(e) => setNewAgentForm({ ...newAgentForm, role: e.target.value })}
                            >
                                {Object.keys(ROLE_DEFAULTS).map((r) => (
                                    <option key={r} value={r}>{r}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-text-muted">Model</label>
                            <select
                                className="w-full rounded-btn border border-surface-4 bg-surface-2 px-3 py-2 text-sm text-text-primary"
                                value={newAgentForm.model}
                                onChange={(e) => setNewAgentForm({ ...newAgentForm, model: e.target.value })}
                            >
                                {models.map((m) => (
                                    <option key={m} value={m}>{m}</option>
                                ))}
                            </select>
                        </div>
                        <button
                            type="button"
                            className="w-full rounded-btn bg-accent py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
                            onClick={async () => {
                                const sys = ROLE_DEFAULTS[newAgentForm.role] || '';
                                const a = await api.createWorkspaceAgent({
                                    name: newAgentForm.name || 'Unnamed',
                                    role: newAgentForm.role,
                                    model: newAgentForm.model,
                                    avatar: newAgentForm.avatar,
                                    system_prompt: sys,
                                });
                                setModal(null);
                                void refresh();
                                selectAgent(a.id);
                            }}
                        >
                            Create agent
                        </button>
                    </div>
                </Modal>
            )}
            {modal?.type === 'newTeam' && (
                <Modal onClose={() => setModal(null)} title="New team">
                    <input
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        placeholder="Team name"
                        value={newTeamForm.name}
                        onChange={(e) => setNewTeamForm({ ...newTeamForm, name: e.target.value })}
                    />
                    <textarea
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        placeholder="Description"
                        value={newTeamForm.description}
                        onChange={(e) => setNewTeamForm({ ...newTeamForm, description: e.target.value })}
                    />
                    <select
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        value={newTeamForm.workflow}
                        onChange={(e) =>
                            setNewTeamForm({
                                ...newTeamForm,
                                workflow: e.target.value as WorkspaceTeam['workflow'],
                            })
                        }
                    >
                        <option value="sequential">Sequential</option>
                        <option value="parallel">Parallel</option>
                        <option value="orchestrated">Orchestrated</option>
                    </select>
                    <p className="text-xs text-text-muted mb-1">Agents (first = lead)</p>
                    <div className="space-y-1 max-h-40 overflow-y-auto mb-2">
                        {newTeamForm.agent_ids.map((id, idx) => {
                            return (
                                <div key={`${id}-${idx}`} className="flex items-center gap-1 text-xs">
                                    <span className="w-16 text-text-muted">
                                        {idx === 0 ? 'Lead' : `#${idx + 1}`}
                                    </span>
                                    <select
                                        className="flex-1 bg-surface-2 rounded px-1 py-0.5 border border-surface-4"
                                        value={id}
                                        onChange={(e) => {
                                            const next = [...newTeamForm.agent_ids];
                                            next[idx] = e.target.value;
                                            setNewTeamForm({ ...newTeamForm, agent_ids: next });
                                        }}
                                    >
                                        {agents.map((x) => (
                                            <option key={x.id} value={x.id}>
                                                {x.name}
                                            </option>
                                        ))}
                                    </select>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            const next = newTeamForm.agent_ids.filter((_, i) => i !== idx);
                                            setNewTeamForm({ ...newTeamForm, agent_ids: next });
                                        }}
                                    >
                                        <X className="w-3 h-3" />
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            if (idx === 0) return;
                                            const next = [...newTeamForm.agent_ids];
                                            [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
                                            setNewTeamForm({ ...newTeamForm, agent_ids: next });
                                        }}
                                    >
                                        <ChevronUp className="w-3 h-3" />
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            if (idx >= newTeamForm.agent_ids.length - 1) return;
                                            const next = [...newTeamForm.agent_ids];
                                            [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
                                            setNewTeamForm({ ...newTeamForm, agent_ids: next });
                                        }}
                                    >
                                        <ChevronDown className="w-3 h-3" />
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                    <button
                        type="button"
                        className="text-xs text-accent mb-2"
                        onClick={() =>
                            setNewTeamForm({
                                ...newTeamForm,
                                agent_ids: [...newTeamForm.agent_ids, agents[0]?.id || ''],
                            })
                        }
                    >
                        + Add agent slot
                    </button>
                    <button
                        type="button"
                        className="w-full py-2 rounded-none bg-accent text-white text-sm"
                        onClick={async () => {
                            await api.createTeam({
                                ...newTeamForm,
                                agent_ids: newTeamForm.agent_ids.filter(Boolean),
                            });
                            setModal(null);
                            void refresh();
                        }}
                    >
                        Save team
                    </button>
                </Modal>
            )}
            {modal?.type === 'generateSkill' && agentDetail && (
                <Modal onClose={() => setModal(null)} title="Generate skill">
                    <input
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        placeholder="Skill name"
                        value={genSkillForm.name}
                        onChange={(e) => setGenSkillForm({ ...genSkillForm, name: e.target.value })}
                    />
                    <textarea
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        placeholder="Description (optional)"
                        value={genSkillForm.description}
                        onChange={(e) => setGenSkillForm({ ...genSkillForm, description: e.target.value })}
                    />
                    <textarea
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        placeholder="Example task (optional)"
                        value={genSkillForm.example}
                        onChange={(e) => setGenSkillForm({ ...genSkillForm, example: e.target.value })}
                    />
                    <button
                        type="button"
                        className="w-full py-2 rounded-none bg-accent text-white text-sm flex items-center justify-center gap-2"
                        onClick={async () => {
                            const res = await api.generateSkill(agentDetail.id, {
                                skill_name: genSkillForm.name,
                                skill_description: genSkillForm.description,
                                example_task: genSkillForm.example || undefined,
                            });
                            setModal({ type: 'previewSkill', markdown: res.markdown, slug: res.suggested_slug });
                        }}
                    >
                        <Sparkles className="w-4 h-4" /> Generate
                    </button>
                </Modal>
            )}
            {modal?.type === 'previewSkill' && agentDetail && (
                <Modal onClose={() => setModal(null)} title="Preview skill">
                    <textarea
                        className="w-full min-h-[240px] text-xs font-mono bg-surface-2 rounded p-2 border border-surface-4 mb-2"
                        value={modal.markdown}
                        onChange={(e) => setModal({ ...modal, markdown: e.target.value })}
                    />
                    <button
                        type="button"
                        className="w-full py-2 rounded-none bg-accent text-white text-sm"
                        onClick={async () => {
                            await api.saveSkill(agentDetail.id, modal.slug, modal.markdown);
                            setModal(null);
                            const d = await api.getWorkspaceAgent(agentDetail.id);
                            setSkills(d.skill_files || []);
                        }}
                    >
                        Save to disk
                    </button>
                </Modal>
            )}
            {modal?.type === 'editSkill' && agentDetail && (
                <Modal onClose={() => setModal(null)} title={`Edit ${modal.slug}`}>
                    <textarea
                        className="w-full min-h-[280px] text-xs font-mono bg-surface-2 rounded p-2 border border-surface-4 mb-2"
                        value={modal.content}
                        onChange={(e) => setModal({ ...modal, content: e.target.value })}
                    />
                    <button
                        type="button"
                        className="w-full py-2 rounded-none bg-accent text-white text-sm"
                        onClick={async () => {
                            await api.saveSkill(agentDetail.id, modal.slug, modal.content);
                            setModal(null);
                            const d = await api.getWorkspaceAgent(agentDetail.id);
                            setSkills(d.skill_files || []);
                        }}
                    >
                        Save
                    </button>
                </Modal>
            )}
        </div>
    );
}

function Modal({
    title,
    children,
    onClose,
}: {
    title: string;
    children: ReactNode;
    onClose: () => void;
}) {
    useEffect(() => {
        const h = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', h);
        return () => window.removeEventListener('keydown', h);
    }, [onClose]);
    return (
            <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
            role="dialog"
            aria-modal
        >
            <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-panel border border-surface-4 bg-surface-1 p-5 shadow-2xl">
                <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
                    <button
                        type="button"
                        onClick={onClose}
                        className="rounded-btn p-1.5 text-text-muted transition-colors hover:bg-surface-3 hover:text-text-primary"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
}

function TeamCenter({
    team,
    agents,
    teamTask,
    setTeamTask,
    teamLog,
    teamRunning,
    onRun,
}: {
    team: WorkspaceTeam | undefined;
    agents: WorkspaceAgent[];
    teamTask: string;
    setTeamTask: (s: string) => void;
    teamLog: string;
    teamRunning: boolean;
    onRun: () => void;
}) {
    if (!team) {
        return (
            <div className="flex flex-col h-full min-h-0 items-center justify-center text-text-muted text-sm p-8">
                Team not found. Select another from the list.
            </div>
        );
    }
    const roster = team.agent_ids
        .map((id) => agents.find((a) => a.id === id))
        .filter(Boolean) as WorkspaceAgent[];
    return (
        <div className="flex flex-col h-full min-h-0 p-4">
            <h2 className="text-lg font-semibold mb-1">{team.name}</h2>
            <p className="text-xs text-text-muted mb-3">{team.description}</p>
            <div className="flex flex-wrap gap-2 mb-4">
                {roster.map((a, i) => (
                    <span
                        key={a.id}
                        className="text-xs px-2 py-1 rounded-none bg-surface-2 border border-surface-4"
                    >
                        {i === 0 ? 'Lead: ' : ''}
                        {a.avatar} {a.name}
                    </span>
                ))}
            </div>
            <textarea
                className="w-full min-h-[80px] text-sm bg-surface-2 rounded p-2 border border-surface-4 mb-2"
                placeholder="What task should this team tackle?"
                value={teamTask}
                onChange={(e) => setTeamTask(e.target.value)}
            />
            <button
                type="button"
                disabled={teamRunning}
                onClick={onRun}
                className="mb-4 px-4 py-2 rounded-none bg-accent text-white text-sm disabled:opacity-50"
            >
                {teamRunning ? 'Running…' : 'Run team'}
            </button>
            <div className="flex-1 min-h-0 overflow-y-auto rounded-none border border-surface-4 p-2 bg-surface-1 text-xs font-mono whitespace-pre-wrap">
                {teamLog || <span className="text-text-muted">Execution log will appear here.</span>}
            </div>
        </div>
    );
}
