import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type * as Monaco from 'monaco-editor';
import Editor, { DiffEditor } from '@monaco-editor/react';
import { Bot, Files, GitBranch, Keyboard, Maximize2, Search, Terminal } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import * as agentApi from '../lib/agentSpaceApi';
import { getGitHubStatus } from '../lib/githubApi';
import GitHubPanel from '../components/GitHubPanel';
import { BuilderCommandPalette, type BuilderPaletteAction } from '../components/builder/BuilderCommandPalette';
import { BuilderStatusBar } from '../components/builder/BuilderStatusBar';
import { isShortcutFocusInEditorField } from '../components/builder/builderShortcutGate';
import {
    loadBuilderLayout,
    loadMinimalChrome,
    persistBuilderLayout,
    persistMinimalChrome,
} from '../components/builder/builderStorage';
import { ResizeHandle } from '../components/builder/ResizeHandle';
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

function sanitizeCloneDir(name: string): string {
    return name.replace(/[^a-zA-Z0-9._-]/g, '').slice(0, 64);
}

function defaultCloneFolderFromUrl(url: string): string {
    const u = url.trim().replace(/\.git$/i, '').replace(/\/$/, '');
    const part = u.split(/[/:]/).filter(Boolean).pop() || 'repo';
    const cleaned = sanitizeCloneDir(part);
    return cleaned || 'repo';
}
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
const statusTone = (status: NodeStatus) => status === 'running' ? 'border-accent/40 bg-accent/10' : status === 'completed' ? 'border-accent-green/40 bg-accent-green/10' : status === 'failed' ? 'border-accent-red/40 bg-accent-red/10' : 'border-surface-4 bg-surface-1';

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
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const builderFullLayout = searchParams.get('full') === '1';
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
    const [bottomLogTab, setBottomLogTab] = useState<'all' | 'terminal' | 'agent'>('all');
    const [shortcutsOpen, setShortcutsOpen] = useState(false);
    const [minimalChrome, setMinimalChrome] = useState(() => loadMinimalChrome());
    const [showGitHubModal, setShowGitHubModal] = useState(false);
    const [sidebarSearchQuery, setSidebarSearchQuery] = useState('');
    const [cloneRepoUrl, setCloneRepoUrl] = useState('');
    const [cloneFolderName, setCloneFolderName] = useState('');
    const [cloneBusy, setCloneBusy] = useState(false);
    const welcomeFileInputRef = useRef<HTMLInputElement>(null);
    const [sidebarWidth, setSidebarWidth] = useState(() => loadBuilderLayout().sidebarWidth);
    const [rightWidth, setRightWidth] = useState(() => loadBuilderLayout().rightWidth);
    const [bottomPanelHeight, setBottomPanelHeight] = useState(() => loadBuilderLayout().bottomHeight);
    const [searchSubTab, setSearchSubTab] = useState<'filter' | 'text'>('filter');
    const [workspaceTextQuery, setWorkspaceTextQuery] = useState('');
    const [workspaceSearchBusy, setWorkspaceSearchBusy] = useState(false);
    const [workspaceMatches, setWorkspaceMatches] = useState<agentApi.WorkspaceTextSearchMatch[]>([]);
    const [editorCursor, setEditorCursor] = useState<{ line: number; col: number } | null>(null);
    const [statusBarBranch, setStatusBarBranch] = useState('');
    const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
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

    const refreshStatusBranch = useCallback(() => {
        getGitHubStatus()
            .then((s) => setStatusBarBranch(s.branch ? `⎇ ${s.branch}` : ''))
            .catch(() => setStatusBarBranch(''));
    }, []);

    const refreshTree = useCallback(async () => {
        setLoadingTree(true);
        try {
            setTreeData(await agentApi.listRepoTree('.', 12, 30000, false));
            refreshStatusBranch();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load file tree.');
        } finally {
            setLoadingTree(false);
        }
    }, [refreshStatusBranch]);

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
        refreshStatusBranch();
        const id = window.setInterval(() => refreshStatusBranch(), 120_000);
        return () => window.clearInterval(id);
    }, [refreshStatusBranch]);

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

    const openLocalFileToTab = useCallback(
        async (file: File) => {
            try {
                const text = await file.text();
                const name = file.name || 'untitled.txt';
                const path = joinRepoPath(selectedDirectory || '.', name);
                upsertTab(
                    {
                        id: `file:${path}`,
                        type: 'file',
                        title: name,
                        path,
                        content: text,
                        dirty: true,
                        language: detectLanguage(name),
                    },
                    true,
                );
                setMessage(`Opened “${name}” from disk. Save to write it into the workspace.`);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Could not read that file.');
            }
        },
        [selectedDirectory, upsertTab],
    );

    const runGitClone = useCallback(async () => {
        const url = cloneRepoUrl.trim();
        if (!url) {
            setError('Enter a repository URL to clone.');
            return;
        }
        const dirRaw = cloneFolderName.trim() || defaultCloneFolderFromUrl(url);
        const dir = sanitizeCloneDir(dirRaw) || 'repo';
        setCloneBusy(true);
        setError('');
        setMessage('');
        setBottomPanelOpen(true);
        try {
            const escapedUrl = url.replace(/"/g, '');
            const escapedDir = dir.replace(/"/g, '');
            const result = await agentApi.toolsShell({
                command: `git clone "${escapedUrl}" "${escapedDir}"`,
                cwd: '.',
                profile: normalizeProfile(settings.command_profile),
                timeout: 600,
            });
            const exit = Number(result.exit_code ?? (result.success ? 0 : 1));
            const ok = exit === 0;
            if (!ok) {
                setError(String(result.stderr || result.stdout || 'git clone failed.'));
                return;
            }
            setMessage(`Cloned into ${dir}. Explorer refreshed.`);
            setCloneRepoUrl('');
            setCloneFolderName('');
            await refreshTree();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Clone failed. Enable shell in Settings if it is disabled.');
        } finally {
            setCloneBusy(false);
        }
    }, [cloneFolderName, cloneRepoUrl, refreshTree, settings.command_profile]);

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

    const filteredActivityRows = useMemo(() => {
        if (bottomLogTab === 'all') return activityRows;
        return activityRows.filter((r) => r.prefix === bottomLogTab);
    }, [activityRows, bottomLogTab]);

    const searchFilteredTreeRoot = useMemo(() => {
        if (!treeData) return null;
        if (!sidebarSearchQuery.trim()) return treeData.tree;
        return filterRepoTree(treeData.tree, sidebarSearchQuery);
    }, [sidebarSearchQuery, treeData]);

    const runWorkspaceTextSearch = useCallback(async () => {
        const q = workspaceTextQuery.trim();
        if (!q) return;
        setWorkspaceSearchBusy(true);
        setError('');
        try {
            const res = await agentApi.workspaceTextSearch({ query: q, path_prefix: '.', max_results: 200 });
            setWorkspaceMatches(res.matches || []);
        } catch (err) {
            setWorkspaceMatches([]);
            setError(err instanceof Error ? err.message : 'Workspace search failed.');
        } finally {
            setWorkspaceSearchBusy(false);
        }
    }, [workspaceTextQuery]);

    const handleMonacoMount = useCallback((editor: Monaco.editor.IStandaloneCodeEditor) => {
        editor.onDidChangeCursorPosition((ev) => {
            setEditorCursor({ line: ev.position.lineNumber, col: ev.position.column });
        });
    }, []);

    useEffect(() => {
        if (activeTab?.type !== 'file') setEditorCursor(null);
    }, [activeTab?.type, activeTabId]);

    const commitSidebarLayout = useCallback(() => {
        persistBuilderLayout({ sidebarWidth });
    }, [sidebarWidth]);

    const commitRightLayout = useCallback(() => {
        persistBuilderLayout({ rightWidth });
    }, [rightWidth]);

    const commitBottomLayout = useCallback(() => {
        persistBuilderLayout({ bottomHeight: bottomPanelHeight });
    }, [bottomPanelHeight]);

    const paletteActions = useMemo<BuilderPaletteAction[]>(
        () => [
            {
                id: 'toggle-sidebar',
                label: 'Toggle sidebar',
                hint: 'Ctrl+B',
                run: () => setSidebarOpen((s) => !s),
            },
            {
                id: 'focus-explorer',
                label: 'Show explorer',
                hint: 'Ctrl+Shift+E',
                run: () => {
                    setSidebarOpen(true);
                    setSidebarTab('explorer');
                },
            },
            {
                id: 'focus-search',
                label: 'Show search',
                hint: 'Ctrl+Shift+F',
                run: () => {
                    setSidebarOpen(true);
                    setSidebarTab('search');
                },
            },
            {
                id: 'focus-text-search',
                label: 'Search in files (text)',
                run: () => {
                    setSidebarOpen(true);
                    setSidebarTab('search');
                    setSearchSubTab('text');
                },
            },
            {
                id: 'focus-git',
                label: 'Show source control',
                hint: 'Ctrl+Shift+G',
                run: () => {
                    setSidebarOpen(true);
                    setSidebarTab('source-control');
                },
            },
            {
                id: 'github-modal',
                label: 'Open large Git panel',
                run: () => setShowGitHubModal(true),
            },
            {
                id: 'shortcuts-help',
                label: 'Keyboard shortcuts',
                run: () => setShortcutsOpen(true),
            },
            {
                id: 'toggle-minimal-chrome',
                label: minimalChrome ? 'Show builder top bar' : 'Minimal chrome: hide top bar',
                run: () => {
                    setMinimalChrome((prev) => {
                        const next = !prev;
                        persistMinimalChrome(next);
                        return next;
                    });
                },
            },
            {
                id: 'toggle-full-builder',
                label: builderFullLayout ? 'Exit full-screen builder' : 'Full-screen builder (hide app nav)',
                run: () => navigate(builderFullLayout ? '/builder' : '/builder?full=1'),
            },
            {
                id: 'toggle-terminal',
                label: 'Toggle bottom panel',
                hint: 'Ctrl+J / Ctrl+`',
                run: () => setBottomPanelOpen((s) => !s),
            },
            {
                id: 'toggle-ai',
                label: 'Toggle AI sidebar',
                hint: 'Ctrl+L',
                run: () => setRightPanelOpen((s) => !s),
            },
            {
                id: 'open-file',
                label: 'Open local file…',
                run: () => welcomeFileInputRef.current?.click(),
            },
            {
                id: 'clone-hint',
                label: 'Clone from terminal',
                run: () => {
                    setBottomPanelOpen(true);
                    setMessage('Run git clone from the bottom panel, or use the clone field on the welcome view when no file is open.');
                },
            },
        ],
        [minimalChrome, builderFullLayout, navigate],
    );

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            const metaOrCtrl = e.ctrlKey || e.metaKey;
            if (e.repeat) return;

            if (metaOrCtrl && e.shiftKey && e.code === 'KeyP') {
                e.preventDefault();
                setCommandPaletteOpen(true);
                return;
            }

            if (!metaOrCtrl) return;
            if (isShortcutFocusInEditorField(e.target)) return;

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

    useEffect(() => {
        if (!shortcutsOpen) return;
        const onEsc = (ev: KeyboardEvent) => {
            if (ev.key === 'Escape') setShortcutsOpen(false);
        };
        window.addEventListener('keydown', onEsc);
        return () => window.removeEventListener('keydown', onEsc);
    }, [shortcutsOpen]);

    const activityBtnClass = (active: boolean) =>
        cn(
            'flex h-11 w-11 shrink-0 items-center justify-center transition-colors',
            active ? 'border-l-2 border-l-accent/80 bg-white/[0.06] text-text-primary' : 'text-text-muted hover:bg-white/[0.04] hover:text-text-primary',
        );

    return (
        <div className="h-full min-h-0 flex flex-col bg-[#1e1e1e] text-text-primary">
            {!minimalChrome && (
            <div className="flex h-8 shrink-0 items-center gap-2 border-b border-white/[0.06] bg-[#252526] px-2.5 text-[11px] text-text-secondary">
                <span className="shrink-0 text-sm font-medium text-text-primary">Builder</span>
                <span className="hidden min-w-0 flex-1 items-center gap-2 truncate sm:flex">
                    <span className="text-text-muted">·</span>
                    <span className="truncate text-[11px] text-text-muted">{sharedSavedTeamName || sharedTeamName || 'Team'}</span>
                    {(runId || sharedLastRunId) && (
                        <>
                            <span className="text-text-muted">·</span>
                            <span className="shrink-0 text-[11px] text-text-muted">
                                {runStatus || sharedLastRunStatus || 'idle'} · {(runId || sharedLastRunId).slice(0, 8)}
                            </span>
                        </>
                    )}
                </span>
                <div className="ml-auto flex shrink-0 items-center gap-1">
                    <button
                        type="button"
                        onClick={() => { setSidebarOpen(true); setSidebarTab('source-control'); }}
                        className="px-2 py-1 text-[11px] text-text-secondary hover:bg-white/[0.06] hover:text-text-primary"
                        title="Open source control in sidebar (Ctrl+Shift+G). Use Expand there for a larger panel."
                    >
                        Git
                    </button>
                    <button
                        type="button"
                        onClick={() => setShortcutsOpen(true)}
                        className="flex h-7 w-7 items-center justify-center text-text-muted hover:bg-white/[0.06] hover:text-text-primary"
                        title="Keyboard shortcuts"
                        aria-label="Keyboard shortcuts"
                    >
                        <Keyboard size={15} strokeWidth={1.5} aria-hidden />
                    </button>
                    {builderFullLayout ? (
                        <Link
                            to="/builder"
                            className="px-2 py-1 text-[11px] text-text-secondary hover:bg-white/[0.06] hover:text-text-primary"
                            title="Show app navigation bar"
                        >
                            Exit full
                        </Link>
                    ) : (
                        <Link
                            to="/builder?full=1"
                            className="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-text-secondary hover:bg-white/[0.06] hover:text-text-primary"
                            title="Hide app nav"
                        >
                            <Maximize2 size={12} aria-hidden />
                            <span className="hidden sm:inline">Full</span>
                        </Link>
                    )}
                </div>
            </div>
            )}

            <div className="flex min-h-0 flex-1">
                <nav
                    className="flex w-12 shrink-0 flex-col items-center gap-0.5 border-r border-white/[0.06] bg-[#252526] py-1"
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
                        title="Search — Find files & text (Ctrl+Shift+F)"
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
                    <aside
                        className="flex min-h-0 shrink-0 flex-col border-r border-white/[0.06] bg-[#252526]"
                        style={{ width: sidebarWidth }}
                    >
                        {sidebarTab === 'explorer' && (
                            <div className="flex min-h-0 flex-1 flex-col">
                                <div className="border-b border-white/[0.06] px-3 py-2">
                                    <div className="flex items-center justify-between gap-2">
                                        <p className="text-[11px] font-medium text-text-secondary">Explorer</p>
                                        <button type="button" onClick={() => refreshTree().catch(() => undefined)} className="rounded-none border border-surface-4 px-2 py-0.5 text-[10px] text-text-secondary hover:bg-surface-2">
                                            {loadingTree ? '…' : 'Refresh'}
                                        </button>
                                    </div>
                                    <p className="mt-2 text-[10px] leading-snug text-text-muted">
                                        New repo: use the panel terminal (<kbd className="border border-surface-4 px-0.5 font-mono text-[9px]">git init</kbd> /{' '}
                                        <kbd className="border border-surface-4 px-0.5 font-mono text-[9px]">git clone</kbd>) or create a repo on{' '}
                                        <a href="https://github.com/new" target="_blank" rel="noreferrer" className="text-accent hover:underline">
                                            github.com/new
                                        </a>
                                        .
                                    </p>
                                    <div className="mt-2 flex gap-1.5">
                                        <button type="button" onClick={() => setPendingCreate({ parentPath: selectedDirectory || '.', kind: 'file', value: '' })} className="flex-1 rounded-none border border-surface-4 px-2 py-1 text-[10px] text-text-primary hover:bg-surface-2">+ File</button>
                                        <button type="button" onClick={() => setPendingCreate({ parentPath: selectedDirectory || '.', kind: 'folder', value: '' })} className="flex-1 rounded-none border border-surface-4 px-2 py-1 text-[10px] text-text-primary hover:bg-surface-2">+ Folder</button>
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
                                <div className="border-b border-white/[0.06] px-2 py-2">
                                    <p className="px-1 text-[11px] font-medium text-text-secondary">Search</p>
                                    <div className="mt-2 flex rounded-none border border-surface-4 bg-surface-0 p-0.5 text-[10px]">
                                        <button
                                            type="button"
                                            className={cn('flex-1 px-2 py-1', searchSubTab === 'filter' ? 'bg-surface-2 text-text-primary' : 'text-text-muted hover:text-text-primary')}
                                            onClick={() => setSearchSubTab('filter')}
                                        >
                                            Find files
                                        </button>
                                        <button
                                            type="button"
                                            className={cn('flex-1 px-2 py-1', searchSubTab === 'text' ? 'bg-surface-2 text-text-primary' : 'text-text-muted hover:text-text-primary')}
                                            onClick={() => setSearchSubTab('text')}
                                        >
                                            Text
                                        </button>
                                    </div>
                                </div>
                                {searchSubTab === 'filter' && (
                                    <>
                                        <div className="border-b border-white/[0.06] px-3 py-2">
                                            <input
                                                value={sidebarSearchQuery}
                                                onChange={(e) => setSidebarSearchQuery(e.target.value)}
                                                className="w-full rounded-none border border-surface-4 bg-white px-2 py-1.5 text-xs text-black outline-none"
                                                placeholder="Filter by file name or path…"
                                            />
                                            <p className="mt-1 text-[10px] text-text-muted">Narrows the tree below (not full-text search).</p>
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
                                    </>
                                )}
                                {searchSubTab === 'text' && (
                                    <div className="flex min-h-0 flex-1 flex-col px-3 py-2">
                                        <input
                                            value={workspaceTextQuery}
                                            onChange={(e) => setWorkspaceTextQuery(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') runWorkspaceTextSearch().catch(() => undefined);
                                            }}
                                            className="w-full rounded-none border border-surface-4 bg-white px-2 py-1.5 text-xs text-black outline-none"
                                            placeholder="Search text in workspace…"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => runWorkspaceTextSearch().catch(() => undefined)}
                                            disabled={workspaceSearchBusy || !workspaceTextQuery.trim()}
                                            className="mt-2 rounded-none border border-accent/40 px-2 py-1.5 text-[11px] text-accent disabled:opacity-50"
                                        >
                                            {workspaceSearchBusy ? 'Searching…' : 'Search'}
                                        </button>
                                        <p className="mt-2 text-[10px] text-text-muted">Literal substring in indexed text file types (see backend). Click a row to open the file.</p>
                                        <div className="mt-2 min-h-0 flex-1 space-y-1 overflow-auto">
                                            {workspaceMatches.length === 0 && !workspaceSearchBusy && (
                                                <p className="text-xs text-text-secondary">{workspaceTextQuery.trim() ? 'No results.' : 'Enter text and Search.'}</p>
                                            )}
                                            {workspaceMatches.map((row, idx) => (
                                                <button
                                                    key={`${row.path}:${row.line}:${idx}`}
                                                    type="button"
                                                    onClick={() => openFile(row.path).catch(() => undefined)}
                                                    className="w-full border border-surface-4 bg-surface-0 px-2 py-1.5 text-left text-[10px] hover:bg-surface-2"
                                                >
                                                    <span className="font-mono text-text-primary">{row.path}</span>
                                                    <span className="text-text-muted"> :{row.line}</span>
                                                    <p className="mt-0.5 truncate text-text-secondary">{row.preview}</p>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                        {sidebarTab === 'source-control' && showGitHubModal && (
                            <div className="p-3 text-center text-xs text-text-secondary">
                                Large Git panel is open. Press Esc to return to the sidebar view.
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
                {sidebarOpen && (
                    <ResizeHandle
                        axis="horizontal"
                        onDelta={(dx) => setSidebarWidth((w) => Math.min(520, Math.max(200, w + dx)))}
                        onCommit={commitSidebarLayout}
                    />
                )}

                <div className="flex min-w-0 min-h-0 flex-1 flex-col">
                <section className="flex min-h-0 min-w-0 flex-1 flex-col">
                    <div className="border-b border-white/[0.06] bg-[#252526]">
                        <div className="flex gap-0.5 overflow-x-auto px-2 py-1">
                            {tabs.length === 0 && (
                                <span className="px-2 py-1 text-[11px] text-text-muted">No open editors</span>
                            )}
                            {tabs.map((tab) => (
                                <button
                                    key={tab.id}
                                    type="button"
                                    onClick={() => setActiveTabId(tab.id)}
                                    className={cn(
                                        'group flex max-w-[200px] shrink-0 items-center gap-1.5 rounded-none border border-b-0 px-2.5 py-1.5 text-[11px]',
                                        activeTabId === tab.id
                                            ? 'border-white/[0.08] bg-[#1e1e1e] text-text-primary'
                                            : 'border-transparent bg-transparent text-text-muted hover:bg-white/[0.04] hover:text-text-secondary',
                                    )}
                                >
                                    <span className="truncate">
                                        {tab.title}
                                        {tab.type === 'file' && tab.dirty ? ' ·' : ''}
                                    </span>
                                    <button
                                        type="button"
                                        aria-label={`Close ${tab.title}`}
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            closeTab(tab.id);
                                        }}
                                        className="px-0.5 text-text-muted hover:bg-white/10 hover:text-text-primary"
                                    >
                                        ×
                                    </button>
                                </button>
                            ))}
                        </div>
                        {activeTab && (
                            <div className="flex items-center justify-between gap-2 border-t border-white/[0.06] bg-[#1e1e1e] px-2.5 py-1.5">
                                <div className="min-w-0 flex-1">
                                    <p className="truncate font-mono text-[11px] text-text-secondary" title={activeTab.path}>
                                        {activeTab.path}
                                    </p>
                                </div>
                                <div className="flex shrink-0 items-center gap-2">
                                    <div className="flex items-center border border-white/[0.08] bg-[#252526] p-0.5 text-[11px]">
                                        <button
                                            type="button"
                                            onClick={() => setEditorWriteMode('review')}
                                            className={cn(
                                                'px-2 py-0.5',
                                                editorWriteMode === 'review' ? 'bg-accent/15 text-accent' : 'text-text-muted hover:bg-white/[0.06]',
                                            )}
                                        >
                                            Review
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setEditorWriteMode('direct')}
                                            className={cn(
                                                'px-2 py-0.5',
                                                editorWriteMode === 'direct' ? 'bg-accent-green/15 text-accent-green' : 'text-text-muted hover:bg-white/[0.06]',
                                            )}
                                        >
                                            Direct
                                        </button>
                                    </div>
                                    {activeTab.type === 'file' && (
                                        <button
                                            type="button"
                                            onClick={() => saveActiveFile().catch(() => undefined)}
                                            disabled={savingFile || !activeTab.dirty}
                                            className="border border-accent/35 px-2.5 py-1 text-[11px] text-accent disabled:opacity-50"
                                        >
                                            {savingFile
                                                ? editorWriteMode === 'review'
                                                    ? 'Submitting…'
                                                    : 'Saving…'
                                                : activeTab.dirty
                                                  ? editorWriteMode === 'review'
                                                      ? 'Submit for review'
                                                      : 'Save'
                                                  : editorWriteMode === 'review'
                                                    ? 'In review'
                                                    : 'Saved'}
                                        </button>
                                    )}
                                    {loadingFile && <span className="text-[11px] text-text-muted">Opening…</span>}
                                </div>
                            </div>
                        )}
                    </div>
                    <div className="min-h-0 flex-1 bg-[#1e1e1e]">
                        {activeTab?.type === 'file' && <Editor height="100%" language={activeTab.language} value={activeTab.content} theme="vs-dark" onChange={(value) => updateActiveTabContent(value || '')} onMount={handleMonacoMount} options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: 'on', lineNumbers: 'on', scrollBeyondLastLine: false, tabSize: 2, automaticLayout: true }} />}
                        {activeTab?.type === 'diff' && <DiffEditor height="100%" original={activeTab.original} modified={activeTab.modified} theme="vs-dark" language={detectLanguage(activeTab.path)} options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false }, wordWrap: 'on', scrollBeyondLastLine: false, automaticLayout: true }} />}
                        {!activeTab && (
                            <div className="flex h-full min-h-0 flex-col overflow-auto bg-[#1e1e1e]">
                                <input
                                    ref={welcomeFileInputRef}
                                    type="file"
                                    className="hidden"
                                    onChange={(e) => {
                                        const f = e.target.files?.[0];
                                        e.target.value = '';
                                        if (f) void openLocalFileToTab(f);
                                    }}
                                />
                                <div className="flex min-h-0 flex-1 justify-center overflow-auto px-4 py-8">
                                    <div className="w-full max-w-3xl space-y-6">
                                        <div>
                                            <h2 className="text-base font-medium text-text-primary">Open or clone a project</h2>
                                            <p className="mt-1 text-[12px] leading-relaxed text-text-muted">
                                                Workspace:{' '}
                                                <span className="font-mono text-text-secondary">
                                                    {selectedDirectory === '.' ? 'repository root' : selectedDirectory}
                                                </span>
                                            </p>
                                            <div className="mt-3 flex flex-wrap gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => welcomeFileInputRef.current?.click()}
                                                    className="border border-white/[0.1] bg-white/[0.04] px-3 py-1.5 text-[12px] text-text-primary hover:bg-white/[0.07]"
                                                >
                                                    Open local file
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setSidebarOpen(true);
                                                        setSidebarTab('explorer');
                                                    }}
                                                    className="border border-white/[0.1] bg-white/[0.04] px-3 py-1.5 text-[12px] text-text-primary hover:bg-white/[0.07]"
                                                >
                                                    Show explorer
                                                </button>
                                            </div>
                                        </div>
                                        <div className="space-y-2 rounded-none border border-white/[0.06] bg-[#252526] p-4">
                                            <p className="text-[12px] text-text-muted">
                                                Clone runs <code className="bg-black/30 px-1 font-mono text-[11px]">git clone</code> in this workspace (shell must be allowed in Settings). Folder name: letters, numbers,{' '}
                                                <code className="bg-black/30 px-0.5 font-mono text-[11px]">.</code>{' '}
                                                <code className="bg-black/30 px-0.5 font-mono text-[11px]">_</code>{' '}
                                                <code className="bg-black/30 px-0.5 font-mono text-[11px]">-</code>.
                                            </p>
                                            <input
                                                value={cloneRepoUrl}
                                                onChange={(e) => setCloneRepoUrl(e.target.value)}
                                                className="w-full border border-white/[0.1] bg-white px-2.5 py-2 text-sm text-black outline-none"
                                                placeholder="https://github.com/owner/repo.git"
                                            />
                                            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                                                <input
                                                    value={cloneFolderName}
                                                    onChange={(e) => setCloneFolderName(e.target.value)}
                                                    className="flex-1 border border-white/[0.1] bg-white px-2.5 py-2 text-sm text-black outline-none"
                                                    placeholder="Folder name (optional)"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => runGitClone().catch(() => undefined)}
                                                    disabled={cloneBusy}
                                                    className="shrink-0 border border-accent/35 px-3 py-2 text-[12px] text-accent disabled:opacity-50"
                                                >
                                                    {cloneBusy ? 'Cloning…' : 'Clone'}
                                                </button>
                                            </div>
                                        </div>
                                        <div className="grid gap-2 sm:grid-cols-2">
                                            <div className="rounded-none border border-white/[0.06] bg-[#252526] p-3">
                                                <p className="text-[12px] font-medium text-text-primary">Objective preview</p>
                                                <p className="mt-1.5 text-[11px] leading-snug text-text-muted">
                                                    {loadingPreview
                                                        ? 'Preparing…'
                                                        : preview
                                                          ? `${preview.team_agent_count} agents for the current objective.`
                                                          : 'Add a build objective in the right panel.'}
                                                </p>
                                            </div>
                                            <div className="rounded-none border border-white/[0.06] bg-[#252526] p-3">
                                                <p className="text-[12px] font-medium text-text-primary">Suggested skills</p>
                                                <p className="mt-1.5 text-[11px] leading-snug text-text-muted">
                                                    {loadingRecommendedSkills
                                                        ? 'Selecting…'
                                                        : recommendedSkills.length > 0
                                                          ? recommendedSkills
                                                                .slice(0, 4)
                                                                .map((skill) => skill.name)
                                                                .join(', ')
                                                          : 'Skills appear when the objective is clear enough.'}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </section>

                {bottomPanelOpen && (
                    <>
                        <ResizeHandle
                            axis="vertical"
                            onDelta={(dy) => setBottomPanelHeight((h) => Math.min(600, Math.max(100, h - dy)))}
                            onCommit={commitBottomLayout}
                        />
                        <section className="shrink-0 border-t border-white/[0.06] bg-[#1a1d21]">
                            <div className="flex flex-col gap-2 border-b border-white/[0.06] px-2.5 py-2 sm:flex-row sm:items-center sm:justify-between">
                                <div className="flex flex-wrap items-center gap-1">
                                    {(['all', 'terminal', 'agent'] as const).map((key) => (
                                        <button
                                            key={key}
                                            type="button"
                                            onClick={() => setBottomLogTab(key)}
                                            className={cn(
                                                'px-2 py-1 text-[11px]',
                                                bottomLogTab === key
                                                    ? 'bg-white/[0.08] text-text-primary'
                                                    : 'text-text-muted hover:bg-white/[0.05] hover:text-text-secondary',
                                            )}
                                        >
                                            {key === 'all' ? 'All' : key === 'terminal' ? 'Terminal' : 'Log'}
                                        </button>
                                    ))}
                                </div>
                                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 sm:justify-end">
                                    <input
                                        value={terminalCwd}
                                        onChange={(e) => setTerminalCwd(e.target.value)}
                                        className="w-28 border border-white/[0.08] bg-[#252526] px-2 py-1 text-[11px] text-text-primary outline-none"
                                        placeholder="cwd"
                                    />
                                    <input
                                        value={terminalCommand}
                                        onChange={(e) => setTerminalCommand(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') runTerminalCommand().catch(() => undefined);
                                        }}
                                        className="min-w-[8rem] flex-1 border border-white/[0.08] bg-[#252526] px-2 py-1 text-[11px] text-text-primary outline-none sm:max-w-xs"
                                        placeholder="Command"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => runTerminalCommand().catch(() => undefined)}
                                        disabled={runningTerminal}
                                        className="shrink-0 border border-accent/35 px-2.5 py-1 text-[11px] text-accent disabled:opacity-50"
                                    >
                                        {runningTerminal ? 'Running…' : 'Run'}
                                    </button>
                                </div>
                            </div>
                            <div
                                style={{ height: bottomPanelHeight }}
                                className="overflow-auto px-2.5 py-2 font-mono text-[11px] leading-5 text-text-secondary"
                            >
                                {filteredActivityRows.length === 0 ? (
                                    <p className="text-[11px] text-text-muted">
                                        {activityRows.length === 0
                                            ? 'No shell output or agent events yet.'
                                            : 'Nothing in this filter.'}
                                    </p>
                                ) : (
                                    filteredActivityRows.map((row) => (
                                        <div key={row.id} className="border-b border-white/[0.04] py-2 last:border-b-0">
                                            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-text-muted">
                                                <span>{formatTime(row.timestamp)}</span>
                                                <span className="capitalize">{row.prefix}</span>
                                                <span className="text-text-secondary">{row.title}</span>
                                            </div>
                                            <pre className={cn('mt-1 whitespace-pre-wrap break-words', row.tone)}>
                                                {row.body || '(no output)'}
                                            </pre>
                                        </div>
                                    ))
                                )}
                            </div>
                        </section>
                    </>
                )}
                </div>

                {rightPanelOpen && (
                    <ResizeHandle
                        axis="horizontal"
                        onDelta={(dx) => setRightWidth((w) => Math.min(720, Math.max(260, w - dx)))}
                        onCommit={commitRightLayout}
                    />
                )}
                {rightPanelOpen && (
                <aside className="flex shrink-0 flex-col border-l border-white/[0.06] bg-[#252526]" style={{ width: rightWidth }}>
                    <div className="border-b border-white/[0.06] px-3 py-2.5">
                        <p className="text-[13px] font-medium text-text-primary">Build & agents</p>
                        <p className="mt-0.5 text-[11px] text-text-muted">Objective, team, and reviews</p>
                    </div>
                    <div className="flex gap-2 border-b border-white/[0.06] px-3 py-2 text-[11px]">
                        <div className="min-w-0 flex-1 border border-white/[0.06] bg-[#1e1e1e] px-2 py-1.5">
                            <p className="text-[10px] text-text-muted">Agents</p>
                            <p className="truncate font-medium text-text-primary">{visualNodes.length || previewNodes.length || 0}</p>
                        </div>
                        <div className="min-w-0 flex-1 border border-white/[0.06] bg-[#1e1e1e] px-2 py-1.5">
                            <p className="text-[10px] text-text-muted">Run</p>
                            <p className="truncate font-medium text-text-primary">{runStatus || 'idle'}</p>
                        </div>
                        <div className="min-w-0 flex-1 border border-white/[0.06] bg-[#1e1e1e] px-2 py-1.5">
                            <p className="text-[10px] text-text-muted">Reviews</p>
                            <p className="truncate font-medium text-text-primary">{runReviews.length}</p>
                        </div>
                    </div>
                    <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
                        <div className="rounded-none border border-white/[0.06] bg-[#1e1e1e] p-3">
                            <p className="text-[11px] font-medium text-text-secondary">Task</p>
                            <textarea rows={5} value={prompt} onChange={(e) => setPrompt(e.target.value)} className="mt-2 w-full rounded-none border border-surface-4 bg-white px-3 py-2 text-sm text-black outline-none" placeholder="Describe the app to build" />
                            <textarea rows={4} value={context} onChange={(e) => setContext(e.target.value)} className="mt-2 w-full rounded-none border border-surface-4 bg-white px-3 py-2 text-xs text-black outline-none" placeholder="Optional repo context, constraints, or acceptance criteria" />
                            <div className="mt-3 flex gap-2"><button type="button" onClick={() => launchBuild().catch(() => undefined)} disabled={loadingLaunch} className="flex-1 rounded-none border border-accent/40 px-3 py-2 text-xs text-accent disabled:opacity-50">{loadingLaunch ? 'Launching...' : 'Start Autonomous Build'}</button><button type="button" onClick={() => stopBuild().catch(() => undefined)} disabled={!runId || loadingStop} className="rounded-none border border-accent-red/40 px-3 py-2 text-xs text-accent-red disabled:opacity-50">{loadingStop ? 'Stopping…' : 'Stop'}</button></div>
                            {recommendedSkills.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{recommendedSkills.slice(0, 6).map((skill) => <span key={skill.slug} className="rounded-none border border-accent/30 bg-accent/10 px-2 py-1 text-[11px] text-accent">{skill.name}</span>)}</div>}
                            {recommendedSkillContext && <details className="mt-3 text-[11px] text-text-secondary"><summary className="cursor-pointer text-text-primary">Skill context preview</summary><pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded-none border border-surface-4 bg-surface-1 p-2 text-[10px]">{recommendedSkillContext}</pre></details>}
                        </div>
                        <div className="rounded-none border border-white/[0.06] bg-[#1e1e1e] p-3">
                            <p className="text-[11px] font-medium text-text-secondary">Current team</p>
                            <div className="mt-3 space-y-2">{visualNodes.length === 0 ? <p className="text-xs text-text-secondary">{loadingPreview ? 'Previewing agent plan…' : 'No active plan yet.'}</p> : visualNodes.map((node) => <div key={node.id} className={`rounded-none border p-2 ${statusTone(node.status || 'idle')}`}><div className="flex items-start justify-between gap-2"><div><p className="text-xs text-text-primary">{node.id}</p><p className="mt-1 text-[11px] text-text-secondary">{node.role} · L{node.workerLevel}</p></div><span className="rounded-none border border-surface-4 px-2 py-1 text-[10px] text-text-secondary">{node.status || 'idle'}</span></div>{node.dependsOn.length > 0 && <p className="mt-1 text-[11px] text-text-muted">depends on {node.dependsOn.join(', ')}</p>}{node.description && <p className="mt-1 text-[11px] text-text-secondary">{node.description}</p>}</div>)}</div>
                        </div>
                        <div className="rounded-none border border-white/[0.06] bg-[#1e1e1e] p-3">
                            <p className="text-[11px] font-medium text-text-secondary">Agent messages</p>
                            <select value={agentTo} onChange={(e) => setAgentTo(e.target.value)} className="mt-2 w-full rounded-none border border-surface-4 bg-white px-2 py-1.5 text-xs text-black outline-none"><option value="">All / Planner</option>{agentIds.map((id) => <option key={id} value={id}>{id}</option>)}</select>
                            <select value={agentChannel} onChange={(e) => setAgentChannel(e.target.value)} className="mt-2 w-full rounded-none border border-surface-4 bg-white px-2 py-1.5 text-xs text-black outline-none"><option value="change-request">change-request</option><option value="handoff">handoff</option><option value="verification">verification</option><option value="general">general</option></select>
                            <textarea rows={3} value={agentMessage} onChange={(e) => setAgentMessage(e.target.value)} className="mt-2 w-full rounded-none border border-surface-4 bg-white px-2 py-2 text-xs text-black outline-none" placeholder="Tell the active team what to change, prioritize, or verify." />
                            <button type="button" onClick={() => sendAgentControl().catch(() => undefined)} disabled={!runId || sendingAgentMessage} className="mt-2 w-full rounded-none border border-accent/40 px-3 py-2 text-xs text-accent disabled:opacity-50">{sendingAgentMessage ? 'Sending…' : 'Send Agent Task'}</button>
                        </div>
                        <div className="rounded-none border border-white/[0.06] bg-[#1e1e1e] p-3">
                            <div className="flex items-center justify-between gap-2">
                                <p className="text-[11px] font-medium text-text-secondary">Review diffs</p>
                                {loadingReviews && <span className="text-[11px] text-text-muted">Loading…</span>}
                            </div>
                            <div className="mt-3 space-y-2">{runReviews.length === 0 ? <p className="text-xs text-text-secondary">No review diffs for the selected run yet.</p> : runReviews.map((review) => <div key={review.id} className="rounded-none border border-surface-4 bg-surface-1 p-3"><div className="flex items-start justify-between gap-2"><div><p className="text-xs text-text-primary">{review.objective}</p><p className="mt-1 text-[11px] text-text-secondary">{review.status} · {review.summary?.file_count || review.changes?.length || 0} files</p></div><span className="text-[10px] text-text-muted">{review.id.slice(0, 8)}</span></div><div className="mt-2 flex flex-wrap gap-1.5">{(review.changes || []).slice(0, 4).map((change) => <button key={`${review.id}:${change.path}`} type="button" onClick={() => openReviewDiff(review, change.path)} className="rounded-none border border-surface-4 bg-surface-0 px-2 py-1 text-[10px] text-text-secondary hover:text-text-primary">{change.path.split('/').pop() || change.path}</button>)}</div><div className="mt-3 flex gap-2"><button type="button" onClick={() => handleReviewAction(review.id, 'approve').catch(() => undefined)} className="rounded-none border border-accent/40 px-2 py-1 text-[11px] text-accent">Approve</button><button type="button" onClick={() => handleReviewAction(review.id, 'apply').catch(() => undefined)} className="rounded-none border border-accent-green/40 px-2 py-1 text-[11px] text-accent-green">Apply</button><button type="button" onClick={() => handleReviewAction(review.id, 'undo').catch(() => undefined)} className="rounded-none border border-accent-red/40 px-2 py-1 text-[11px] text-accent-red">Undo</button></div></div>)}</div>
                        </div>
                        <div className="rounded-none border border-white/[0.06] bg-[#1e1e1e] p-3">
                            <p className="text-[11px] font-medium text-text-secondary">Recent runs</p>
                            <div className="mt-3 space-y-2">{runs.length === 0 ? <p className="text-xs text-text-secondary">No runs yet.</p> : runs.map((row) => <button key={row.id} type="button" onClick={() => { setRunId(row.id); setRunStatus(row.status); setEvents([]); }} className={cn('w-full rounded-none border p-2 text-left', runId === row.id ? 'border-accent/40 bg-surface-1' : 'border-surface-4 bg-surface-0')}><p className="truncate text-xs text-text-primary">{row.objective}</p><p className="mt-1 text-[11px] text-text-secondary">{row.status} · {row.action_count} actions</p></button>)}</div>
                        </div>
                    </div>
                </aside>
                )}
            </div>

            <BuilderStatusBar
                fileLabel={
                    activeTab?.type === 'file'
                        ? activeTab.path
                        : activeTab?.type === 'diff'
                          ? `${activeTab.path} · diff`
                          : 'No editor'
                }
                lineCol={
                    activeTab?.type === 'file' && editorCursor
                        ? `Ln ${editorCursor.line}, Col ${editorCursor.col}`
                        : '—'
                }
                language={
                    activeTab?.type === 'file'
                        ? activeTab.language
                        : activeTab?.type === 'diff'
                          ? detectLanguage(activeTab.path)
                          : '—'
                }
                branch={statusBarBranch}
                notice={error ? { type: 'error', text: error } : message ? { type: 'ok', text: message } : null}
                minimalChrome={minimalChrome}
                onRestoreTopBar={() => {
                    setMinimalChrome(false);
                    persistMinimalChrome(false);
                }}
            />
            {shortcutsOpen && (
                <div
                    className="fixed inset-0 z-50 flex items-start justify-center bg-black/45 px-4 pt-[10vh]"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="builder-shortcuts-title"
                >
                    <button
                        type="button"
                        className="absolute inset-0 cursor-default"
                        aria-label="Close shortcuts"
                        onClick={() => setShortcutsOpen(false)}
                    />
                    <div className="relative z-10 w-full max-w-md border border-white/[0.1] bg-[#252526] p-4 shadow-none">
                        <div className="flex items-start justify-between gap-2">
                            <h2 id="builder-shortcuts-title" className="text-sm font-medium text-text-primary">
                                Keyboard shortcuts
                            </h2>
                            <button
                                type="button"
                                onClick={() => setShortcutsOpen(false)}
                                className="px-2 py-0.5 text-text-muted hover:bg-white/[0.06] hover:text-text-primary"
                            >
                                Esc
                            </button>
                        </div>
                        <ul className="mt-4 space-y-2.5 text-[12px] text-text-secondary">
                            <li>
                                <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+Shift+P</kbd>{' '}
                                Command palette
                            </li>
                            <li>
                                <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+B</kbd> Toggle sidebar
                            </li>
                            <li>
                                <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+Shift+E</kbd> Explorer
                            </li>
                            <li>
                                <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+Shift+F</kbd> Search
                            </li>
                            <li>
                                <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+Shift+G</kbd> Source control
                            </li>
                            <li>
                                <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+`</kbd> or{' '}
                                <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+J</kbd> Bottom panel
                            </li>
                            <li>
                                <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+L</kbd> AI sidebar
                            </li>
                        </ul>
                        <div className="mt-4 border-t border-white/[0.08] pt-4">
                            <label className="flex cursor-pointer items-center gap-2 text-[12px] text-text-secondary">
                                <input
                                    type="checkbox"
                                    className="h-3.5 w-3.5 border border-white/20 bg-[#1e1e1e]"
                                    checked={minimalChrome}
                                    onChange={(e) => {
                                        const v = e.target.checked;
                                        setMinimalChrome(v);
                                        persistMinimalChrome(v);
                                    }}
                                />
                                Minimal chrome (hide top bar)
                            </label>
                        </div>
                    </div>
                </div>
            )}
            <BuilderCommandPalette open={commandPaletteOpen} onClose={() => setCommandPaletteOpen(false)} actions={paletteActions} />
            <GitHubPanel open={showGitHubModal} onClose={() => setShowGitHubModal(false)} onRepositoryChanged={refreshTree} />
        </div>
    );
}

function FileTreeNode({ node, depth, selectedDirectory, selectedFilePath, pendingCreate, onOpenFile, onSelectDirectory, onRequestCreate, onChangePendingValue, onCreate, onCancelCreate, creatingNode, writeMode }: { node: agentApi.RepoTreeNode; depth: number; selectedDirectory: string; selectedFilePath: string; pendingCreate: PendingCreate | null; onOpenFile: (path: string) => void; onSelectDirectory: (path: string) => void; onRequestCreate: (parentPath: string, kind: 'file' | 'folder') => void; onChangePendingValue: (value: string) => void; onCreate: () => void | Promise<void>; onCancelCreate: () => void; creatingNode: boolean; writeMode: 'direct' | 'review'; }) {
    if (node.type === 'file') {
        return <button type="button" onClick={() => onOpenFile(node.path)} className={cn('flex w-full items-center rounded-none px-2 py-1 text-left text-xs', selectedFilePath === node.path ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:bg-surface-2')} style={{ paddingLeft: `${depth * 14 + 10}px` }}><span className="truncate">{node.name}</span></button>;
    }
    const children = Array.isArray(node.children) ? node.children : [];
    const isSelected = selectedDirectory === node.path;
    const showInlineCreate = pendingCreate?.parentPath === node.path;
    return (
        <details open={depth < 1 || selectedDirectory.startsWith(node.path === '.' ? '' : `${node.path}/`) || isSelected} className="mb-0.5">
            <summary className={cn('flex cursor-pointer list-none items-center justify-between gap-2 rounded-none px-2 py-1 text-xs', isSelected ? 'bg-surface-2 text-text-primary' : 'text-text-primary hover:bg-surface-2')} style={{ paddingLeft: `${depth * 14 + 8}px` }} onClick={() => onSelectDirectory(node.path)}><span className="truncate">{node.name}</span><span className="flex shrink-0 items-center gap-1"><button type="button" onClick={(event) => { event.preventDefault(); event.stopPropagation(); onSelectDirectory(node.path); onRequestCreate(node.path, 'file'); }} className="px-1 text-[10px] text-text-muted hover:bg-surface-3 hover:text-text-primary" title="New file">+F</button><button type="button" onClick={(event) => { event.preventDefault(); event.stopPropagation(); onSelectDirectory(node.path); onRequestCreate(node.path, 'folder'); }} className="px-1 text-[10px] text-text-muted hover:bg-surface-3 hover:text-text-primary" title="New folder">+D</button></span></summary>
            <div className="mt-0.5">
                {showInlineCreate && <div className="px-2 py-1" style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}><div className="rounded-none border border-surface-4 bg-surface-0 p-2"><p className="text-[10px] text-text-secondary">New {pendingCreate.kind} in {pendingCreate.parentPath} · {writeMode === 'review' && pendingCreate.kind === 'file' ? 'submit to review' : 'write directly'}</p><input value={pendingCreate.value} onChange={(e) => onChangePendingValue(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') onCreate(); if (e.key === 'Escape') onCancelCreate(); }} className="mt-2 w-full rounded-none border border-surface-4 bg-white px-2 py-1 text-[11px] text-black outline-none" placeholder={`Enter ${pendingCreate.kind} name`} /><div className="mt-2 flex gap-2"><button type="button" onClick={() => onCreate()} disabled={creatingNode} className="rounded-none border border-accent/40 px-2 py-1 text-[10px] text-accent disabled:opacity-50">{creatingNode ? (writeMode === 'review' && pendingCreate.kind === 'file' ? 'Submitting…' : 'Creating…') : writeMode === 'review' && pendingCreate.kind === 'file' ? 'Submit Review' : 'Create'}</button><button type="button" onClick={onCancelCreate} className="rounded-none border border-surface-4 px-2 py-1 text-[10px] text-text-secondary hover:bg-surface-2">Cancel</button></div></div></div>}
                {children.map((child) => <FileTreeNode key={`${child.path}-${child.name}`} node={child} depth={depth + 1} selectedDirectory={selectedDirectory} selectedFilePath={selectedFilePath} pendingCreate={pendingCreate} onOpenFile={onOpenFile} onSelectDirectory={onSelectDirectory} onRequestCreate={onRequestCreate} onChangePendingValue={onChangePendingValue} onCreate={onCreate} onCancelCreate={onCancelCreate} creatingNode={creatingNode} writeMode={writeMode} />)}
            </div>
        </details>
    );
}
