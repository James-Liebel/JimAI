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
            <header className="flex-shrink-0 border-b border-surface-4 px-4 py-3 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                    <Bot className="w-5 h-5 text-accent" />
                    <h1 className="text-xl font-semibold tracking-tight text-text-primary">Agents</h1>
                    <span className="text-sm text-text-muted hidden sm:inline">
                        Personas, skills, and teams — local Ollama only
                    </span>
                </div>
                <Link
                    to="/agent-studio"
                    className="text-xs text-accent hover:underline"
                >
                    Open classic Agent Studio (flow)
                </Link>
            </header>

            {loading ? (
                <div className="flex-1 flex items-center justify-center text-text-muted">
                    <Loader2 className="w-8 h-8 animate-spin" />
                </div>
            ) : (
                <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-0 border-t border-surface-4">
                    {/* Left roster */}
                    <aside className="lg:col-span-3 border-r border-surface-4 flex flex-col min-h-0 overflow-hidden bg-surface-1">
                        <div className="p-3 border-b border-surface-4">
                            <button
                                type="button"
                                onClick={() => {
                                    setModal({ type: 'newAgent' });
                                    setNewAgentForm((f) => ({
                                        ...f,
                                        model: models[0] || 'qwen3:8b',
                                    }));
                                }}
                                className="w-full flex items-center justify-center gap-2 py-2 rounded-none bg-accent text-white text-sm font-medium hover:bg-accent-hover"
                            >
                                <Plus className="w-4 h-4" /> New Agent
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-2 space-y-1">
                            <p className="text-[10px] uppercase tracking-wide text-text-muted px-2">Agents</p>
                            {agents.length === 0 ? (
                                <p className="text-sm text-text-muted px-2 py-4">No agents yet. Create one.</p>
                            ) : (
                                agents.map((a) => (
                                    <div
                                        key={a.id}
                                        className={cn(
                                            'relative rounded-none border px-2 py-2 flex items-start gap-2 cursor-pointer transition-colors',
                                            selectedAgentId === a.id && !selectedTeamId
                                                ? 'border-accent bg-accent/10'
                                                : 'border-surface-4 hover:bg-surface-2',
                                        )}
                                        onClick={() => selectAgent(a.id)}
                                    >
                                        <span className="text-xl">{a.avatar}</span>
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm font-medium truncate">{a.name}</div>
                                            <div className="text-[11px] text-text-muted truncate">{a.role}</div>
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-3 text-text-secondary">
                                                {a.model}
                                            </span>
                                        </div>
                                        <span
                                            className={cn(
                                                'w-2 h-2 rounded-none mt-1 flex-shrink-0',
                                                a.status === 'running'
                                                    ? 'bg-amber-400'
                                                    : a.status === 'error'
                                                      ? 'bg-red-500'
                                                      : 'bg-accent-green',
                                            )}
                                        />
                                        <button
                                            type="button"
                                            className="p-1 rounded hover:bg-surface-3"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                setMenuOpen(menuOpen === a.id ? null : a.id);
                                            }}
                                        >
                                            <MoreVertical className="w-4 h-4 text-text-muted" />
                                        </button>
                                        {menuOpen === a.id && (
                                            <div
                                                className="absolute right-1 top-9 z-20 bg-surface-2 border border-surface-4 rounded-none shadow-none text-xs py-1 min-w-[120px]"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <button
                                                    type="button"
                                                    className="w-full text-left px-3 py-1.5 hover:bg-surface-3"
                                                    onClick={async () => {
                                                        setMenuOpen(null);
                                                        if (
                                                            !confirm(`Delete agent "${a.name}"?`)
                                                        ) return;
                                                        await api.deleteWorkspaceAgent(a.id);
                                                        if (selectedAgentId === a.id) {
                                                            setSelectedAgentId(null);
                                                            setAgentDetail(null);
                                                        }
                                                        void refresh();
                                                    }}
                                                >
                                                    Delete
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                ))
                            )}
                        </div>
                        <div className="p-3 border-t border-surface-4 space-y-2">
                            <p className="text-[10px] uppercase tracking-wide text-text-muted px-1">Teams</p>
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
                                className="w-full flex items-center justify-center gap-2 py-1.5 rounded-none border border-surface-4 text-sm hover:bg-surface-2"
                            >
                                <Users className="w-4 h-4" /> New Team
                            </button>
                            {teams.map((t) => (
                                <button
                                    key={t.id}
                                    type="button"
                                    onClick={() => selectTeam(t.id)}
                                    className={cn(
                                        'w-full text-left rounded-none border px-2 py-2 text-sm',
                                        selectedTeamId === t.id
                                            ? 'border-accent bg-accent/10'
                                            : 'border-surface-4 hover:bg-surface-2',
                                    )}
                                >
                                    <div className="font-medium">{t.name}</div>
                                    <div className="text-[10px] text-text-muted">{t.workflow}</div>
                                </button>
                            ))}
                        </div>
                    </aside>

                    {/* Center */}
                    <main className="lg:col-span-6 flex flex-col min-h-0 border-r border-surface-4">
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
                                <div className="p-4 border-b border-surface-4 space-y-3 max-h-[45vh] overflow-y-auto">
                                    <input
                                        className="w-full text-xl font-semibold bg-transparent border-b border-transparent focus:border-accent outline-none"
                                        value={agentDetail.name}
                                        onChange={(e) =>
                                            setAgentDetail({ ...agentDetail, name: e.target.value })
                                        }
                                        onBlur={() => void saveAgentFields({ name: agentDetail.name })}
                                    />
                                    <input
                                        className="w-full text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                                        value={agentDetail.role}
                                        onChange={(e) =>
                                            setAgentDetail({ ...agentDetail, role: e.target.value })
                                        }
                                        onBlur={() => void saveAgentFields({ role: agentDetail.role })}
                                    />
                                    <select
                                        className="w-full text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                                        value={agentDetail.model}
                                        onChange={(e) => {
                                            const m = e.target.value;
                                            setAgentDetail({ ...agentDetail, model: m });
                                            void saveAgentFields({ model: m });
                                        }}
                                    >
                                        {models.map((m) => (
                                            <option key={m} value={m}>
                                                {m}
                                            </option>
                                        ))}
                                    </select>
                                    <textarea
                                        className="w-full min-h-[120px] text-sm bg-surface-2 rounded p-2 border border-surface-4 font-mono"
                                        placeholder="System prompt / persona"
                                        value={agentDetail.system_prompt}
                                        onChange={(e) =>
                                            setAgentDetail({ ...agentDetail, system_prompt: e.target.value })
                                        }
                                        onBlur={() =>
                                            void saveAgentFields({ system_prompt: agentDetail.system_prompt })
                                        }
                                    />
                                    <div className="flex flex-wrap gap-2 text-xs">
                                        <button
                                            type="button"
                                            className="px-2 py-1 rounded bg-surface-3 hover:bg-surface-4"
                                            onClick={() => setChatMessages([])}
                                        >
                                            Clear chat
                                        </button>
                                        <button
                                            type="button"
                                            className="px-2 py-1 rounded bg-surface-3 hover:bg-surface-4"
                                            onClick={() => {
                                                const blob = new Blob(
                                                    [JSON.stringify(agentDetail, null, 2)],
                                                    { type: 'application/json' },
                                                );
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
                                        <label className="flex items-center gap-1 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={agentDetail.memory_enabled}
                                                onChange={(e) => {
                                                    const v = e.target.checked;
                                                    setAgentDetail({ ...agentDetail, memory_enabled: v });
                                                    void saveAgentFields({ memory_enabled: v });
                                                }}
                                            />
                                            Memory
                                        </label>
                                    </div>
                                </div>
                                <div className="flex-1 flex flex-col min-h-0 p-4">
                                    <p className="text-xs text-text-muted mb-2">Test chat (skills injected on server)</p>
                                    <div className="flex-1 overflow-y-auto space-y-2 mb-2 rounded-none border border-surface-4 p-2 bg-surface-1">
                                        {chatMessages.map((msg, i) => (
                                            <div
                                                key={i}
                                                className={cn(
                                                    'text-sm rounded px-2 py-1',
                                                    msg.role === 'user'
                                                        ? 'bg-accent/20 ml-4'
                                                        : 'bg-surface-2 mr-4',
                                                )}
                                            >
                                                <span className="text-[10px] text-text-muted">{msg.role}</span>
                                                <div className="whitespace-pre-wrap">{msg.content}</div>
                                            </div>
                                        ))}
                                        {streaming && (
                                            <div className="text-xs text-text-muted flex items-center gap-1">
                                                <span className="inline-flex gap-0.5">
                                                    <span className="w-1 h-1 rounded-none bg-accent animate-pulse" />
                                                    <span className="w-1 h-1 rounded-none bg-accent animate-pulse delay-75" />
                                                    <span className="w-1 h-1 rounded-none bg-accent animate-pulse delay-150" />
                                                </span>
                                                Generating
                                            </div>
                                        )}
                                        <div ref={chatEndRef} />
                                    </div>
                                    <div className="flex gap-2">
                                        <textarea
                                            className="flex-1 min-h-[44px] max-h-32 text-sm bg-surface-2 rounded px-2 py-2 border border-surface-4 resize-y"
                                            placeholder="Message… (Ctrl+Enter to send)"
                                            value={chatInput}
                                            onChange={(e) => setChatInput(e.target.value)}
                                            onKeyDown={onKeyDownChat}
                                        />
                                        <button
                                            type="button"
                                            disabled={streaming}
                                            onClick={() => void sendChat()}
                                            className="px-4 rounded-none bg-accent text-white hover:bg-accent-hover disabled:opacity-50"
                                        >
                                            <Send className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center text-text-muted p-8 text-center">
                                <Bot className="w-12 h-12 mb-4 opacity-40" />
                                <p className="text-sm">Select an agent or team from the left.</p>
                            </div>
                        )}
                    </main>

                    {/* Skills */}
                    <aside className="lg:col-span-3 flex flex-col min-h-0 bg-surface-1">
                        <div className="p-3 border-b border-surface-4">
                            <h2 className="text-sm font-semibold mb-2">Skills</h2>
                            {agentDetail ? (
                                <>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setGenSkillForm({ name: '', description: '', example: '' });
                                            setModal({ type: 'generateSkill' });
                                        }}
                                        className="w-full flex items-center justify-center gap-2 py-2 rounded-none border border-accent text-accent text-sm hover:bg-accent/10 mb-2"
                                    >
                                        <Sparkles className="w-4 h-4" /> Generate skill
                                    </button>
                                    <input
                                        type="search"
                                        placeholder="Filter skills…"
                                        className="w-full text-xs bg-surface-2 rounded px-2 py-1 border border-surface-4"
                                        value={skillFilter}
                                        onChange={(e) => setSkillFilter(e.target.value)}
                                    />
                                </>
                            ) : (
                                <p className="text-xs text-text-muted">Select an agent to manage skills.</p>
                            )}
                        </div>
                        <div className="flex-1 overflow-y-auto p-2 space-y-2">
                            {agentDetail &&
                                filteredSkills.map((s) => (
                                    <div
                                        key={s.slug}
                                        className="rounded-none border border-surface-4 p-2 text-xs bg-surface-0"
                                    >
                                        <div className="font-medium">{s.name}</div>
                                        <p className="text-text-muted line-clamp-2 mt-1">{s.preview}</p>
                                        <p className="text-[10px] text-text-muted mt-1">{s.modified_at}</p>
                                        <div className="flex gap-1 mt-2">
                                            <button
                                                type="button"
                                                className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-4"
                                                onClick={async () => {
                                                    const content = await api.getSkillRaw(agentDetail.id, s.slug);
                                                    setModal({ type: 'editSkill', slug: s.slug, content });
                                                }}
                                            >
                                                Edit
                                            </button>
                                            <button
                                                type="button"
                                                className="px-2 py-0.5 rounded bg-surface-3 hover:bg-surface-4 text-accent-red"
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
                                ))}
                            {agentDetail && filteredSkills.length === 0 && (
                                <p className="text-xs text-text-muted px-2">No skills match filter.</p>
                            )}
                        </div>
                    </aside>
                </div>
            )}

            {/* Modals */}
            {modal?.type === 'newAgent' && (
                <Modal onClose={() => setModal(null)} title="New agent">
                    <label className="block text-xs text-text-muted mb-1">Name</label>
                    <input
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        value={newAgentForm.name}
                        onChange={(e) => setNewAgentForm({ ...newAgentForm, name: e.target.value })}
                    />
                    <label className="block text-xs text-text-muted mb-1">Role template</label>
                    <select
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        value={newAgentForm.role}
                        onChange={(e) => {
                            const r = e.target.value;
                            setNewAgentForm({
                                ...newAgentForm,
                                role: r,
                            });
                        }}
                    >
                        {Object.keys(ROLE_DEFAULTS).map((r) => (
                            <option key={r} value={r}>
                                {r}
                            </option>
                        ))}
                    </select>
                    <label className="block text-xs text-text-muted mb-1">Model</label>
                    <select
                        className="w-full mb-2 text-sm bg-surface-2 rounded px-2 py-1 border border-surface-4"
                        value={newAgentForm.model}
                        onChange={(e) => setNewAgentForm({ ...newAgentForm, model: e.target.value })}
                    >
                        {models.map((m) => (
                            <option key={m} value={m}>
                                {m}
                            </option>
                        ))}
                    </select>
                    <button
                        type="button"
                        className="w-full py-2 rounded-none bg-accent text-white text-sm"
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
                        Create
                    </button>
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            role="dialog"
            aria-modal
        >
            <div className="bg-surface-1 border border-surface-4 rounded-none max-w-lg w-full max-h-[90vh] overflow-y-auto p-4 shadow-none">
                <div className="flex justify-between items-center mb-3">
                    <h3 className="font-semibold">{title}</h3>
                    <button type="button" onClick={onClose} className="p-1 rounded hover:bg-surface-3">
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
