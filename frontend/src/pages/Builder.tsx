import { useCallback, useEffect, useMemo, useState } from 'react';
import Editor, { DiffEditor } from '@monaco-editor/react';
import { Bot, Files, GitBranch, Search, Terminal } from 'lucide-react';
import * as agentApi from '../lib/agentSpaceApi';
import GitHubPanel from '../components/GitHubPanel';
import { cn, readSharedWorkspaceDraft, writeSharedWorkspaceDraft } from '../lib/utils';

type NodeStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed';
type PendingCreate = { parentPath: string; kind: 'file' | 'folder'; value: string };
type TerminalRow = { id: string; command: string; cwd: string; exitCode: number; stdout: string; stderr: string; timestamp: number };
type FlowNode = { id: string; role: string; workerLevel: number; dependsOn: string[]; description?: string; status?: NodeStatus };
type FileTab = { id: string; type: 'file'; title: string; path: string; content: string; dirty: boolean; language: string };
type DiffTab = { id: string; type: 'diff'; title: string; path: string; reviewId: string; reviewStatus: string; original: string; modified: string };
type Tab = FileTab | DiffTab;

const detectLanguage = (path: string) => {
    const lower = path.toLowerCase();
    if (lower.endsWith('.tsx') || lower.endsWith('.ts')) return 'typescript';
    if (lower.endsWith('.jsx') || lower.endsWith('.js')) return 'javascript';
    if (lower.endsWith('.py')) return 'python';
    if (lower.endsWith('.json')) return 'json';
    if (lower.endsWith('.md')) return 'markdown';
    if (lower.endsWith('.html')) return 'html';
    if (lower.endsWith('.css')) return 'css';
    if (lower.endsWith('.yml') || lower.endsWith('.yaml')) return 'yaml';
    return 'plaintext';
};
const normalizeProfile = (value: unknown): 'safe' | 'dev' | 'unrestricted' => (value === 'dev' || value === 'unrestricted' ? value : 'safe');
const joinRepoPath = (parentPath: string, childName: string) => (parentPath && parentPath !== '.' ? `${parentPath}/${childName}` : childName).replace(/\\/g, '/');
const parentDirectory = (path: string) => {
    const parts = String(path || '').replace(/\\/g, '/').split('/');
    parts.pop();
    return parts.filter(Boolean).join('/') || '.';
};

function filterRepoTree(node: agentApi.RepoTreeNode, q: string): agentApi.RepoTreeNode | null {
    const needle = q.trim().toLowerCase();
    if (!needle) return node;
    if (node.type === 'file') {
        return node.name.toLowerCase().includes(needle) || node.path.toLowerCase().includes(needle) ? node : null;
    }
    const rawKids = node.children || [];
    const mapped = rawKids.map((c) => filterRepoTree(c, q)).filter((c): c is agentApi.RepoTreeNode => c != null);
    if (mapped.length) return { ...node, children: mapped };
    if (node.name.toLowerCase().includes(needle) || node.path.toLowerCase().includes(needle)) return { ...node, children: rawKids };
    return null;
}
const formatTime = (ts?: number) => (ts ? new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '--:--:--');
const statusTone = (status: NodeStatus) => status === 'running' ? 'border-accent/40 bg-accent/10' : status === 'completed' ? 'border-accent-green/40 bg-accent-green/10' : status === 'failed' ? 'border-accent-red/40 bg-accent-red/10' : 'border-surface-3 bg-surface-1';

function parseSubagentId(message: string, type: string) {
    if (!message) return '';
    if (type === 'subagent.started') return message.match(/Starting\s+([^\s]+)/i)?.[1] || '';
    if (type === 'subagent.completed') return message.match(/(?:Planner|Tester|Verifier|Subagent)\s+([^\s]+)\s+completed/i)?.[1] || '';
    if (type === 'subagent.error') return message.match(/Subagent\s+([^\s]+)\s+failed/i)?.[1] || '';
    return '';
}

function extractWorkflowNodes(events: agentApi.AgentSpaceEvent[]): FlowNode[] {
    for (let i = events.length - 1; i >= 0; i -= 1) {
        const evt = events[i];
        if (evt.type !== 'run.workflow') continue;
        const rows = Array.isArray((evt.data as { subagents?: unknown })?.subagents) ? (evt.data as { subagents?: Array<Record<string, unknown>> }).subagents || [] : [];
        return rows
            .map((row) => ({
                id: String(row.id || '').trim(),
                role: String(row.role || 'coder'),
                workerLevel: Number(row.worker_level || 1) || 1,
                dependsOn: Array.isArray(row.depends_on) ? row.depends_on.map((dep) => String(dep || '').trim()).filter(Boolean) : [],
                description: String(row.description || ''),
            }))
            .filter((row) => row.id);
    }
    return [];
}

function buildDiffTab(review: agentApi.AgentSpaceReview, path: string): DiffTab | null {
    const change = (review.changes || []).find((row) => row.path === path) || review.changes?.[0];
    if (!change) return null;
    return {
        id: `review:${review.id}:${path}`,
        type: 'diff',
        title: `${path.split('/').pop() || path} · diff`,
        path,
        reviewId: review.id,
        reviewStatus: review.status,
        original: String(change.old_content || ''),
        modified: String(change.new_content || ''),
    };
}

export default function Builder() {
    const [prompt, setPrompt] = useState('');
    const [context, setContext] = useState('');
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [settings, setSettings] = useState<Record<string, unknown>>({});
    const [preview, setPreview] = useState<agentApi.BuilderPreviewResponse | null>(null);
    const [loadingPreview, setLoadingPreview] = useState(false);
    const [loadingLaunch, setLoadingLaunch] = useState(false);
    const [loadingStop, setLoadingStop] = useState(false);
    const [runId, setRunId] = useState('');
    const [runStatus, setRunStatus] = useState('');
    const [runs, setRuns] = useState<agentApi.AgentSpaceRunSummary[]>([]);
    const [events, setEvents] = useState<agentApi.AgentSpaceEvent[]>([]);
    const [runReviews, setRunReviews] = useState<agentApi.AgentSpaceReview[]>([]);
    const [loadingReviews, setLoadingReviews] = useState(false);
    const [sharedTeamName, setSharedTeamName] = useState('Auto Build Team');
    const [sharedSavedTeamId, setSharedSavedTeamId] = useState('');
    const [sharedSavedTeamName, setSharedSavedTeamName] = useState('');
    const [sharedSelectedSkills, setSharedSelectedSkills] = useState<Array<{ slug: string; name: string }>>([]);
    const [sharedLastRunId, setSharedLastRunId] = useState('');
    const [sharedLastRunStatus, setSharedLastRunStatus] = useState('');
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [sidebarTab, setSidebarTab] = useState<'explorer' | 'search' | 'source-control'>('explorer');
    const [rightPanelOpen, setRightPanelOpen] = useState(true);
    const [bottomPanelOpen, setBottomPanelOpen] = useState(true);
    const [showGitHubModal, setShowGitHubModal] = useState(false);
    const [sidebarSearchQuery, setSidebarSearchQuery] = useState('');
    const [recommendedSkills, setRecommendedSkills] = useState<agentApi.AgentSkillSummary[]>([]);
    const [recommendedSkillContext, setRecommendedSkillContext] = useState('');
    const [loadingRecommendedSkills, setLoadingRecommendedSkills] = useState(false);
    const [treeData, setTreeData] = useState<agentApi.RepoTreeResponse | null>(null);
    const [loadingTree, setLoadingTree] = useState(false);
    const [selectedDirectory, setSelectedDirectory] = useState('.');
    const [pendingCreate, setPendingCreate] = useState<PendingCreate | null>(null);
    const [creatingNode, setCreatingNode] = useState(false);
    const [tabs, setTabs] = useState<Tab[]>([]);
    const [activeTabId, setActiveTabId] = useState('');
    const [loadingFile, setLoadingFile] = useState(false);
    const [savingFile, setSavingFile] = useState(false);
    const [editorWriteMode, setEditorWriteMode] = useState<'direct' | 'review'>('review');
    const [terminalCwd, setTerminalCwd] = useState('.');
    const [terminalCommand, setTerminalCommand] = useState('');
    const [terminalRows, setTerminalRows] = useState<TerminalRow[]>([]);
    const [runningTerminal, setRunningTerminal] = useState(false);
    const [agentTo, setAgentTo] = useState('');
    const [agentChannel, setAgentChannel] = useState('change-request');
    const [agentMessage, setAgentMessage] = useState('');
    const [sendingAgentMessage, setSendingAgentMessage] = useState(false);

    const currentRun = useMemo(() => runs.find((row) => row.id === runId) || null, [runId, runs]);
    const activeTab = useMemo(() => tabs.find((tab) => tab.id === activeTabId) || null, [activeTabId, tabs]);

    const refreshRuns = useCallback(async () => {
        const rows = await agentApi.listRuns(50);
        setRuns(rows);
        const current = rows.find((row) => row.id === runId);
        if (current) setRunStatus(current.status);
    }, [runId]);

    const refreshTree = useCallback(async () => {
        setLoadingTree(true);
        try {
            setTreeData(await agentApi.listRepoTree('.', 12, 30000, false));
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load file tree.');
        } finally {
            setLoadingTree(false);
        }
    }, []);

    useEffect(() => {
        const shared = readSharedWorkspaceDraft();
        if (shared.prompt) setPrompt(String(shared.prompt));
        if (shared.context) setContext(String(shared.context));
        if (shared.teamName) setSharedTeamName(String(shared.teamName));
        if (shared.savedTeamId) setSharedSavedTeamId(String(shared.savedTeamId));
        if (shared.savedTeamName) setSharedSavedTeamName(String(shared.savedTeamName));
        if (Array.isArray(shared.selectedSkills)) setSharedSelectedSkills(shared.selectedSkills.map((row) => ({ slug: String(row.slug || ''), name: String(row.name || '') })).filter((row) => row.slug));
        if (shared.lastRunId) setSharedLastRunId(String(shared.lastRunId));
        if (shared.lastRunStatus) setSharedLastRunStatus(String(shared.lastRunStatus));
    }, []);

    useEffect(() => {
        const onStorage = () => {
            const shared = readSharedWorkspaceDraft();
            setSharedTeamName(String(shared.teamName || 'Auto Build Team'));
            setSharedSavedTeamId(String(shared.savedTeamId || ''));
            setSharedSavedTeamName(String(shared.savedTeamName || ''));
            setSharedSelectedSkills(Array.isArray(shared.selectedSkills) ? shared.selectedSkills.map((row) => ({ slug: String(row.slug || ''), name: String(row.name || '') })).filter((row) => row.slug) : []);
            setSharedLastRunId(String(shared.lastRunId || ''));
            setSharedLastRunStatus(String(shared.lastRunStatus || ''));
        };
        window.addEventListener('storage', onStorage);
        return () => window.removeEventListener('storage', onStorage);
    }, []);

    useEffect(() => {
        agentApi.getSettings().then(setSettings).catch((err) => setError(err instanceof Error ? err.message : 'Failed to load settings.'));
        refreshRuns().catch(() => undefined);
        refreshTree().catch(() => undefined);
    }, [refreshRuns, refreshTree]);

    useEffect(() => {
        setEditorWriteMode(Boolean(settings.review_gate ?? true) ? 'review' : 'direct');
    }, [settings.review_gate]);

    useEffect(() => {
        const timer = window.setInterval(() => refreshRuns().catch(() => undefined), 2500);
        return () => window.clearInterval(timer);
    }, [refreshRuns]);

    useEffect(() => {
        writeSharedWorkspaceDraft({
            prompt,
            context,
            teamName: sharedSavedTeamName || sharedTeamName || 'Auto Build Team',
            selectedSkills: sharedSelectedSkills,
        });
    }, [context, prompt, sharedSavedTeamName, sharedSelectedSkills, sharedTeamName]);

    useEffect(() => {
        if (!runId) return;
        return agentApi.subscribeRunEvents(runId, (event) => setEvents((prev) => [...prev.slice(-499), event]), () => undefined);
    }, [runId]);

    useEffect(() => {
        if (prompt.trim().length < 3) {
            setPreview(null);
            return;
        }
        let active = true;
        setLoadingPreview(true);
        const timer = window.setTimeout(() => {
            agentApi.builderPreview({
                prompt: prompt.trim(),
                context: context.trim(),
                team_name: sharedSavedTeamName || sharedTeamName || 'Auto Build Team',
                auto_agent_packs: true,
                use_saved_teams: true,
            }).then((data) => active && setPreview(data)).catch(() => active && setPreview(null)).finally(() => active && setLoadingPreview(false));
        }, 400);
        return () => {
            active = false;
            window.clearTimeout(timer);
        };
    }, [context, prompt, sharedSavedTeamName, sharedTeamName]);

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
        const timer = window.setTimeout(() => {
            agentApi.selectSkills({ objective, limit: 8, include_context: true })
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
                .finally(() => active && setLoadingRecommendedSkills(false));
        }, 450);
        return () => {
            active = false;
            window.clearTimeout(timer);
        };
    }, [context, prompt]);

    useEffect(() => {
        const reviewIds = currentRun?.review_ids || [];
        if (!runId || reviewIds.length === 0) {
            setRunReviews([]);
            return;
        }
        let active = true;
        setLoadingReviews(true);
        Promise.all(reviewIds.slice(-6).map((reviewId) => agentApi.getReview(reviewId)))
            .then((rows) => active && setRunReviews(rows))
            .catch(() => active && setRunReviews([]))
            .finally(() => active && setLoadingReviews(false));
        return () => {
            active = false;
        };
    }, [currentRun, runId]);

    const upsertTab = useCallback((nextTab: Tab, activate = true) => {
        setTabs((prev) => {
            const idx = prev.findIndex((tab) => tab.id === nextTab.id);
            if (idx === -1) return [...prev, nextTab];
            const clone = [...prev];
            clone[idx] = nextTab;
            return clone;
        });
        if (activate) setActiveTabId(nextTab.id);
    }, []);

    const openFile = useCallback(async (path: string) => {
        if (!path || path === '.') return;
        setLoadingFile(true);
        setError('');
        try {
            const row = await agentApi.toolsRead(path);
            upsertTab({
                id: `file:${row.path}`,
                type: 'file',
                title: row.path.split('/').pop() || row.path,
                path: row.path,
                content: row.content || '',
                dirty: false,
                language: detectLanguage(row.path),
            }, true);
            setSelectedDirectory(parentDirectory(row.path));
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to open file.');
        } finally {
            setLoadingFile(false);
        }
    }, [upsertTab]);

    const openReviewDiff = useCallback((review: agentApi.AgentSpaceReview, path: string) => {
        const tab = buildDiffTab(review, path);
        if (tab) upsertTab(tab, true);
    }, [upsertTab]);

    const updateActiveTabContent = useCallback((content: string) => {
        setTabs((prev) => prev.map((tab) => tab.id === activeTabId && tab.type === 'file' ? { ...tab, content, dirty: true } : tab));
    }, [activeTabId]);

    const closeTab = useCallback((tabId: string) => {
        setTabs((prev) => {
            const next = prev.filter((tab) => tab.id !== tabId);
            if (activeTabId === tabId) setActiveTabId(next[next.length - 1]?.id || '');
            return next;
        });
    }, [activeTabId]);

    const handleWriteResult = useCallback(async (result: agentApi.ToolWriteResult, options: { path: string; content: string; successMessage: string; reviewMessage: string }) => {
        if (result.mode === 'review' && result.review) {
            const review = result.review;
            setRunReviews((prev) => {
                const withoutCurrent = prev.filter((row) => row.id !== review.id);
                return [review, ...withoutCurrent];
            });
            openReviewDiff(review, options.path);
            setTabs((prev) => prev.map((tab) => tab.id === `file:${options.path}` && tab.type === 'file' ? { ...tab, content: options.content, dirty: false } : tab));
            setMessage(options.reviewMessage);
            return;
        }
        setTabs((prev) => prev.map((tab) => tab.id === `file:${options.path}` && tab.type === 'file' ? { ...tab, content: options.content, dirty: false } : tab));
        await refreshTree();
        setMessage(options.successMessage);
    }, [openReviewDiff, refreshTree]);

    const saveActiveFile = useCallback(async () => {
        if (!activeTab || activeTab.type !== 'file') return;
        setSavingFile(true);
        setMessage('');
        setError('');
        try {
            const result = await agentApi.toolsWrite({
                path: activeTab.path,
                content: activeTab.content,
                review_gate: editorWriteMode === 'review',
            });
            await handleWriteResult(result, {
                path: activeTab.path,
                content: activeTab.content,
                successMessage: `Saved ${activeTab.path}.`,
                reviewMessage: `Submitted ${activeTab.path} for review.`,
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to save file.');
        } finally {
            setSavingFile(false);
        }
    }, [activeTab, editorWriteMode, handleWriteResult]);

    const createWorkspaceNode = useCallback(async () => {
        if (!pendingCreate) return;
        const name = pendingCreate.value.trim();
        if (!name) {
            setError(`Enter a ${pendingCreate.kind} name first.`);
            return;
        }
        const nextPath = joinRepoPath(pendingCreate.parentPath, name);
        setCreatingNode(true);
        setMessage('');
        setError('');
        try {
            if (pendingCreate.kind === 'folder') {
                await agentApi.createWorkspaceDirectory(nextPath);
                setSelectedDirectory(nextPath);
                setMessage(`Created folder ${nextPath}.`);
            } else {
                const result = await agentApi.toolsWrite({
                    path: nextPath,
                    content: '',
                    review_gate: editorWriteMode === 'review',
                });
                setSelectedDirectory(parentDirectory(nextPath));
                await handleWriteResult(result, {
                    path: nextPath,
                    content: '',
                    successMessage: `Created file ${nextPath}.`,
                    reviewMessage: `Submitted new file ${nextPath} for review.`,
                });
                if (result.mode !== 'review') {
                    await openFile(nextPath);
                } else {
                    upsertTab({
                        id: `file:${nextPath}`,
                        type: 'file',
                        title: nextPath.split('/').pop() || nextPath,
                        path: nextPath,
                        content: '',
                        dirty: false,
                        language: detectLanguage(nextPath),
                    }, true);
                }
            }
            setPendingCreate(null);
            await refreshTree();
        } catch (err) {
            setError(err instanceof Error ? err.message : `Failed to create ${pendingCreate.kind}.`);
        } finally {
            setCreatingNode(false);
        }
    }, [editorWriteMode, handleWriteResult, openFile, pendingCreate, refreshTree, upsertTab]);

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
            const skillNames = sharedSelectedSkills.map((skill) => skill.name).filter(Boolean);
            const finalContext = skillNames.length ? [context.trim(), `Preferred skills from Agent Studio:\n- ${skillNames.join('\n- ')}`].filter(Boolean).join('\n\n') : context.trim();
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
            writeSharedWorkspaceDraft({
                prompt: cleanPrompt,
                context,
                teamName: sharedSavedTeamName || sharedTeamName || 'Auto Build Team',
                savedTeamId: sharedSavedTeamId,
                savedTeamName: sharedSavedTeamName || sharedTeamName || 'Auto Build Team',
                selectedSkills: sharedSelectedSkills,
                lastRunId: response.run.id,
                lastRunStatus: response.run.status,
                lastRunObjective: cleanPrompt,
            });
            setMessage(`Build run started: ${response.run.id}.`);
            await refreshRuns();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start build run.');
        } finally {
            setLoadingLaunch(false);
        }
    }, [context, prompt, refreshRuns, settings.allow_shell, settings.command_profile, settings.continue_on_subagent_failure, settings.review_gate, sharedSavedTeamId, sharedSavedTeamName, sharedSelectedSkills, sharedTeamName]);

    const stopBuild = useCallback(async () => {
        if (!runId) return;
        setLoadingStop(true);
        setError('');
        setMessage('');
        try {
            await agentApi.stopRun(runId, 'Stopped from Builder IDE.');
            setRunStatus('stopped');
            setSharedLastRunStatus('stopped');
            setMessage(`Run ${runId} stop requested.`);
            await refreshRuns();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to stop run.');
        } finally {
            setLoadingStop(false);
        }
    }, [refreshRuns, runId]);

    const sendAgentControl = useCallback(async () => {
        if (!agentMessage.trim()) {
            setError('Enter an agent task or instruction first.');
            return;
        }
        if (!runId) {
            setError('No active run selected.');
            return;
        }
        setSendingAgentMessage(true);
        setError('');
        setMessage('');
        try {
            await agentApi.postRunMessage(runId, {
                from_agent: 'user',
                to_agent: agentTo.trim(),
                channel: agentChannel.trim() || 'general',
                content: agentMessage.trim(),
            });
            setAgentMessage('');
            setMessage(`Sent ${agentChannel} message to ${agentTo || 'agent team'}.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send agent instruction.');
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
            const result = await agentApi.toolsShell({ command, cwd: terminalCwd.trim() || '.', profile: normalizeProfile(settings.command_profile), timeout: 180 });
            setTerminalRows((prev) => [{
                id: `${Date.now()}-${Math.random()}`,
                command,
                cwd: terminalCwd.trim() || '.',
                exitCode: Number(result.exit_code ?? (result.success ? 0 : -1)),
                stdout: String(result.stdout || ''),
                stderr: String(result.stderr || ''),
                timestamp: Date.now(),
            }, ...prev].slice(0, 120));
            setTerminalCommand('');
        } catch (err) {
            setTerminalRows((prev) => [{
                id: `${Date.now()}-${Math.random()}`,
                command,
                cwd: terminalCwd.trim() || '.',
                exitCode: -1,
                stdout: '',
                stderr: err instanceof Error ? err.message : 'Terminal command failed.',
                timestamp: Date.now(),
            }, ...prev].slice(0, 120));
        } finally {
            setRunningTerminal(false);
        }
    }, [settings.command_profile, terminalCommand, terminalCwd]);

    const handleReviewAction = useCallback(async (reviewId: string, action: 'approve' | 'apply' | 'undo') => {
        setMessage('');
        setError('');
        try {
            if (action === 'approve') await agentApi.approveReview(reviewId);
            if (action === 'apply') await agentApi.applyReview(reviewId);
            if (action === 'undo') await agentApi.undoReview(reviewId);
            const refreshed = await agentApi.getReview(reviewId);
            setRunReviews((prev) => prev.map((row) => row.id === reviewId ? refreshed : row));
            if (action !== 'approve') await refreshTree();
            await refreshRuns();
            setMessage(`Review ${reviewId.slice(0, 8)} ${action}d.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : `Failed to ${action} review.`);
        }
    }, [refreshRuns, refreshTree]);

    const previewNodes = useMemo<FlowNode[]>(() => (preview?.team_agents || []).map((agent) => ({
        id: agent.id,
        role: agent.role,
        workerLevel: Number(agent.worker_level || 1) || 1,
        dependsOn: agent.depends_on || [],
        description: agent.description || '',
    })), [preview]);

    const visualNodes = useMemo<FlowNode[]>(() => {
        const base = extractWorkflowNodes(events).length > 0 ? extractWorkflowNodes(events) : previewNodes;
        const statuses = new Map<string, NodeStatus>();
        base.forEach((node) => statuses.set(node.id, 'pending'));
        events.forEach((evt) => {
            const agentId = parseSubagentId(String(evt.message || ''), evt.type);
            if (!agentId) return;
            if (evt.type === 'subagent.started') statuses.set(agentId, 'running');
            if (evt.type === 'subagent.completed') statuses.set(agentId, 'completed');
            if (evt.type === 'subagent.error') statuses.set(agentId, 'failed');
        });
        return base.map((node) => ({ ...node, status: statuses.get(node.id) || 'pending' }));
    }, [events, previewNodes]);

    const agentIds = useMemo(() => visualNodes.map((node) => node.id), [visualNodes]);
    const activityRows = useMemo(() => [...events.map((evt, index) => ({
        id: `event:${index}:${evt.type}`,
        timestamp: Number(evt.timestamp || 0),
        title: evt.type,
        prefix: 'agent',
        body: String(evt.message || ''),
        tone: evt.type.includes('error') || evt.type.includes('failed') ? 'text-accent-red' : evt.type.includes('completed') ? 'text-accent-green' : 'text-text-secondary',
    })), ...terminalRows.map((row) => ({
        id: `terminal:${row.id}`,
        timestamp: row.timestamp,
        title: `${row.cwd} $ ${row.command}`,
        prefix: 'terminal',
        body: [row.stdout, row.stderr].filter(Boolean).join('\n') || `exit_code: ${row.exitCode}`,
        tone: row.exitCode === 0 ? 'text-text-secondary' : 'text-accent-red',
    }))].sort((a, b) => b.timestamp - a.timestamp).slice(0, 200), [events, terminalRows]);

    const searchFilteredTreeRoot = useMemo(() => {
        if (!treeData) return null;
        if (!sidebarSearchQuery.trim()) return treeData.tree;
        return filterRepoTree(treeData.tree, sidebarSearchQuery);
    }, [sidebarSearchQuery, treeData]);

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            const metaOrCtrl = e.ctrlKey || e.metaKey;
            if (!metaOrCtrl || e.repeat) return;
            if (e.key === 'b' && !e.shiftKey && !e.altKey) {
                e.preventDefault();
                setSidebarOpen((s) => !s);
                return;
            }
            if (e.code === 'KeyE' && e.shiftKey && !e.altKey) {
                e.preventDefault();
                setSidebarOpen(true);
                setSidebarTab('explorer');
                return;
            }
            if (e.code === 'KeyF' && e.shiftKey && !e.altKey) {
                e.preventDefault();
                setSidebarOpen(true);
                setSidebarTab('search');
                return;
            }
            if (e.code === 'KeyG' && e.shiftKey && !e.altKey) {
                e.preventDefault();
                setSidebarOpen(true);
                setSidebarTab('source-control');
                return;
            }
            if (e.key === 'j' && !e.shiftKey && !e.altKey) {
                e.preventDefault();
                setBottomPanelOpen((s) => !s);
                return;
            }
            if ((e.key === '`' || e.code === 'Backquote') && !e.shiftKey && !e.altKey) {
                e.preventDefault();
                setBottomPanelOpen(true);
                return;
            }
            if (e.code === 'KeyL' && !e.shiftKey && !e.altKey) {
                e.preventDefault();
                setRightPanelOpen((s) => !s);
                return;
            }
        };
        window.addEventListener('keydown', onKeyDown, true);
        return () => window.removeEventListener('keydown', onKeyDown, true);
    }, []);

    useEffect(() => {
        if (!showGitHubModal) return;
        const onEsc = (ev: KeyboardEvent) => {
            if (ev.key === 'Escape') setShowGitHubModal(false);
        };
        window.addEventListener('keydown', onEsc);
        return () => window.removeEventListener('keydown', onEsc);
    }, [showGitHubModal]);

    const activityBtnClass = (active: boolean) =>
        cn(
            'flex h-11 w-11 shrink-0 items-center justify-center rounded-md transition-colors',
            active ? 'border-l-2 border-l-accent bg-white/10 text-text-primary' : 'text-text-muted hover:bg-white/5 hover:text-text-primary',
        );

    return (
        <div className="h-full min-h-0 flex flex-col bg-surface-0 text-text-primary">
            <div className="flex h-9 shrink-0 items-center gap-3 border-b border-surface-3 bg-[#1e1e1e] px-3 text-[11px] text-text-secondary">
                <span className="font-medium text-text-primary">JimAI Builder</span>
                <span className="hidden sm:inline">·</span>
                <span className="hidden sm:inline text-text-muted">Local agents · Ollama</span>
                <span className="hidden flex-1 justify-center text-center font-mono text-[10px] text-text-muted lg:flex">
                    Ctrl+B sidebar · Ctrl+Shift+E/F/G · Ctrl+` panel · Ctrl+J panel · Ctrl+L AI
                </span>
                <div className="flex shrink-0 items-center gap-1.5">
                    <button
                        type="button"
                        onClick={() => { setSidebarOpen(true); setSidebarTab('source-control'); }}
                        className="rounded border border-surface-4 px-2 py-0.5 text-text-primary hover:bg-white/5"
                    >
                        Source Control
                    </button>
                    <button
                        type="button"
                        onClick={() => setShowGitHubModal(true)}
                        className="rounded border border-surface-4 px-2 py-0.5 text-text-primary hover:bg-white/5"
                        title="Large GitHub panel"
                    >
                        GitHub…
                    </button>
                    <span className="max-w-[120px] truncate rounded border border-surface-4 px-2 py-0.5">{sharedSavedTeamName || sharedTeamName || 'Team'}</span>
                    {(runId || sharedLastRunId) && (
                        <span className="hidden truncate rounded border border-surface-4 px-2 py-0.5 sm:inline">
                            {runStatus || sharedLastRunStatus || 'idle'} · {(runId || sharedLastRunId).slice(0, 8)}
                        </span>
                    )}
                </div>
            </div>

            <div className="flex min-h-0 flex-1">
                <nav
                    className="flex w-12 shrink-0 flex-col items-center gap-0.5 border-r border-[#2d2d2d] bg-[#252526] py-1"
                    aria-label="Activity bar"
                >
                    <button
                        type="button"
                        className={activityBtnClass(sidebarOpen && sidebarTab === 'explorer')}
                        title="Explorer (Ctrl+Shift+E)"
                        onClick={() => { setSidebarOpen(true); setSidebarTab('explorer'); }}
                    >
                        <Files size={20} strokeWidth={1.5} aria-hidden />
                    </button>
                    <button
                        type="button"
                        className={activityBtnClass(sidebarOpen && sidebarTab === 'search')}
                        title="Search (Ctrl+Shift+F)"
                        onClick={() => { setSidebarOpen(true); setSidebarTab('search'); }}
                    >
                        <Search size={20} strokeWidth={1.5} aria-hidden />
                    </button>
                    <button
                        type="button"
                        className={activityBtnClass(sidebarOpen && sidebarTab === 'source-control')}
                        title="Source Control (Ctrl+Shift+G)"
                        onClick={() => { setSidebarOpen(true); setSidebarTab('source-control'); }}
                    >
                        <GitBranch size={20} strokeWidth={1.5} aria-hidden />
                    </button>
                    <div className="min-h-2 flex-1" />
                    <button
                        type="button"
                        className={activityBtnClass(bottomPanelOpen)}
                        title="Toggle panel — Terminal (Ctrl+` or Ctrl+J)"
                        onClick={() => setBottomPanelOpen((s) => !s)}
                    >
                        <Terminal size={20} strokeWidth={1.5} aria-hidden />
                    </button>
                    <button
                        type="button"
                        className={activityBtnClass(rightPanelOpen)}
                        title="Toggle AI sidebar (Ctrl+L)"
                        onClick={() => setRightPanelOpen((s) => !s)}
                    >
                        <Bot size={20} strokeWidth={1.5} aria-hidden />
                    </button>
                </nav>

                {sidebarOpen && (
                    <aside className="flex min-h-0 w-[260px] shrink-0 flex-col border-r border-surface-3 bg-surface-1">
                        {sidebarTab === 'explorer' && (
                            <div className="flex min-h-0 flex-1 flex-col">
                                <div className="border-b border-surface-3 px-3 py-2">
                                    <div className="flex items-center justify-between gap-2">
                                        <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Explorer</p>
                                        <button type="button" onClick={() => refreshTree().catch(() => undefined)} className="rounded-btn border border-surface-4 px-2 py-0.5 text-[10px] text-text-secondary hover:bg-surface-2">
                                            {loadingTree ? '…' : 'Refresh'}
                                        </button>
                                    </div>
                                    <p className="mt-2 text-[10px] leading-snug text-text-muted">
                                        New repo: use the panel terminal (<kbd className="rounded border border-surface-4 px-0.5 font-mono text-[9px]">git init</kbd> /{' '}
                                        <kbd className="rounded border border-surface-4 px-0.5 font-mono text-[9px]">git clone</kbd>) or create a repo on{' '}
                                        <a href="https://github.com/new" target="_blank" rel="noreferrer" className="text-accent hover:underline">
                                            github.com/new
                                        </a>
                                        .
                                    </p>
                                    <div className="mt-2 flex gap-1.5">
                                        <button type="button" onClick={() => setPendingCreate({ parentPath: selectedDirectory || '.', kind: 'file', value: '' })} className="flex-1 rounded-btn border border-surface-4 px-2 py-1 text-[10px] text-text-primary hover:bg-surface-2">+ File</button>
                                        <button type="button" onClick={() => setPendingCreate({ parentPath: selectedDirectory || '.', kind: 'folder', value: '' })} className="flex-1 rounded-btn border border-surface-4 px-2 py-1 text-[10px] text-text-primary hover:bg-surface-2">+ Folder</button>
                                    </div>
                                </div>
                                <div className="min-h-0 flex-1 overflow-auto p-2">
                                    {treeData ? (
                                        <FileTreeNode node={treeData.tree} depth={0} selectedDirectory={selectedDirectory} selectedFilePath={activeTab?.path || ''} pendingCreate={pendingCreate} onOpenFile={openFile} onSelectDirectory={setSelectedDirectory} onRequestCreate={(parentPath, kind) => setPendingCreate({ parentPath, kind, value: '' })} onChangePendingValue={(value) => setPendingCreate((prev) => prev ? { ...prev, value } : prev)} onCreate={createWorkspaceNode} onCancelCreate={() => setPendingCreate(null)} creatingNode={creatingNode} writeMode={editorWriteMode} />
                                    ) : (
                                        <p className="px-2 py-3 text-xs text-text-secondary">Loading repository tree…</p>
                                    )}
                                </div>
                            </div>
                        )}
                        {sidebarTab === 'search' && (
                            <div className="flex min-h-0 flex-1 flex-col">
                                <div className="border-b border-surface-3 px-3 py-2">
                                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Search</p>
                                    <input
                                        value={sidebarSearchQuery}
                                        onChange={(e) => setSidebarSearchQuery(e.target.value)}
                                        className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-2 py-1.5 text-xs text-black outline-none"
                                        placeholder="Filter files by name or path…"
                                        autoFocus
                                    />
                                    <p className="mt-1 text-[10px] text-text-muted">Matches filter the explorer tree below.</p>
                                </div>
                                <div className="min-h-0 flex-1 overflow-auto p-2">
                                    {treeData && searchFilteredTreeRoot ? (
                                        <FileTreeNode node={searchFilteredTreeRoot} depth={0} selectedDirectory={selectedDirectory} selectedFilePath={activeTab?.path || ''} pendingCreate={pendingCreate} onOpenFile={openFile} onSelectDirectory={setSelectedDirectory} onRequestCreate={(parentPath, kind) => setPendingCreate({ parentPath, kind, value: '' })} onChangePendingValue={(value) => setPendingCreate((prev) => prev ? { ...prev, value } : prev)} onCreate={createWorkspaceNode} onCancelCreate={() => setPendingCreate(null)} creatingNode={creatingNode} writeMode={editorWriteMode} />
                                    ) : treeData && sidebarSearchQuery.trim() && !searchFilteredTreeRoot ? (
                                        <p className="px-2 py-3 text-xs text-text-secondary">No matches.</p>
                                    ) : !treeData ? (
                                        <p className="px-2 py-3 text-xs text-text-secondary">Loading…</p>
                                    ) : (
                                        <p className="px-2 py-3 text-xs text-text-secondary">Type to filter the workspace tree.</p>
                                    )}
                                </div>
                            </div>
                        )}
                        {sidebarTab === 'source-control' && showGitHubModal && (
                            <div className="p-3 text-center text-xs text-text-secondary">
                                Large GitHub panel is open. Close it (Esc) to use the sidebar view.
                            </div>
                        )}
                        {sidebarTab === 'source-control' && !showGitHubModal && (
                            <div className="flex min-h-0 flex-1 flex-col">
                                <GitHubPanel
                                    open
                                    variant="embedded"
                                    onClose={() => setSidebarOpen(false)}
                                    onRepositoryChanged={refreshTree}
                                    onExpandToModal={() => setShowGitHubModal(true)}
                                />
                            </div>
                        )}
                    </aside>
                )}

                <div className="flex min-w-0 min-h-0 flex-1 flex-col">
                <section className="flex min-h-0 min-w-0 flex-1 flex-col">
                    <div className="border-b border-surface-3 bg-surface-1">
                        <div className="flex items-center justify-between gap-3 px-3 py-2">
                            <div className="min-w-0"><p className="text-[11px] uppercase tracking-wide text-text-secondary">Editor</p><p className="truncate text-sm text-text-primary">{activeTab ? activeTab.path : 'Open a file or diff from the explorer or review panel.'}</p></div>
                            <div className="flex items-center gap-2">
                                <div className="flex items-center rounded-btn border border-surface-4 bg-surface-0 p-1 text-[11px]">
                                    <button
                                        type="button"
                                        onClick={() => setEditorWriteMode('review')}
                                        className={cn('rounded px-2 py-1', editorWriteMode === 'review' ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:bg-surface-2')}
                                    >
                                        Review mode
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setEditorWriteMode('direct')}
                                        className={cn('rounded px-2 py-1', editorWriteMode === 'direct' ? 'bg-accent-green/15 text-accent-green' : 'text-text-secondary hover:bg-surface-2')}
                                    >
                                        Direct mode
                                    </button>
                                </div>
                                {activeTab?.type === 'file' && <button type="button" onClick={() => saveActiveFile().catch(() => undefined)} disabled={savingFile || !activeTab.dirty} className="rounded-btn border border-accent/40 px-3 py-1.5 text-xs text-accent disabled:opacity-50">{savingFile ? (editorWriteMode === 'review' ? 'Submitting…' : 'Saving…') : activeTab.dirty ? (editorWriteMode === 'review' ? 'Submit for Review' : 'Save File') : editorWriteMode === 'review' ? 'In Review' : 'Saved'}</button>}
                                {loadingFile && <span className="text-[11px] text-text-secondary">Opening…</span>}
                            </div>
                        </div>
                        <div className="flex gap-1 overflow-auto border-t border-surface-3 px-2 py-2">
                            {tabs.length === 0 && <span className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-1 text-[11px] text-text-secondary">No open tabs</span>}
                            {tabs.map((tab) => <button key={tab.id} type="button" onClick={() => setActiveTabId(tab.id)} className={cn('group flex items-center gap-2 rounded-btn border px-3 py-1.5 text-xs', activeTabId === tab.id ? 'border-accent/40 bg-surface-0 text-text-primary' : 'border-surface-4 bg-surface-1 text-text-secondary hover:bg-surface-2')}><span className="truncate max-w-[180px]">{tab.title}{tab.type === 'file' && tab.dirty ? ' *' : ''}</span><span onClick={(event) => { event.stopPropagation(); closeTab(tab.id); }} className="rounded px-1 text-text-muted hover:bg-surface-2 hover:text-text-primary">×</span></button>)}
                        </div>
                    </div>
                    <div className="min-h-0 flex-1 bg-[#0d1117]">
                        {activeTab?.type === 'file' && <Editor height="100%" language={activeTab.language} value={activeTab.content} theme="vs-dark" onChange={(value) => updateActiveTabContent(value || '')} options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: 'on', lineNumbers: 'on', scrollBeyondLastLine: false, tabSize: 2, automaticLayout: true }} />}
                        {activeTab?.type === 'diff' && <DiffEditor height="100%" original={activeTab.original} modified={activeTab.modified} theme="vs-dark" language={detectLanguage(activeTab.path)} options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false }, wordWrap: 'on', scrollBeyondLastLine: false, automaticLayout: true }} />}
                        {!activeTab && <div className="flex h-full items-center justify-center p-8"><div className="max-w-2xl rounded-card border border-surface-3 bg-surface-1 p-6"><p className="text-xs uppercase tracking-wide text-text-secondary">Workspace Ready</p><h2 className="mt-2 text-xl font-semibold text-text-primary">Edit the repo, run agents, review diffs, and monitor logs in one page.</h2><div className="mt-4 grid gap-3 md:grid-cols-2"><div className="rounded-btn border border-surface-3 bg-surface-0 p-3"><p className="text-sm text-text-primary">Prompt preview</p><p className="mt-2 text-xs text-text-secondary">{loadingPreview ? 'Preparing builder preview…' : preview ? `${preview.team_agent_count} agents ready for the current objective.` : 'Start typing a build objective to generate the agent plan.'}</p></div><div className="rounded-btn border border-surface-3 bg-surface-0 p-3"><p className="text-sm text-text-primary">Suggested skills</p><p className="mt-2 text-xs text-text-secondary">{loadingRecommendedSkills ? 'Selecting skills…' : recommendedSkills.length > 0 ? recommendedSkills.slice(0, 4).map((skill) => skill.name).join(', ') : 'Skills appear here once the objective is clear enough.'}</p></div></div></div></div>}
                    </div>
                </section>

                {bottomPanelOpen && (
                <section className="shrink-0 border-t border-surface-3 bg-[#0a0f14]">
                    <div className="flex items-center justify-between gap-3 border-b border-surface-3 px-3 py-2">
                        <div><p className="text-[11px] uppercase tracking-wide text-text-secondary">Terminal / agent log</p><p className="text-xs text-text-muted">Shell output and live agent events stream here.</p></div>
                        <div className="flex items-center gap-2"><input value={terminalCwd} onChange={(e) => setTerminalCwd(e.target.value)} className="w-36 rounded-btn border border-surface-4 bg-surface-1 px-2 py-1 text-xs text-text-primary outline-none" placeholder="cwd" /><input value={terminalCommand} onChange={(e) => setTerminalCommand(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') runTerminalCommand().catch(() => undefined); }} className="w-64 rounded-btn border border-surface-4 bg-surface-1 px-2 py-1 text-xs text-text-primary outline-none" placeholder="npm test" /><button type="button" onClick={() => runTerminalCommand().catch(() => undefined)} disabled={runningTerminal} className="rounded-btn border border-accent/40 px-3 py-1 text-xs text-accent disabled:opacity-50">{runningTerminal ? 'Running…' : 'Run'}</button></div>
                    </div>
                    <div className="h-[220px] overflow-auto px-3 py-3 font-mono text-[11px] leading-5 text-text-secondary">{activityRows.length === 0 ? <p className="text-text-muted">No terminal output or agent events yet.</p> : activityRows.map((row) => <div key={row.id} className="border-b border-surface-3/40 py-2 last:border-b-0"><div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-text-muted"><span>{formatTime(row.timestamp)}</span><span>{row.prefix}</span><span className="text-text-primary normal-case tracking-normal">{row.title}</span></div><pre className={cn('mt-1 whitespace-pre-wrap break-words', row.tone)}>{row.body || '(no output)'}</pre></div>)}</div>
                </section>
                )}
                </div>

                {rightPanelOpen && (
                <aside className="flex w-[360px] shrink-0 flex-col border-l border-surface-3 bg-surface-1">
                    <div className="border-b border-surface-3 px-4 py-3"><p className="text-[11px] uppercase tracking-wide text-text-secondary">Local AI · Agent interface</p><p className="mt-1 text-sm text-text-primary">Run and supervise local agents from the editor</p></div>
                    <div className="min-h-0 flex-1 overflow-auto p-4 space-y-4">
                        <div className="grid grid-cols-3 gap-2 text-[11px]"><div className="rounded-btn border border-surface-3 bg-surface-0 p-2"><p className="text-text-muted">Agents</p><p className="mt-1 text-text-primary">{visualNodes.length || previewNodes.length || 0}</p></div><div className="rounded-btn border border-surface-3 bg-surface-0 p-2"><p className="text-text-muted">Run</p><p className="mt-1 text-text-primary">{runStatus || 'idle'}</p></div><div className="rounded-btn border border-surface-3 bg-surface-0 p-2"><p className="text-text-muted">Reviews</p><p className="mt-1 text-text-primary">{runReviews.length}</p></div></div>
                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Task</p>
                            <textarea rows={5} value={prompt} onChange={(e) => setPrompt(e.target.value)} className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-3 py-2 text-sm text-black outline-none" placeholder="Describe the app to build" />
                            <textarea rows={4} value={context} onChange={(e) => setContext(e.target.value)} className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-3 py-2 text-xs text-black outline-none" placeholder="Optional repo context, constraints, or acceptance criteria" />
                            <div className="mt-3 flex gap-2"><button type="button" onClick={() => launchBuild().catch(() => undefined)} disabled={loadingLaunch} className="flex-1 rounded-btn border border-accent/40 px-3 py-2 text-xs text-accent disabled:opacity-50">{loadingLaunch ? 'Launching...' : 'Start Autonomous Build'}</button><button type="button" onClick={() => stopBuild().catch(() => undefined)} disabled={!runId || loadingStop} className="rounded-btn border border-accent-red/40 px-3 py-2 text-xs text-accent-red disabled:opacity-50">{loadingStop ? 'Stopping…' : 'Stop'}</button></div>
                            {recommendedSkills.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{recommendedSkills.slice(0, 6).map((skill) => <span key={skill.slug} className="rounded-full border border-accent/30 bg-accent/10 px-2 py-1 text-[11px] text-accent">{skill.name}</span>)}</div>}
                            {recommendedSkillContext && <details className="mt-3 text-[11px] text-text-secondary"><summary className="cursor-pointer text-text-primary">Skill context preview</summary><pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded-btn border border-surface-3 bg-surface-1 p-2 text-[10px]">{recommendedSkillContext}</pre></details>}
                        </div>
                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Current agent team</p>
                            <div className="mt-3 space-y-2">{visualNodes.length === 0 ? <p className="text-xs text-text-secondary">{loadingPreview ? 'Previewing agent plan…' : 'No active plan yet.'}</p> : visualNodes.map((node) => <div key={node.id} className={`rounded-btn border p-2 ${statusTone(node.status || 'idle')}`}><div className="flex items-start justify-between gap-2"><div><p className="text-xs text-text-primary">{node.id}</p><p className="mt-1 text-[11px] text-text-secondary">{node.role} · L{node.workerLevel}</p></div><span className="rounded-full border border-surface-4 px-2 py-1 text-[10px] text-text-secondary">{node.status || 'idle'}</span></div>{node.dependsOn.length > 0 && <p className="mt-1 text-[11px] text-text-muted">depends on {node.dependsOn.join(', ')}</p>}{node.description && <p className="mt-1 text-[11px] text-text-secondary">{node.description}</p>}</div>)}</div>
                        </div>
                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Agent control</p>
                            <select value={agentTo} onChange={(e) => setAgentTo(e.target.value)} className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-2 py-1.5 text-xs text-black outline-none"><option value="">All / Planner</option>{agentIds.map((id) => <option key={id} value={id}>{id}</option>)}</select>
                            <select value={agentChannel} onChange={(e) => setAgentChannel(e.target.value)} className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-2 py-1.5 text-xs text-black outline-none"><option value="change-request">change-request</option><option value="handoff">handoff</option><option value="verification">verification</option><option value="general">general</option></select>
                            <textarea rows={3} value={agentMessage} onChange={(e) => setAgentMessage(e.target.value)} className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-2 py-2 text-xs text-black outline-none" placeholder="Tell the active team what to change, prioritize, or verify." />
                            <button type="button" onClick={() => sendAgentControl().catch(() => undefined)} disabled={!runId || sendingAgentMessage} className="mt-2 w-full rounded-btn border border-accent/40 px-3 py-2 text-xs text-accent disabled:opacity-50">{sendingAgentMessage ? 'Sending…' : 'Send Agent Task'}</button>
                        </div>
                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <div className="flex items-center justify-between gap-2"><p className="text-[11px] uppercase tracking-wide text-text-secondary">Agent diffs</p>{loadingReviews && <span className="text-[11px] text-text-secondary">Loading…</span>}</div>
                            <div className="mt-3 space-y-2">{runReviews.length === 0 ? <p className="text-xs text-text-secondary">No review diffs for the selected run yet.</p> : runReviews.map((review) => <div key={review.id} className="rounded-btn border border-surface-3 bg-surface-1 p-3"><div className="flex items-start justify-between gap-2"><div><p className="text-xs text-text-primary">{review.objective}</p><p className="mt-1 text-[11px] text-text-secondary">{review.status} · {review.summary?.file_count || review.changes?.length || 0} files</p></div><span className="text-[10px] text-text-muted">{review.id.slice(0, 8)}</span></div><div className="mt-2 flex flex-wrap gap-1.5">{(review.changes || []).slice(0, 4).map((change) => <button key={`${review.id}:${change.path}`} type="button" onClick={() => openReviewDiff(review, change.path)} className="rounded-full border border-surface-4 bg-surface-0 px-2 py-1 text-[10px] text-text-secondary hover:text-text-primary">{change.path.split('/').pop() || change.path}</button>)}</div><div className="mt-3 flex gap-2"><button type="button" onClick={() => handleReviewAction(review.id, 'approve').catch(() => undefined)} className="rounded-btn border border-accent/40 px-2 py-1 text-[11px] text-accent">Approve</button><button type="button" onClick={() => handleReviewAction(review.id, 'apply').catch(() => undefined)} className="rounded-btn border border-accent-green/40 px-2 py-1 text-[11px] text-accent-green">Apply</button><button type="button" onClick={() => handleReviewAction(review.id, 'undo').catch(() => undefined)} className="rounded-btn border border-accent-red/40 px-2 py-1 text-[11px] text-accent-red">Undo</button></div></div>)}</div>
                        </div>
                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Recent runs</p>
                            <div className="mt-3 space-y-2">{runs.length === 0 ? <p className="text-xs text-text-secondary">No runs yet.</p> : runs.map((row) => <button key={row.id} type="button" onClick={() => { setRunId(row.id); setRunStatus(row.status); setEvents([]); }} className={cn('w-full rounded-btn border p-2 text-left', runId === row.id ? 'border-accent/40 bg-surface-1' : 'border-surface-3 bg-surface-0')}><p className="truncate text-xs text-text-primary">{row.objective}</p><p className="mt-1 text-[11px] text-text-secondary">{row.status} · {row.action_count} actions</p></button>)}</div>
                        </div>
                    </div>
                </aside>
                )}
            </div>

            {(message || error) && <div className="border-t border-surface-3 bg-surface-1 px-4 py-2">{message && <p className="text-sm text-accent-green">{message}</p>}{error && <p className="text-sm text-accent-red">{error}</p>}</div>}
            <GitHubPanel open={showGitHubModal} onClose={() => setShowGitHubModal(false)} onRepositoryChanged={refreshTree} />
        </div>
    );
}

function FileTreeNode({ node, depth, selectedDirectory, selectedFilePath, pendingCreate, onOpenFile, onSelectDirectory, onRequestCreate, onChangePendingValue, onCreate, onCancelCreate, creatingNode, writeMode }: { node: agentApi.RepoTreeNode; depth: number; selectedDirectory: string; selectedFilePath: string; pendingCreate: PendingCreate | null; onOpenFile: (path: string) => void; onSelectDirectory: (path: string) => void; onRequestCreate: (parentPath: string, kind: 'file' | 'folder') => void; onChangePendingValue: (value: string) => void; onCreate: () => void | Promise<void>; onCancelCreate: () => void; creatingNode: boolean; writeMode: 'direct' | 'review'; }) {
    if (node.type === 'file') {
        return <button type="button" onClick={() => onOpenFile(node.path)} className={cn('flex w-full items-center rounded-btn px-2 py-1 text-left text-xs', selectedFilePath === node.path ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:bg-surface-2')} style={{ paddingLeft: `${depth * 14 + 10}px` }}><span className="truncate">{node.name}</span></button>;
    }
    const children = Array.isArray(node.children) ? node.children : [];
    const isSelected = selectedDirectory === node.path;
    const showInlineCreate = pendingCreate?.parentPath === node.path;
    return (
        <details open={depth < 1 || selectedDirectory.startsWith(node.path === '.' ? '' : `${node.path}/`) || isSelected} className="mb-0.5">
            <summary className={cn('flex cursor-pointer list-none items-center justify-between gap-2 rounded-btn px-2 py-1 text-xs', isSelected ? 'bg-surface-2 text-text-primary' : 'text-text-primary hover:bg-surface-2')} style={{ paddingLeft: `${depth * 14 + 8}px` }} onClick={() => onSelectDirectory(node.path)}><span className="truncate">{node.name}</span><span className="flex shrink-0 items-center gap-1"><button type="button" onClick={(event) => { event.preventDefault(); event.stopPropagation(); onSelectDirectory(node.path); onRequestCreate(node.path, 'file'); }} className="rounded px-1 text-[10px] text-text-muted hover:bg-surface-3 hover:text-text-primary" title="New file">+F</button><button type="button" onClick={(event) => { event.preventDefault(); event.stopPropagation(); onSelectDirectory(node.path); onRequestCreate(node.path, 'folder'); }} className="rounded px-1 text-[10px] text-text-muted hover:bg-surface-3 hover:text-text-primary" title="New folder">+D</button></span></summary>
            <div className="mt-0.5">
                {showInlineCreate && <div className="px-2 py-1" style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}><div className="rounded-btn border border-surface-4 bg-surface-0 p-2"><p className="text-[10px] text-text-secondary">New {pendingCreate.kind} in {pendingCreate.parentPath} · {writeMode === 'review' && pendingCreate.kind === 'file' ? 'submit to review' : 'write directly'}</p><input value={pendingCreate.value} onChange={(e) => onChangePendingValue(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') onCreate(); if (e.key === 'Escape') onCancelCreate(); }} className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-2 py-1 text-[11px] text-black outline-none" placeholder={`Enter ${pendingCreate.kind} name`} /><div className="mt-2 flex gap-2"><button type="button" onClick={() => onCreate()} disabled={creatingNode} className="rounded-btn border border-accent/40 px-2 py-1 text-[10px] text-accent disabled:opacity-50">{creatingNode ? (writeMode === 'review' && pendingCreate.kind === 'file' ? 'Submitting…' : 'Creating…') : writeMode === 'review' && pendingCreate.kind === 'file' ? 'Submit Review' : 'Create'}</button><button type="button" onClick={onCancelCreate} className="rounded-btn border border-surface-4 px-2 py-1 text-[10px] text-text-secondary hover:bg-surface-2">Cancel</button></div></div></div>}
                {children.map((child) => <FileTreeNode key={`${child.path}-${child.name}`} node={child} depth={depth + 1} selectedDirectory={selectedDirectory} selectedFilePath={selectedFilePath} pendingCreate={pendingCreate} onOpenFile={onOpenFile} onSelectDirectory={onSelectDirectory} onRequestCreate={onRequestCreate} onChangePendingValue={onChangePendingValue} onCreate={onCreate} onCancelCreate={onCancelCreate} creatingNode={creatingNode} writeMode={writeMode} />)}
            </div>
        </details>
    );
}
