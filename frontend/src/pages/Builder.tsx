import { useCallback, useEffect, useMemo, useState } from 'react';
import * as agentApi from '../lib/agentSpaceApi';
import { readSharedWorkspaceDraft, writeSharedWorkspaceDraft } from '../lib/utils';

type OrchestrationStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed';

type OrchestrationNode = {
    id: string;
    role: string;
    workerLevel: number;
    model?: string;
    dependsOn: string[];
    description?: string;
    status?: OrchestrationStatus;
};

type AgentMessageRow = {
    from: string;
    to: string;
    channel: string;
};

type TerminalRow = {
    id: string;
    command: string;
    cwd: string;
    exitCode: number;
    stdout: string;
    stderr: string;
    timestamp: number;
};

const APP_CREATIONS_DIR = 'data/app_creations';
const APP_CREATIONS_INDEX = `${APP_CREATIONS_DIR}/APP_CREATIONS.md`;
const APP_CREATIONS_HINT = `Store each generated app under ${APP_CREATIONS_DIR}/<app_name>/ and update ${APP_CREATIONS_INDEX}.`;

function humanizeOptionKey(key: string): string {
    return String(key || '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (char) => char.toUpperCase())
        .trim();
}

function parseSubagentId(message: string, eventType: string): string {
    if (!message) return '';
    if (eventType === 'subagent.started') {
        const m = message.match(/Starting\s+([^\s]+)\s+\(/i);
        return m ? m[1] : '';
    }
    if (eventType === 'subagent.completed') {
        const m = message.match(/(?:Planner|Tester|Verifier|Subagent)\s+([^\s]+)\s+completed/i);
        return m ? m[1] : '';
    }
    if (eventType === 'subagent.error') {
        const m = message.match(/Subagent\s+([^\s]+)\s+failed/i);
        return m ? m[1] : '';
    }
    return '';
}

function extractWorkflowNodesFromEvents(events: agentApi.AgentSpaceEvent[]): OrchestrationNode[] {
    for (let i = events.length - 1; i >= 0; i -= 1) {
        const evt = events[i];
        if (evt.type !== 'run.workflow') continue;
        const subagents = (evt.data as { subagents?: unknown })?.subagents;
        if (!Array.isArray(subagents)) continue;
        const rows: OrchestrationNode[] = [];
        for (const item of subagents) {
            const row = item as Record<string, unknown>;
            const id = String(row.id || '').trim();
            if (!id) continue;
            rows.push({
                id,
                role: String(row.role || 'coder'),
                workerLevel: Number(row.worker_level || 1) || 1,
                model: String(row.model || ''),
                dependsOn: Array.isArray(row.depends_on)
                    ? row.depends_on.map((dep) => String(dep || '').trim()).filter(Boolean)
                    : [],
                description: String(row.description || ''),
            });
        }
        return rows;
    }
    return [];
}

function statusTone(status: OrchestrationStatus): string {
    if (status === 'running') return 'border-accent/40 bg-accent/10';
    if (status === 'completed') return 'border-accent-green/40 bg-accent-green/10';
    if (status === 'failed') return 'border-accent-red/40 bg-accent-red/10';
    if (status === 'pending') return 'border-surface-3 bg-surface-2';
    return 'border-surface-3 bg-surface-1';
}

function normalizeProfile(value: unknown): 'safe' | 'dev' | 'unrestricted' {
    const v = String(value || 'safe');
    if (v === 'dev' || v === 'unrestricted') return v;
    return 'safe';
}

export default function Builder() {
    const [prompt, setPrompt] = useState('');
    const [context, setContext] = useState('');
    const [advancedMode, setAdvancedMode] = useState(false);

    const [runId, setRunId] = useState('');
    const [runStatus, setRunStatus] = useState('');
    const [runs, setRuns] = useState<agentApi.AgentSpaceRunSummary[]>([]);
    const [events, setEvents] = useState<agentApi.AgentSpaceEvent[]>([]);
    const [preview, setPreview] = useState<agentApi.BuilderPreviewResponse | null>(null);

    const [settings, setSettings] = useState<Record<string, unknown>>({});
    const [loadingLaunch, setLoadingLaunch] = useState(false);
    const [loadingStop, setLoadingStop] = useState(false);
    const [loadingPreview, setLoadingPreview] = useState(false);

    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [recommendedSkills, setRecommendedSkills] = useState<agentApi.AgentSkillSummary[]>([]);
    const [recommendedSkillContext, setRecommendedSkillContext] = useState('');
    const [loadingRecommendedSkills, setLoadingRecommendedSkills] = useState(false);
    const [sharedTeamName, setSharedTeamName] = useState('Auto Build Team');
    const [sharedSavedTeamId, setSharedSavedTeamId] = useState('');
    const [sharedSavedTeamName, setSharedSavedTeamName] = useState('');
    const [sharedSelectedSkills, setSharedSelectedSkills] = useState<Array<{ slug: string; name: string }>>([]);
    const [sharedLastRunId, setSharedLastRunId] = useState('');
    const [sharedLastRunStatus, setSharedLastRunStatus] = useState('');

    const [treePath, setTreePath] = useState('.');
    const [treeData, setTreeData] = useState<agentApi.RepoTreeResponse | null>(null);
    const [loadingTree, setLoadingTree] = useState(false);
    const [fullTreeMode, setFullTreeMode] = useState(false);
    const [selectedFile, setSelectedFile] = useState('');
    const [selectedFileContent, setSelectedFileContent] = useState('');
    const [loadingFile, setLoadingFile] = useState(false);

    const [terminalCwd, setTerminalCwd] = useState('.');
    const [terminalCommand, setTerminalCommand] = useState('');
    const [terminalRows, setTerminalRows] = useState<TerminalRow[]>([]);
    const [runningTerminal, setRunningTerminal] = useState(false);

    const [agentTo, setAgentTo] = useState('');
    const [agentChannel, setAgentChannel] = useState('change-request');
    const [agentMessage, setAgentMessage] = useState('');
    const [sendingAgentMessage, setSendingAgentMessage] = useState(false);

    const [exportTarget, setExportTarget] = useState('app-build-export');
    const [exportPaths, setExportPaths] = useState(APP_CREATIONS_DIR);
    const [exporting, setExporting] = useState(false);

    const refreshRuns = useCallback(async () => {
        const rows = await agentApi.listRuns(50);
        setRuns(rows);
        if (runId) {
            const current = rows.find((row) => row.id === runId);
            if (current) setRunStatus(current.status);
        }
    }, [runId]);

    const refreshTree = useCallback(async () => {
        setLoadingTree(true);
        try {
            const depth = fullTreeMode ? 16 : 8;
            const limit = fullTreeMode ? 30000 : 10000;
            const data = await agentApi.listRepoTree(treePath || '.', depth, limit, false);
            setTreeData(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load file tree.');
        } finally {
            setLoadingTree(false);
        }
    }, [fullTreeMode, treePath]);

    useEffect(() => {
        const shared = readSharedWorkspaceDraft();
        if (shared.prompt) setPrompt(String(shared.prompt));
        if (shared.context) setContext(String(shared.context));
        if (shared.teamName) setSharedTeamName(String(shared.teamName));
        if (shared.savedTeamId) setSharedSavedTeamId(String(shared.savedTeamId));
        if (shared.savedTeamName) setSharedSavedTeamName(String(shared.savedTeamName));
        if (Array.isArray(shared.selectedSkills)) {
            setSharedSelectedSkills(shared.selectedSkills.map((row) => ({
                slug: String(row.slug || ''),
                name: String(row.name || ''),
            })).filter((row) => row.slug));
        }
        if (shared.lastRunId) setSharedLastRunId(String(shared.lastRunId));
        if (shared.lastRunStatus) setSharedLastRunStatus(String(shared.lastRunStatus));
    }, []);

    useEffect(() => {
        const onStorage = () => {
            const shared = readSharedWorkspaceDraft();
            setSharedTeamName(String(shared.teamName || 'Auto Build Team'));
            setSharedSavedTeamId(String(shared.savedTeamId || ''));
            setSharedSavedTeamName(String(shared.savedTeamName || ''));
            setSharedSelectedSkills(Array.isArray(shared.selectedSkills)
                ? shared.selectedSkills.map((row) => ({
                    slug: String(row.slug || ''),
                    name: String(row.name || ''),
                })).filter((row) => row.slug)
                : []);
            setSharedLastRunId(String(shared.lastRunId || ''));
            setSharedLastRunStatus(String(shared.lastRunStatus || ''));
        };
        window.addEventListener('storage', onStorage);
        return () => window.removeEventListener('storage', onStorage);
    }, []);

    useEffect(() => {
        agentApi.getSettings()
            .then((cfg) => setSettings(cfg))
            .catch(() => {});
        refreshRuns().catch(() => {});
        refreshTree().catch(() => {});
    }, [refreshRuns, refreshTree]);

    useEffect(() => {
        const id = window.setInterval(() => refreshRuns().catch(() => {}), 2500);
        return () => window.clearInterval(id);
    }, [refreshRuns]);

    useEffect(() => {
        writeSharedWorkspaceDraft({
            prompt,
            context,
            teamName: sharedTeamName,
        });
    }, [context, prompt, sharedTeamName]);

    useEffect(() => {
        if (!runId) return;
        const unsubscribe = agentApi.subscribeRunEvents(
            runId,
            (event) => setEvents((prev) => [...prev.slice(-499), event]),
            () => {},
        );
        return unsubscribe;
    }, [runId]);

    useEffect(() => {
        if (prompt.trim().length < 3) {
            setPreview(null);
            return;
        }
        let active = true;
        setLoadingPreview(true);
        const id = window.setTimeout(() => {
            agentApi.builderPreview({
                prompt: prompt.trim(),
                context: context.trim(),
                team_name: 'Auto Build Team',
                auto_agent_packs: true,
                use_saved_teams: true,
            })
                .then((data) => {
                    if (active) setPreview(data);
                })
                .catch(() => {
                    if (active) setPreview(null);
                })
                .finally(() => {
                    if (active) setLoadingPreview(false);
                });
        }, 450);
        return () => {
            active = false;
            window.clearTimeout(id);
        };
    }, [prompt, context]);

    useEffect(() => {
        const objective = [prompt.trim(), context.trim()].filter(Boolean).join('\n\n');
        if (objective.length < 3) {
            setRecommendedSkills([]);
            setRecommendedSkillContext('');
            setLoadingRecommendedSkills(false);
            return;
        }
        let active = true;
        setLoadingRecommendedSkills(true);
        const id = window.setTimeout(() => {
            agentApi.selectSkills({
                objective,
                limit: 8,
                include_context: true,
            })
                .then((data) => {
                    if (!active) return;
                    setRecommendedSkills(Array.isArray(data.selected) ? data.selected : []);
                    setRecommendedSkillContext(String(data.context || ''));
                })
                .catch(() => {
                    if (!active) return;
                    setRecommendedSkills([]);
                    setRecommendedSkillContext('');
                })
                .finally(() => {
                    if (active) setLoadingRecommendedSkills(false);
                });
        }, 500);
        return () => {
            active = false;
            window.clearTimeout(id);
        };
    }, [context, prompt]);

    const openFile = useCallback(async (path: string) => {
        if (!path || path === '.') return;
        setSelectedFile(path);
        setLoadingFile(true);
        setError('');
        try {
            const row = await agentApi.toolsRead(path);
            setSelectedFileContent(row.content || '');
        } catch (err) {
            setSelectedFileContent('');
            setError(err instanceof Error ? err.message : 'Failed to open file.');
        } finally {
            setLoadingFile(false);
        }
    }, []);

    const launchBuild = useCallback(async () => {
        const cleanPrompt = prompt.trim();
        if (!cleanPrompt) {
            setError('Enter a build prompt first.');
            return;
        }
        setError('');
        setMessage('');
        setLoadingLaunch(true);
        setEvents([]);
        try {
            const launchContext = [context.trim(), APP_CREATIONS_HINT].filter(Boolean).join('\n\n');
            const preferredSkills = sharedSelectedSkills.map((skill) => skill.name).filter(Boolean);
            const finalContext = preferredSkills.length > 0
                ? [launchContext, `Preferred skills from Agent Studio:\n- ${preferredSkills.join('\n- ')}`].filter(Boolean).join('\n\n')
                : launchContext;
            const response = await agentApi.builderLaunch({
                prompt: cleanPrompt,
                context: finalContext,
                team_name: sharedSavedTeamName || sharedTeamName || 'Auto Build Team',
                save_team: true,
                auto_agent_packs: true,
                use_saved_teams: true,
                review_gate: Boolean(settings.review_gate ?? true),
                allow_shell: Boolean(settings.allow_shell ?? false),
                command_profile: normalizeProfile(settings.command_profile),
                required_checks: [],
                autonomous: true,
                continue_on_subagent_failure: Boolean(settings.continue_on_subagent_failure ?? true),
            });
            setRunId(response.run.id);
            setRunStatus(response.run.status);
            setSharedLastRunId(response.run.id);
            setSharedLastRunStatus(response.run.status);
            const refs = Array.isArray(response.open_source_refs) ? response.open_source_refs.length : 0;
            setMessage(
                refs > 0
                    ? `Build run started: ${response.run.id}. Open-source refs attached: ${refs}.`
                    : `Build run started: ${response.run.id}.`,
            );
            writeSharedWorkspaceDraft({
                prompt: cleanPrompt,
                context,
                teamName: sharedSavedTeamName || sharedTeamName || 'Auto Build Team',
                savedTeamName: sharedSavedTeamName || sharedTeamName || 'Auto Build Team',
                selectedSkills: sharedSelectedSkills,
                lastRunId: response.run.id,
                lastRunStatus: response.run.status,
                lastRunObjective: cleanPrompt,
            });
            await refreshRuns();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start build run.');
        } finally {
            setLoadingLaunch(false);
        }
    }, [context, prompt, refreshRuns, settings.allow_shell, settings.command_profile, settings.review_gate, sharedSavedTeamName, sharedSelectedSkills, sharedTeamName]);

    const stopBuild = useCallback(async () => {
        if (!runId) return;
        setError('');
        setMessage('');
        setLoadingStop(true);
        try {
            await agentApi.stopRun(runId, 'Stopped from Builder workspace.');
            setRunStatus('stopped');
            setMessage(`Run ${runId} stop requested.`);
            await refreshRuns();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to stop run.');
        } finally {
            setLoadingStop(false);
        }
    }, [refreshRuns, runId]);

    const sendAgentControl = useCallback(async () => {
        const note = agentMessage.trim();
        if (!note) {
            setError('Enter an orchestration message first.');
            return;
        }
        if (!runId) {
            setError('No active run selected.');
            return;
        }
        setError('');
        setMessage('');
        setSendingAgentMessage(true);
        try {
            await agentApi.postRunMessage(runId, {
                from_agent: 'user',
                to_agent: agentTo.trim(),
                channel: agentChannel.trim() || 'general',
                content: note,
            });
            setAgentMessage('');
            setMessage(`Sent ${agentChannel} message to ${agentTo || 'agent team'}.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send orchestration message.');
        } finally {
            setSendingAgentMessage(false);
        }
    }, [agentChannel, agentMessage, agentTo, runId]);

    const runTerminalCommand = useCallback(async () => {
        const command = terminalCommand.trim();
        if (!command) return;
        setRunningTerminal(true);
        setError('');
        try {
            const result = await agentApi.toolsShell({
                command,
                cwd: terminalCwd.trim() || '.',
                profile: normalizeProfile(settings.command_profile),
                timeout: 180,
            });
            const row: TerminalRow = {
                id: `${Date.now()}-${Math.random()}`,
                command,
                cwd: terminalCwd.trim() || '.',
                exitCode: Number(result.exit_code ?? (result.success ? 0 : -1)),
                stdout: String(result.stdout || ''),
                stderr: String(result.stderr || ''),
                timestamp: Date.now(),
            };
            setTerminalRows((prev) => [row, ...prev].slice(0, 80));
            setTerminalCommand('');
        } catch (err) {
            const row: TerminalRow = {
                id: `${Date.now()}-${Math.random()}`,
                command,
                cwd: terminalCwd.trim() || '.',
                exitCode: -1,
                stdout: '',
                stderr: err instanceof Error ? err.message : 'Terminal command failed.',
                timestamp: Date.now(),
            };
            setTerminalRows((prev) => [row, ...prev].slice(0, 80));
        } finally {
            setRunningTerminal(false);
        }
    }, [settings.command_profile, terminalCommand, terminalCwd]);

    const exportBuildOutput = useCallback(async () => {
        setError('');
        setMessage('');
        setExporting(true);
        try {
            const includePaths = exportPaths
                .split('\n')
                .map((line) => line.trim())
                .filter(Boolean);
            if (includePaths.length === 0) {
                setError('Add at least one export include path.');
                return;
            }
            const result = await agentApi.exportBundle(
                exportTarget.trim() || 'app-build-export',
                includePaths,
                'build-page-export',
            );
            setMessage(`Exported ${result.count} path(s) to ${result.target_folder}.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Export failed.');
        } finally {
            setExporting(false);
        }
    }, [exportPaths, exportTarget]);

    const previewNodes = useMemo<OrchestrationNode[]>(
        () => (preview?.team_agents || []).map((agent) => ({
            id: agent.id,
            role: agent.role,
            workerLevel: Number(agent.worker_level || 1) || 1,
            model: String(agent.model || ''),
            dependsOn: agent.depends_on || [],
            description: agent.description || '',
        })),
        [preview],
    );

    const optionHelpEntries = useMemo(
        () => Object.entries(preview?.option_help || {}),
        [preview],
    );

    const liveNodes = useMemo<OrchestrationNode[]>(() => extractWorkflowNodesFromEvents(events), [events]);

    const orchestrationNodes = useMemo<OrchestrationNode[]>(
        () => (liveNodes.length > 0 ? liveNodes : previewNodes),
        [liveNodes, previewNodes],
    );

    const orchestrationStatuses = useMemo(() => {
        const statusMap = new Map<string, OrchestrationStatus>();
        for (const node of orchestrationNodes) {
            statusMap.set(node.id, runId ? 'pending' : 'idle');
        }
        for (const evt of events) {
            const id = parseSubagentId(String(evt.message || ''), evt.type);
            if (!id) continue;
            if (evt.type === 'subagent.started') statusMap.set(id, 'running');
            if (evt.type === 'subagent.completed') statusMap.set(id, 'completed');
            if (evt.type === 'subagent.error') statusMap.set(id, 'failed');
        }
        return statusMap;
    }, [events, orchestrationNodes, runId]);

    const visualNodes = useMemo<OrchestrationNode[]>(
        () => orchestrationNodes.map((node) => ({ ...node, status: orchestrationStatuses.get(node.id) || 'idle' })),
        [orchestrationNodes, orchestrationStatuses],
    );

    const agentIds = useMemo(() => {
        const ids = new Set<string>();
        for (const node of visualNodes) ids.add(node.id);
        if (ids.size === 0) ids.add('planner');
        return Array.from(ids);
    }, [visualNodes]);

    const messageFlow = useMemo<AgentMessageRow[]>(() => {
        const rows: AgentMessageRow[] = [];
        for (const evt of events) {
            if (evt.type !== 'agent.message') continue;
            const payload = (evt.data as { message?: Record<string, unknown> })?.message;
            if (payload && typeof payload === 'object') {
                rows.push({
                    from: String(payload.from || ''),
                    to: String(payload.to || 'broadcast') || 'broadcast',
                    channel: String(payload.channel || 'general'),
                });
                continue;
            }
            const line = String(evt.message || '');
            const m = line.match(/^(.+?)\s->\s(.+?)\s\[(.+?)\]$/);
            if (m) rows.push({ from: m[1], to: m[2], channel: m[3] });
        }
        return rows.slice(-40).reverse();
    }, [events]);

    return (
        <div className="builder-workspace h-full min-h-0 overflow-auto p-3 md:p-6">
            <div className="mx-auto min-h-full w-full max-w-[1720px] grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_360px] gap-4">
                <aside className="rounded-card border border-surface-3 bg-surface-1 flex flex-col overflow-hidden md:min-h-0">
                    <div className="px-4 py-3 border-b border-surface-3">
                        <p className="text-sm font-semibold text-text-primary">File Structure</p>
                        <p className="text-[11px] text-text-secondary">
                            Full repository tree + app creations hub.
                            {advancedMode ? ' Advanced controls are visible.' : ' Simple mode is active.'}
                        </p>
                    </div>
                    <div className="p-3 border-b border-surface-3 flex flex-col gap-2">
                        <p className="text-[11px] uppercase tracking-wide text-text-secondary">Editable</p>
                        <div className="flex items-center gap-2">
                            <input
                                value={treePath}
                                onChange={(e) => setTreePath(e.target.value)}
                                className="builder-input flex-1 bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                                placeholder="."
                            />
                            <button
                                type="button"
                                onClick={() => refreshTree().catch(() => {})}
                                className="px-2 py-1.5 rounded-btn border border-accent/40 text-accent text-xs"
                            >
                                {loadingTree ? '...' : 'Refresh'}
                            </button>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            <button
                                type="button"
                                onClick={() => setTreePath('.')}
                                className="px-2 py-1 rounded-btn border border-surface-4 text-xs text-text-secondary hover:bg-surface-2"
                            >
                                Full Repo
                            </button>
                            <button
                                type="button"
                                onClick={() => setFullTreeMode((prev) => !prev)}
                                className={`px-2 py-1 rounded-btn border text-xs ${
                                    fullTreeMode
                                        ? 'border-accent/40 text-accent bg-accent/10'
                                        : 'border-surface-4 text-text-secondary hover:bg-surface-2'
                                }`}
                                disabled={!advancedMode}
                            >
                                {fullTreeMode ? 'Full Tree ON' : 'Fast Tree'}
                            </button>
                            <button
                                type="button"
                                onClick={() => setTreePath(APP_CREATIONS_DIR)}
                                className="px-2 py-1 rounded-btn border border-accent/40 text-xs text-accent"
                            >
                                App Creations
                            </button>
                            <button
                                type="button"
                                onClick={() => openFile(APP_CREATIONS_INDEX).catch(() => {})}
                                className="px-2 py-1 rounded-btn border border-surface-4 text-xs text-text-secondary hover:bg-surface-2"
                            >
                                Open Index File
                            </button>
                        </div>
                        <p className="text-[11px] text-text-muted">
                            mode: {fullTreeMode ? 'full tree (slower)' : 'fast tree'}
                        </p>
                        {!advancedMode && (
                            <p className="text-[11px] text-text-muted">
                                Turn on advanced mode to enable deep tree scanning and preview panes.
                            </p>
                        )}
                    </div>
                    <div className="flex-1 overflow-auto p-3 md:min-h-0">
                        {!treeData && <p className="text-xs text-text-secondary">No tree loaded.</p>}
                        {treeData && (
                            <>
                                <p className="text-[11px] text-text-muted mb-2">
                                    root: {treeData.root} • scanned: {treeData.scanned}
                                    {treeData.truncated ? ' • truncated' : ''}
                                </p>
                                <RepoTreeNodeView
                                    node={treeData.tree}
                                    selectedFile={selectedFile}
                                    onOpenFile={openFile}
                                    depth={0}
                                />
                            </>
                        )}
                    </div>
                    {advancedMode && (
                        <div className="border-t border-surface-3 p-3 h-[220px] md:h-[38%] min-h-[160px] overflow-auto">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">File Preview</p>
                            <p className="text-[11px] text-text-muted mt-1 truncate">{selectedFile || 'No file selected'}</p>
                            <pre className="mt-2 text-xs text-text-primary whitespace-pre-wrap bg-surface-0 border border-surface-3 rounded-btn p-2 max-h-[240px] overflow-auto">
                                {loadingFile ? 'Loading file...' : (selectedFileContent || 'Select a file to preview.')}
                            </pre>
                        </div>
                    )}
                </aside>

                <main className="flex flex-col gap-4 overflow-auto md:min-h-0 md:pr-1">
                    <section className="rounded-card border border-surface-3 bg-surface-1 p-4 md:p-5">
                        <div className="flex items-center justify-between gap-2">
                            <div>
                                <h1 className="text-base font-semibold text-text-primary">App Builder Workspace</h1>
                                <p className="text-[11px] text-text-secondary">
                                    Prompt the build and monitor progress. New apps are saved to {APP_CREATIONS_DIR}.
                                </p>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="text-xs text-text-secondary">
                                    run: {runId ? `${runId.slice(0, 8)} • ${runStatus || 'running'}` : 'none'}
                                </div>
                                <button
                                    type="button"
                                    onClick={() => setAdvancedMode((prev) => !prev)}
                                    className={`px-2.5 py-1.5 rounded-btn border text-xs ${
                                        advancedMode
                                            ? 'border-accent/40 text-accent bg-accent/10'
                                            : 'border-surface-4 text-text-secondary hover:bg-surface-2'
                                    }`}
                                >
                                    {advancedMode ? 'Advanced: ON' : 'Simple: ON'}
                                </button>
                            </div>
                        </div>
                        <div className="mt-4 grid md:grid-cols-2 gap-3">
                            <div>
                                <p className="text-[11px] uppercase tracking-wide text-text-secondary mb-1">Build Prompt (Editable)</p>
                                <textarea
                                    rows={4}
                                    value={prompt}
                                    onChange={(e) => setPrompt(e.target.value)}
                                    className="builder-input w-full bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-xs text-text-primary"
                                    placeholder="Describe the app to build..."
                                />
                            </div>
                            <div>
                                <p className="text-[11px] uppercase tracking-wide text-text-secondary mb-1">Context (Editable)</p>
                                <textarea
                                    rows={4}
                                    value={context}
                                    onChange={(e) => setContext(e.target.value)}
                                    className="builder-input w-full bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-xs text-text-primary"
                                    placeholder="Optional implementation context..."
                                />
                            </div>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                            <button
                                type="button"
                                disabled={loadingLaunch}
                                onClick={launchBuild}
                                className="px-3 py-2 rounded-btn border border-accent-green/40 text-accent-green text-xs disabled:opacity-40 flex items-center gap-1.5"
                            >
                                {loadingLaunch && (
                                    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
                                )}
                                {loadingLaunch ? 'Launching...' : 'Start Autonomous Build'}
                            </button>
                            <button
                                type="button"
                                disabled={!runId || loadingStop}
                                onClick={stopBuild}
                                className="px-3 py-2 rounded-btn border border-accent-red/40 text-accent-red text-xs disabled:opacity-40"
                            >
                                {loadingStop ? 'Stopping...' : 'Stop Build'}
                            </button>
                            <button
                                type="button"
                                onClick={() => refreshRuns().catch(() => {})}
                                className="px-3 py-2 rounded-btn border border-accent/40 text-accent text-xs"
                            >
                                Refresh Runs
                            </button>
                            {loadingPreview && <span className="text-xs text-text-muted self-center">previewing agents...</span>}
                            {!loadingPreview && preview && (
                                <span className="text-xs text-text-muted self-center">
                                    agents: {preview.team_agent_count} • complexity: {preview.complexity?.level || 'n/a'}
                                </span>
                            )}
                            {!advancedMode && (
                                <span className="text-xs text-text-muted self-center">
                                    Simple mode hides terminal/export/manual orchestration.
                                </span>
                            )}
                        </div>
                        <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-3">
                            <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                <p className="text-[11px] uppercase tracking-wide text-text-secondary">What Builder Will Do</p>
                                <div className="mt-2 space-y-1 text-xs text-text-secondary">
                                    <p>1. Interpret your prompt and choose an agent plan.</p>
                                    <p>2. Auto-select skills that fit the build objective.</p>
                                    <p>3. Research when the task needs current or external information.</p>
                                    <p>4. Write changes into the repo and surface them in Review.</p>
                                </div>
                                {preview && (
                                    <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                                        <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">
                                            {preview.team_agent_count} agents
                                        </span>
                                        <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">
                                            complexity {preview.complexity?.level || 'n/a'}
                                        </span>
                                        <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">
                                            saved teams {preview.used_saved_teams.length}
                                        </span>
                                    </div>
                                )}
                            </div>
                            <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                <p className="text-[11px] uppercase tracking-wide text-text-secondary">Auto-Selected Skills</p>
                                <div className="mt-2 min-h-[58px]">
                                    {loadingRecommendedSkills && (
                                        <p className="text-xs text-text-muted">matching skills to objective...</p>
                                    )}
                                    {!loadingRecommendedSkills && recommendedSkills.length === 0 && (
                                        <p className="text-xs text-text-secondary">No skill recommendations yet. Start describing the app and jimAI will infer them automatically.</p>
                                    )}
                                    {!loadingRecommendedSkills && recommendedSkills.length > 0 && (
                                        <div className="flex flex-wrap gap-2">
                                            {recommendedSkills.slice(0, 8).map((skill) => (
                                                <span
                                                    key={skill.slug}
                                                    className="rounded-full border border-accent/30 bg-accent/10 px-2 py-1 text-[11px] text-accent"
                                                    title={skill.description}
                                                >
                                                    {skill.name}
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                {advancedMode && recommendedSkillContext && (
                                    <details className="mt-3">
                                        <summary className="cursor-pointer text-[11px] text-text-primary">Skill context preview</summary>
                                        <pre className="mt-2 max-h-36 overflow-auto rounded-btn border border-surface-3 bg-surface-1 p-2 text-[10px] text-text-secondary whitespace-pre-wrap">
                                            {recommendedSkillContext}
                                        </pre>
                                    </details>
                                )}
                            </div>
                            <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                <p className="text-[11px] uppercase tracking-wide text-text-secondary">Auto Decisions</p>
                                <div className="mt-2 space-y-2 text-xs text-text-secondary">
                                    {optionHelpEntries.length === 0 && (
                                        <p>Builder decisions appear here once the prompt preview is ready.</p>
                                    )}
                                    {optionHelpEntries.slice(0, 5).map(([key, value]) => (
                                        <div key={key}>
                                            <p className="text-text-primary">{humanizeOptionKey(key)}</p>
                                            <p>{String(value || '')}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                        <div className="mt-3 rounded-btn border border-surface-3 bg-surface-0 p-3">
                            <div className="flex flex-wrap items-center gap-2 text-xs">
                                <span className="text-text-secondary">Connected workspace:</span>
                                <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">
                                    team {sharedSavedTeamName || sharedTeamName || 'Auto Build Team'}
                                </span>
                                {sharedSelectedSkills.slice(0, 4).map((skill) => (
                                    <span key={skill.slug} className="rounded-full border border-accent/30 bg-accent/10 px-2 py-1 text-accent">
                                        {skill.name}
                                    </span>
                                ))}
                                {(sharedLastRunId || sharedSavedTeamId) && (
                                    <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">
                                        {sharedSavedTeamId ? `saved ${sharedSavedTeamId.slice(0, 8)} · ` : ''}
                                        {sharedLastRunId ? `last run ${sharedLastRunStatus || 'unknown'} · ${sharedLastRunId.slice(0, 8)}` : 'team connected'}
                                    </span>
                                )}
                            </div>
                            <p className="mt-2 text-[11px] text-text-muted">
                                Agent Studio saves the active team and selected skills here automatically so Builder can reuse them.
                            </p>
                        </div>
                    </section>

                    <section className="md:flex-1 md:min-h-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_280px] gap-4 overflow-visible">
                        <div className="rounded-card border border-surface-3 bg-surface-1 p-4 md:min-h-0 flex flex-col">
                            <p className="text-sm font-semibold text-text-primary">Live Run Events</p>
                            <div className="mt-3 flex-1 overflow-auto space-y-2 md:min-h-0">
                                {events.length === 0 && <p className="text-xs text-text-secondary">No events yet.</p>}
                                {events.map((evt, idx) => (
                                    <div key={`${idx}-${evt.type}`} className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                                        <p className="text-[11px] text-text-primary">{evt.type}</p>
                                        <p className="text-[11px] text-text-secondary">{String(evt.message || '')}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="rounded-card border border-surface-3 bg-surface-1 p-4 md:min-h-0 flex flex-col">
                            <p className="text-sm font-semibold text-text-primary">Recent Runs</p>
                            <div className="mt-2 flex-1 overflow-auto space-y-2 md:min-h-0">
                                {runs.map((row) => (
                                    <button
                                        key={row.id}
                                        type="button"
                                        onClick={() => {
                                            setRunId(row.id);
                                            setRunStatus(row.status);
                                            setEvents([]);
                                        }}
                                        className={`w-full text-left rounded-btn border p-2 ${
                                            runId === row.id ? 'border-accent/50 bg-surface-2' : 'border-surface-3 bg-surface-0'
                                        }`}
                                    >
                                        <p className="text-xs text-text-primary truncate">{row.objective}</p>
                                        <p className="text-[11px] text-text-secondary mt-1">{row.status} • actions {row.action_count}</p>
                                    </button>
                                ))}
                            </div>
                        </div>
                    </section>

                    {advancedMode && (
                        <section className="rounded-card border border-surface-3 bg-surface-1 p-4 min-h-[280px] md:min-h-[220px] flex flex-col">
                            <p className="text-sm font-semibold text-text-primary">Terminal</p>
                            <p className="text-[11px] text-text-secondary">Run repository commands with policy/profile gates.</p>
                            <div className="mt-2 grid grid-cols-1 md:grid-cols-[160px_minmax(0,1fr)_120px] gap-2">
                                <input
                                    value={terminalCwd}
                                    onChange={(e) => setTerminalCwd(e.target.value)}
                                    className="builder-input bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                                    placeholder="cwd"
                                />
                                <input
                                    value={terminalCommand}
                                    onChange={(e) => setTerminalCommand(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') runTerminalCommand().catch(() => {});
                                    }}
                                    className="builder-input bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                                    placeholder="npm test"
                                />
                                <button
                                    type="button"
                                    onClick={() => runTerminalCommand().catch(() => {})}
                                    disabled={runningTerminal}
                                    className="px-3 py-1.5 rounded-btn border border-accent/40 text-accent text-xs disabled:opacity-40"
                                >
                                    {runningTerminal ? 'Running...' : 'Run'}
                                </button>
                            </div>
                            <div className="mt-2 flex-1 overflow-auto space-y-2 md:min-h-0">
                                {terminalRows.length === 0 && <p className="text-xs text-text-secondary">No terminal output yet.</p>}
                                {terminalRows.map((row) => (
                                    <div key={row.id} className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                                        <p className="text-[11px] text-text-primary">
                                            {row.cwd} $ {row.command}
                                        </p>
                                        <p className={`text-[11px] mt-1 ${row.exitCode === 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                                            exit_code: {row.exitCode}
                                        </p>
                                        {row.stdout && (
                                            <pre className="mt-1 text-[11px] text-text-secondary whitespace-pre-wrap">{row.stdout}</pre>
                                        )}
                                        {row.stderr && (
                                            <pre className="mt-1 text-[11px] text-accent-red whitespace-pre-wrap">{row.stderr}</pre>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    {advancedMode && (
                        <section className="rounded-card border border-surface-3 bg-surface-1 p-4 md:p-5">
                            <p className="text-sm font-semibold text-text-primary">Export App</p>
                            <p className="text-[11px] text-text-secondary mt-1">
                                Export built app folders for separate repos/deploy pipelines.
                            </p>
                            <div className="mt-3 grid md:grid-cols-[260px_minmax(0,1fr)_120px] gap-2">
                                <input
                                    value={exportTarget}
                                    onChange={(e) => setExportTarget(e.target.value)}
                                    className="builder-input bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                                    placeholder="target folder"
                                />
                                <textarea
                                    rows={2}
                                    value={exportPaths}
                                    onChange={(e) => setExportPaths(e.target.value)}
                                    className="builder-input bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                                    placeholder="one include path per line"
                                />
                                <button
                                    type="button"
                                    onClick={() => exportBuildOutput().catch(() => {})}
                                    disabled={exporting}
                                    className="px-3 py-1.5 rounded-btn border border-accent/40 text-accent text-xs disabled:opacity-40"
                                >
                                    {exporting ? 'Exporting...' : 'Export'}
                                </button>
                            </div>
                        </section>
                    )}
                </main>

                <aside className="rounded-card border border-surface-3 bg-surface-1 flex flex-col overflow-hidden md:min-h-0">
                    <div className="px-4 py-3 border-b border-surface-3">
                        <p className="text-sm font-semibold text-text-primary">Agent Panel</p>
                        <p className="text-[11px] text-text-secondary">Orchestrate agents, inspect levels, and send control messages.</p>
                    </div>
                    <div className="p-3 border-b border-surface-3">
                        <div className="grid grid-cols-3 gap-2 text-[11px]">
                            <div className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                                <p className="text-text-muted">Agents</p>
                                <p className="text-text-primary">{visualNodes.length || 0}</p>
                            </div>
                            <div className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                                <p className="text-text-muted">Run</p>
                                <p className="text-text-primary">{runStatus || 'idle'}</p>
                            </div>
                            <div className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                                <p className="text-text-muted">Messages</p>
                                <p className="text-text-primary">{messageFlow.length}</p>
                            </div>
                        </div>
                    </div>
                    {advancedMode && (
                        <div className="p-3 border-b border-surface-3 space-y-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Orchestrate (Editable)</p>
                            <select
                                value={agentTo}
                                onChange={(e) => setAgentTo(e.target.value)}
                                className="builder-input w-full bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                            >
                                <option value="">All / Planner</option>
                                {agentIds.map((id) => (
                                    <option key={id} value={id}>{id}</option>
                                ))}
                            </select>
                            <select
                                value={agentChannel}
                                onChange={(e) => setAgentChannel(e.target.value)}
                                className="builder-input w-full bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                            >
                                <option value="change-request">change-request</option>
                                <option value="handoff">handoff</option>
                                <option value="verification">verification</option>
                                <option value="general">general</option>
                            </select>
                            <textarea
                                rows={3}
                                value={agentMessage}
                                onChange={(e) => setAgentMessage(e.target.value)}
                                className="builder-input w-full bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                                placeholder="Tell agents what to modify, prioritize, or validate..."
                            />
                            <button
                                type="button"
                                disabled={!runId || sendingAgentMessage}
                                onClick={() => sendAgentControl().catch(() => {})}
                                className="w-full px-3 py-2 rounded-btn border border-accent/40 text-accent text-xs disabled:opacity-40"
                            >
                                {sendingAgentMessage ? 'Sending...' : 'Send Orchestration Message'}
                            </button>
                        </div>
                    )}
                    <div className="flex-1 overflow-auto p-3 space-y-3 md:min-h-0">
                        <p className="text-[11px] uppercase tracking-wide text-text-secondary">Agents & Levels</p>
                        {visualNodes.length === 0 && <p className="text-xs text-text-secondary">No agent plan yet.</p>}
                        {visualNodes.map((node) => (
                            <div key={node.id} className={`rounded-btn border p-2 ${statusTone(node.status || 'idle')}`}>
                                <p className="text-xs text-text-primary">{node.id}</p>
                                <p className="text-[11px] text-text-secondary mt-1">
                                    {node.role} • L{node.workerLevel}
                                </p>
                                {node.dependsOn.length > 0 && (
                                    <p className="text-[11px] text-text-muted mt-1">depends: {node.dependsOn.join(', ')}</p>
                                )}
                            </div>
                        ))}
                        {advancedMode && (
                            <>
                                <p className="text-[11px] uppercase tracking-wide text-text-secondary pt-2">Agent Messages</p>
                                {messageFlow.length === 0 && <p className="text-xs text-text-secondary">No agent messages yet.</p>}
                                {messageFlow.map((row, idx) => (
                                    <div key={`${idx}-${row.from}-${row.to}`} className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                                        <p className="text-[11px] text-text-secondary">
                                            {row.from} {'->'} {row.to} [{row.channel}]
                                        </p>
                                    </div>
                                ))}
                            </>
                        )}
                    </div>
                </aside>
            </div>
            {message && <p className="mt-2 text-sm text-accent-green">{message}</p>}
            {error && <p className="mt-2 text-sm text-accent-red">{error}</p>}
        </div>
    );
}

function RepoTreeNodeView({
    node,
    selectedFile,
    onOpenFile,
    depth,
}: {
    node: agentApi.RepoTreeNode;
    selectedFile: string;
    onOpenFile: (path: string) => void;
    depth: number;
}) {
    if (node.type === 'file') {
        return (
            <button
                type="button"
                onClick={() => onOpenFile(node.path)}
                className={`block w-full text-left text-xs rounded-btn px-2 py-1 ${
                    selectedFile === node.path ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:bg-surface-2'
                }`}
                style={{ paddingLeft: `${depth * 12 + 8}px` }}
            >
                {node.name}
            </button>
        );
    }

    const children = Array.isArray(node.children) ? node.children : [];
    return (
        <details open={depth < 1} className="mb-0.5">
            <summary className="cursor-pointer text-xs text-text-primary select-none" style={{ paddingLeft: `${depth * 12 + 6}px` }}>
                {node.name}
            </summary>
            <div className="mt-0.5">
                {children.map((child) => (
                    <RepoTreeNodeView
                        key={`${child.path}-${child.name}`}
                        node={child}
                        selectedFile={selectedFile}
                        onOpenFile={onOpenFile}
                        depth={depth + 1}
                    />
                ))}
            </div>
        </details>
    );
}
