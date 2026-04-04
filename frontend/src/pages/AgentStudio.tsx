import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
    addEdge,
    Background,
    Controls,
    type Connection,
    type Edge,
    type Node,
    Handle,
    Position,
    useEdgesState,
    useNodesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { v4 as uuid } from 'uuid';

import * as agentApi from '../lib/agentSpaceApi';
import { readSharedWorkspaceDraft, writeSharedWorkspaceDraft } from '../lib/utils';

const MODEL_CHOICES = [
    { value: 'qwen2-math:7b-instruct', label: 'Math' },
    { value: 'qwen2.5-coder:7b', label: 'Code' },
    { value: 'qwen3:8b', label: 'Chat' },
    { value: 'qwen2.5vl:7b', label: 'Vision' },
];

const MODEL_COLORS: Record<string, string> = {
    'qwen2-math:7b-instruct': '#f0f0f0',
    'qwen2.5-coder:7b': '#d9d9d9',
    'qwen3:8b': '#bdbdbd',
    'qwen2.5vl:7b': '#f7f7f7',
};

function AgentNode({ data }: { data: Record<string, unknown> }) {
    const model = String(data.model || '');
    const borderColor = MODEL_COLORS[model] || '#707070';
    const role = String(data.role || '');
    return (
        <div
            className="bg-surface-1 border-2 rounded-none p-3 min-w-[190px] text-xs"
            style={{ borderColor }}
        >
            <Handle type="target" position={Position.Top} className="w-2 h-2" />
            <div className="font-medium text-text-primary mb-2 text-sm">{String(data.name || 'Agent')}</div>
            <div className="space-y-1 text-text-secondary">
                <div>
                    <label className="text-[10px] text-text-muted block">Model</label>
                    <span className="text-[11px]">{MODEL_CHOICES.find((m) => m.value === model)?.label || model}</span>
                </div>
                <div>
                    <label className="text-[10px] text-text-muted block">Role</label>
                    <span className="text-[11px]">{role || 'coder'}</span>
                </div>
            </div>
            <Handle type="source" position={Position.Bottom} className="w-2 h-2" />
        </div>
    );
}

const nodeTypes = { agentNode: AgentNode };

const initialNodes: Node[] = [
    {
        id: 'planner',
        type: 'agentNode',
        position: { x: 240, y: 40 },
        data: { name: 'Planner', model: 'qwen3:8b', role: 'planner' },
        deletable: false,
    },
];

export default function AgentStudio() {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge[]>([]);
    const [teamName, setTeamName] = useState('Autonomous Team');
    const [saveStatus, setSaveStatus] = useState('');
    const [savingTeam, setSavingTeam] = useState(false);

    const [skills, setSkills] = useState<agentApi.AgentSkillSummary[]>([]);
    const [selectedSkill, setSelectedSkill] = useState<agentApi.AgentSkillRecord | null>(null);
    const [loadingSkills, setLoadingSkills] = useState(false);
    const [skillsStatus, setSkillsStatus] = useState('');

    const [objective, setObjective] = useState('');
    const [selectionContext, setSelectionContext] = useState('');
    const [selectedSkills, setSelectedSkills] = useState<agentApi.AgentSkillSummary[]>([]);
    const [autoCreatedSkills, setAutoCreatedSkills] = useState<agentApi.AgentSkillSummary[]>([]);

    const [skillName, setSkillName] = useState('');
    const [skillDescription, setSkillDescription] = useState('');
    const [skillTags, setSkillTags] = useState('');
    const [skillComplexity, setSkillComplexity] = useState(3);
    const [skillContent, setSkillContent] = useState('');
    const [creatingSkill, setCreatingSkill] = useState(false);

    const [runPrompt, setRunPrompt] = useState('');
    const [runResult, setRunResult] = useState('');
    const [runningTest, setRunningTest] = useState(false);
    const [savedTeamId, setSavedTeamId] = useState('');
    const [savedTeamName, setSavedTeamName] = useState('');

    const onConnect = useCallback(
        (params: Connection) => setEdges((rows) => addEdge({ ...params, animated: true, style: { stroke: '#f0f0f0' } }, rows)),
        [setEdges],
    );

    const addAgentNode = useCallback(
        (model: string) => {
            const id = uuid();
            const label = MODEL_CHOICES.find((row) => row.value === model)?.label || 'Agent';
            const role = label.toLowerCase() === 'code' ? 'coder' : 'worker';
            const newNode: Node = {
                id,
                type: 'agentNode',
                position: { x: 100 + Math.random() * 380, y: 180 + Math.random() * 220 },
                data: { name: `${label} Agent`, model, role },
            };
            setNodes((rows) => [...rows, newNode]);
        },
        [setNodes],
    );

    const agentSpecs = useMemo(
        () =>
            nodes.map((node, idx) => ({
                id: String(node.id),
                role: String((node.data as Record<string, unknown>).role || (idx === 0 ? 'planner' : 'coder')),
                depends_on: idx === 0 ? [] : [String(nodes[0]?.id || 'planner')],
                description: `${String((node.data as Record<string, unknown>).name || 'Agent')} role`,
                model: String((node.data as Record<string, unknown>).model || 'qwen3:8b'),
                actions: [],
            })),
        [nodes],
    );

    const plannerCount = useMemo(
        () => agentSpecs.filter((row) => row.role === 'planner').length,
        [agentSpecs],
    );

    const loadSkills = useCallback(async () => {
        setLoadingSkills(true);
        try {
            const rows = await agentApi.listSkills(500);
            setSkills(rows);
            if (!selectedSkill && rows.length > 0) {
                const detail = await agentApi.getSkill(rows[0].slug);
                setSelectedSkill(detail);
            }
        } catch (err) {
            setSkillsStatus(`Failed to load skills: ${String(err)}`);
        } finally {
            setLoadingSkills(false);
        }
    }, [selectedSkill]);

    useEffect(() => {
        const shared = readSharedWorkspaceDraft();
        if (shared.teamName) setTeamName(String(shared.teamName));
        if (shared.objective) {
            setObjective(String(shared.objective));
            setRunPrompt(String(shared.objective));
        }
        if (shared.savedTeamId) setSavedTeamId(String(shared.savedTeamId));
        if (shared.savedTeamName) setSavedTeamName(String(shared.savedTeamName));
        if (Array.isArray(shared.selectedSkills) && shared.selectedSkills.length > 0) {
            setSelectedSkills(shared.selectedSkills.map((row) => ({
                slug: String(row.slug || ''),
                name: String(row.name || ''),
                description: '',
                tags: [],
                complexity: 3,
                source: 'shared-workspace',
                created_at: 0,
                updated_at: 0,
            })));
        }
    }, []);

    useEffect(() => {
        const onStorage = () => {
            const shared = readSharedWorkspaceDraft();
            if (shared.teamName) setTeamName(String(shared.teamName));
            if (shared.objective) {
                setObjective(String(shared.objective));
                setRunPrompt(String(shared.objective));
            }
            setSavedTeamId(String(shared.savedTeamId || ''));
            setSavedTeamName(String(shared.savedTeamName || ''));
        };
        window.addEventListener('storage', onStorage);
        return () => window.removeEventListener('storage', onStorage);
    }, []);

    useEffect(() => {
        loadSkills().catch(() => undefined);
    }, [loadSkills]);

    useEffect(() => {
        writeSharedWorkspaceDraft({
            teamName,
            objective,
            prompt: objective,
            selectedSkills: selectedSkills.map((row) => ({ slug: row.slug, name: row.name })),
            savedTeamId,
            savedTeamName,
        });
    }, [objective, savedTeamId, savedTeamName, selectedSkills, teamName]);

    const handleSaveTeam = async () => {
        setSavingTeam(true);
        setSaveStatus('');
        try {
            const payload: agentApi.AgentTeam = {
                name: teamName.trim() || 'Autonomous Team',
                description: 'Team created from Agent Studio canvas.',
                agents: agentSpecs.map((row) => ({
                    id: row.id,
                    role: row.role,
                    depends_on: row.depends_on,
                    description: row.description,
                    model: row.model,
                })),
                metadata: { source: 'agent_studio' },
            };
            const saved = await agentApi.upsertTeam(payload);
            setSavedTeamId(String(saved.id || ''));
            setSavedTeamName(String(saved.name || teamName));
            writeSharedWorkspaceDraft({
                teamName: String(saved.name || teamName),
                savedTeamId: String(saved.id || ''),
                savedTeamName: String(saved.name || teamName),
            });
            setSaveStatus(`Saved team: ${String(saved.name || teamName)}`);
        } catch (err) {
            setSaveStatus(`Save failed: ${String(err)}`);
        } finally {
            setSavingTeam(false);
        }
    };

    const handleInstallDefaults = async () => {
        setSkillsStatus('Installing advanced defaults...');
        try {
            const data = await agentApi.installDefaultSkills();
            await loadSkills();
            setSkillsStatus(`Installed/verified ${data.installed_count} default skills.`);
        } catch (err) {
            setSkillsStatus(`Install defaults failed: ${String(err)}`);
        }
    };

    const handleAutoAdd = async () => {
        const query = objective.trim();
        if (!query) return;
        setSkillsStatus('Auto-generating new skills from objective...');
        try {
            const data = await agentApi.autoAddSkills({ objective: query, max_new_skills: 8 });
            setAutoCreatedSkills(data.created || []);
            setSelectedSkills(data.selected || []);
            await loadSkills();
            setSkillsStatus(`Created ${data.created_count} skills and selected ${data.selected.length}.`);
        } catch (err) {
            setSkillsStatus(`Auto-add failed: ${String(err)}`);
        }
    };

    const handleSelectSkills = async () => {
        const query = objective.trim();
        if (!query) return;
        setSkillsStatus('Selecting best skills...');
        try {
            const data = await agentApi.selectSkills({ objective: query, limit: 12, include_context: true });
            setSelectedSkills(data.selected || []);
            setSelectionContext(String(data.context || ''));
            setSkillsStatus(`Selected ${data.selected_count} skills for objective.`);
        } catch (err) {
            setSkillsStatus(`Select failed: ${String(err)}`);
        }
    };

    const handleCreateSkill = async () => {
        const name = skillName.trim();
        if (!name) return;
        setCreatingSkill(true);
        setSkillsStatus('');
        try {
            const tags = skillTags
                .split(',')
                .map((row) => row.trim())
                .filter((row) => row.length > 0);
            const saved = await agentApi.upsertSkill({
                name,
                description: skillDescription.trim(),
                content: skillContent.trim(),
                tags,
                complexity: Math.max(1, Math.min(5, Number(skillComplexity) || 3)),
                source: 'agent-studio-user',
                metadata: { created_from: 'agent_studio' },
            });
            setSkillName('');
            setSkillDescription('');
            setSkillTags('');
            setSkillContent('');
            setSelectedSkill(saved);
            await loadSkills();
            setSkillsStatus(`Saved skill: ${saved.name}`);
        } catch (err) {
            setSkillsStatus(`Create skill failed: ${String(err)}`);
        } finally {
            setCreatingSkill(false);
        }
    };

    const handleDeleteSkill = async (slug: string) => {
        try {
            await agentApi.deleteSkill(slug);
            if (selectedSkill?.slug === slug) {
                setSelectedSkill(null);
            }
            await loadSkills();
            setSkillsStatus(`Deleted skill: ${slug}`);
        } catch (err) {
            setSkillsStatus(`Delete failed: ${String(err)}`);
        }
    };

    const handleOpenSkill = async (slug: string) => {
        try {
            const detail = await agentApi.getSkill(slug);
            setSelectedSkill(detail);
        } catch (err) {
            setSkillsStatus(`Open skill failed: ${String(err)}`);
        }
    };

    const handleRunTest = async () => {
        const prompt = runPrompt.trim();
        if (!prompt) return;
        setRunningTest(true);
        setRunResult('Launching autonomous run...');
        try {
            const payload = {
                objective: prompt,
                autonomous: true,
                team: {
                    name: teamName.trim() || 'Autonomous Team',
                    description: 'Run from Agent Studio',
                    agents: agentSpecs,
                    save: true,
                    metadata: {
                        source: 'agent_studio',
                        selected_skills: selectedSkills.map((row) => row.slug),
                    },
                },
                force_research: true,
                continue_on_subagent_failure: true,
                subagent_retry_attempts: 2,
            };
            const run = await agentApi.startRun(payload);
            writeSharedWorkspaceDraft({
                teamName: teamName.trim() || 'Autonomous Team',
                savedTeamId,
                savedTeamName: savedTeamName || teamName.trim() || 'Autonomous Team',
                objective: prompt,
                prompt,
                selectedSkills: selectedSkills.map((row) => ({ slug: row.slug, name: row.name })),
                lastRunId: String(run.id || ''),
                lastRunStatus: String(run.status || ''),
                lastRunObjective: prompt,
            });
            setRunResult(`Run queued: ${String(run.id)} | status=${String(run.status)}`);
        } catch (err) {
            setRunResult(`Run failed: ${String(err)}`);
        } finally {
            setRunningTest(false);
        }
    };

    return (
        <div className="h-full min-h-0 flex flex-col bg-surface-0">
            <div className="flex-shrink-0 flex flex-wrap items-center gap-2 px-4 py-2 border-b border-surface-4 bg-surface-1">
                <span className="text-sm font-medium text-text-primary">Agent Studio</span>
                <div className="flex-1" />
                <input
                    value={teamName}
                    onChange={(e) => setTeamName(e.target.value)}
                    className="px-2 py-1 text-xs bg-surface-0 border border-surface-4 rounded-btn text-text-primary outline-none w-52"
                    placeholder="Team name"
                />
                {MODEL_CHOICES.map((choice) => (
                    <button
                        key={choice.value}
                        onClick={() => addAgentNode(choice.value)}
                        className="px-2 py-1 text-xs bg-surface-0 hover:bg-surface-2 border border-surface-4 rounded-btn text-text-primary"
                    >
                        + {choice.label}
                    </button>
                ))}
                <button
                    onClick={handleSaveTeam}
                    disabled={savingTeam}
                    className="px-3 py-1 text-xs bg-surface-0 hover:bg-surface-2 border border-surface-4 rounded-btn text-text-primary disabled:opacity-60"
                >
                    {savingTeam ? 'Saving...' : 'Save Team'}
                </button>
            </div>

            <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-12 gap-0">
                <div className="col-span-1 xl:col-span-8 min-h-[360px] xl:min-h-0 border-b xl:border-b-0 xl:border-r border-surface-4">
                    <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        onConnect={onConnect}
                        nodeTypes={nodeTypes}
                        fitView
                    >
                        <Background color="#1f1f1f" gap={24} />
                        <Controls />
                    </ReactFlow>
                </div>

                <div className="col-span-1 xl:col-span-4 min-h-0 overflow-auto p-3 space-y-3 bg-surface-1">
                    <div className="rounded-none border border-surface-4 bg-surface-0 p-3 space-y-3">
                        <div>
                            <div className="text-xs font-semibold text-text-primary">How Agent Studio Works</div>
                            <p className="mt-1 text-[11px] text-text-secondary">
                                Build or save an agent team, describe the objective, let jimAI choose or create skills, then launch a run.
                            </p>
                        </div>
                        <div className="grid grid-cols-4 gap-2 text-[11px]">
                            <div className="rounded-btn border border-surface-4 bg-surface-1 p-2">
                                <p className="text-text-muted">Agents</p>
                                <p className="mt-1 text-text-primary">{agentSpecs.length}</p>
                            </div>
                            <div className="rounded-btn border border-surface-4 bg-surface-1 p-2">
                                <p className="text-text-muted">Planners</p>
                                <p className="mt-1 text-text-primary">{plannerCount}</p>
                            </div>
                            <div className="rounded-btn border border-surface-4 bg-surface-1 p-2">
                                <p className="text-text-muted">Skills</p>
                                <p className="mt-1 text-text-primary">{selectedSkills.length}</p>
                            </div>
                            <div className="rounded-btn border border-surface-4 bg-surface-1 p-2">
                                <p className="text-text-muted">Library</p>
                                <p className="mt-1 text-text-primary">{skills.length}</p>
                            </div>
                        </div>
                        <div className="rounded-btn border border-accent/25 bg-accent/10 p-2 text-[11px] text-text-primary">
                            Recommended flow: save the team, auto-add or select skills from the objective, then start the run.
                        </div>
                        {(savedTeamName || savedTeamId) && (
                            <div className="rounded-btn border border-surface-4 bg-surface-1 p-2 text-[11px] text-text-secondary">
                                Saved team connected to Builder: {savedTeamName || teamName}
                                {savedTeamId ? ` · ${savedTeamId.slice(0, 8)}` : ''}
                            </div>
                        )}
                    </div>

                    <div className="rounded-none border border-surface-4 bg-surface-0 p-3 space-y-2">
                        <div className="text-xs font-semibold text-text-primary">Run Objective</div>
                        <textarea
                            value={objective}
                            onChange={(e) => setObjective(e.target.value)}
                            rows={3}
                            placeholder="Describe what you want agents to build. Skills can auto-generate from this objective."
                            className="w-full bg-white text-black border border-surface-4 rounded-none px-2 py-2 text-xs resize-none"
                        />
                        <div className="flex gap-2">
                            <button
                                onClick={handleAutoAdd}
                                className="flex-1 px-2 py-1 text-xs border border-surface-4 rounded-btn bg-surface-0 hover:bg-surface-2 text-text-primary"
                            >
                                Auto-Add Skills
                            </button>
                            <button
                                onClick={handleSelectSkills}
                                className="flex-1 px-2 py-1 text-xs border border-surface-4 rounded-btn bg-surface-0 hover:bg-surface-2 text-text-primary"
                            >
                                Select Skills
                            </button>
                        </div>
                        {selectedSkills.length > 0 ? (
                            <div className="text-[11px] text-text-secondary">
                                Selected: {selectedSkills.slice(0, 6).map((row) => row.name).join(', ')}
                            </div>
                        ) : null}
                        {!selectedSkills.length ? (
                            <div className="text-[11px] text-text-muted">
                                No skills selected yet. Use Auto-Add for maximum autonomy or Select Skills for a safer preview.
                            </div>
                        ) : null}
                        {selectionContext ? (
                            <details className="text-[11px] text-text-secondary">
                                <summary className="cursor-pointer text-text-primary">Skill Context Preview</summary>
                                <pre className="mt-2 whitespace-pre-wrap text-[10px] max-h-48 overflow-auto border border-surface-4 rounded p-2 bg-surface-1">
                                    {selectionContext}
                                </pre>
                            </details>
                        ) : null}
                    </div>

                    <div className="rounded-none border border-surface-4 bg-surface-0 p-3 space-y-2">
                        <div className="flex items-center justify-between">
                            <div className="text-xs font-semibold text-text-primary">Skill Library</div>
                            <div className="flex gap-2">
                                <button
                                    onClick={handleInstallDefaults}
                                    className="px-2 py-1 text-[11px] border border-surface-4 rounded-btn bg-surface-0 hover:bg-surface-2 text-text-primary"
                                >
                                    Install Defaults
                                </button>
                                <button
                                    onClick={() => loadSkills()}
                                    className="px-2 py-1 text-[11px] border border-surface-4 rounded-btn bg-surface-0 hover:bg-surface-2 text-text-primary"
                                >
                                    Refresh
                                </button>
                            </div>
                        </div>
                        {loadingSkills ? <div className="text-[11px] text-text-muted">Loading skills...</div> : null}
                        <div className="max-h-48 overflow-auto border border-surface-4 rounded-none">
                            {skills.map((skill) => (
                                <div key={skill.slug} className="px-2 py-2 border-b border-surface-4 last:border-b-0">
                                    <div className="flex items-start justify-between gap-2">
                                        <button
                                            onClick={() => handleOpenSkill(skill.slug)}
                                            className="text-left text-xs text-text-primary hover:underline"
                                        >
                                            {skill.name}
                                        </button>
                                        <button
                                            onClick={() => handleDeleteSkill(skill.slug)}
                                            className="text-[10px] px-1.5 py-0.5 border border-surface-4 rounded text-text-secondary hover:bg-surface-2"
                                        >
                                            Delete
                                        </button>
                                    </div>
                                    <div className="text-[10px] text-text-muted">{skill.slug} · L{skill.complexity}</div>
                                </div>
                            ))}
                        </div>
                        {autoCreatedSkills.length > 0 ? (
                            <div className="text-[11px] text-text-secondary">
                                Auto-created: {autoCreatedSkills.map((row) => row.name).join(', ')}
                            </div>
                        ) : null}
                        {!autoCreatedSkills.length ? (
                            <div className="text-[11px] text-text-muted">
                                Default and custom markdown skills live here. Auto-created skills are added when the objective requires missing capabilities.
                            </div>
                        ) : null}
                    </div>

                    <div className="rounded-none border border-surface-4 bg-surface-0 p-3 space-y-2">
                        <div className="text-xs font-semibold text-text-primary">Create Skill</div>
                        <input
                            value={skillName}
                            onChange={(e) => setSkillName(e.target.value)}
                            placeholder="Skill name"
                            className="w-full bg-white text-black border border-surface-4 rounded-none px-2 py-1.5 text-xs"
                        />
                        <input
                            value={skillDescription}
                            onChange={(e) => setSkillDescription(e.target.value)}
                            placeholder="Short description"
                            className="w-full bg-white text-black border border-surface-4 rounded-none px-2 py-1.5 text-xs"
                        />
                        <div className="grid grid-cols-5 gap-2">
                            <input
                                value={skillTags}
                                onChange={(e) => setSkillTags(e.target.value)}
                                placeholder="tags,comma,separated"
                                className="col-span-4 bg-white text-black border border-surface-4 rounded-none px-2 py-1.5 text-xs"
                            />
                            <input
                                type="number"
                                min={1}
                                max={5}
                                value={skillComplexity}
                                onChange={(e) => setSkillComplexity(Number(e.target.value))}
                                className="col-span-1 bg-white text-black border border-surface-4 rounded-none px-2 py-1.5 text-xs"
                            />
                        </div>
                        <textarea
                            value={skillContent}
                            onChange={(e) => setSkillContent(e.target.value)}
                            rows={6}
                            placeholder="Optional full SKILL.md content. Leave empty to auto-build a complex template."
                            className="w-full bg-white text-black border border-surface-4 rounded-none px-2 py-2 text-xs resize-y"
                        />
                        <button
                            onClick={handleCreateSkill}
                            disabled={creatingSkill}
                            className="w-full px-2 py-1.5 text-xs border border-surface-4 rounded-btn bg-surface-0 hover:bg-surface-2 text-text-primary disabled:opacity-60"
                        >
                            {creatingSkill ? 'Creating...' : 'Save Skill'}
                        </button>
                    </div>

                    <div className="rounded-none border border-surface-4 bg-surface-0 p-3 space-y-2">
                        <div className="text-xs font-semibold text-text-primary">Quick Run</div>
                        <textarea
                            value={runPrompt}
                            onChange={(e) => setRunPrompt(e.target.value)}
                            rows={3}
                            placeholder="Prompt the current team to execute a task."
                            className="w-full bg-white text-black border border-surface-4 rounded-none px-2 py-2 text-xs resize-none"
                        />
                        <button
                            onClick={handleRunTest}
                            disabled={runningTest}
                            className="w-full px-2 py-1.5 text-xs border border-surface-4 rounded-btn bg-surface-0 hover:bg-surface-2 text-text-primary disabled:opacity-60"
                        >
                            {runningTest ? 'Running...' : 'Start Run'}
                        </button>
                        {runResult ? <div className="text-[11px] text-text-secondary whitespace-pre-wrap">{runResult}</div> : null}
                    </div>

                    {selectedSkill ? (
                        <div className="rounded-none border border-surface-4 bg-surface-0 p-3 space-y-2">
                            <div className="text-xs font-semibold text-text-primary">Selected Skill</div>
                            <div className="text-xs text-text-primary">{selectedSkill.name}</div>
                            <div className="text-[11px] text-text-secondary">{selectedSkill.description}</div>
                            <div className="flex flex-wrap gap-2 text-[10px]">
                                <span className="rounded-none border border-surface-4 px-2 py-1 text-text-secondary">
                                    source {selectedSkill.source}
                                </span>
                                <span className="rounded-none border border-surface-4 px-2 py-1 text-text-secondary">
                                    complexity L{selectedSkill.complexity}
                                </span>
                                {selectedSkill.tags.slice(0, 4).map((tag) => (
                                    <span key={tag} className="rounded-none border border-accent/30 bg-accent/10 px-2 py-1 text-accent">
                                        {tag}
                                    </span>
                                ))}
                            </div>
                            <pre className="whitespace-pre-wrap text-[10px] max-h-52 overflow-auto border border-surface-4 rounded p-2 bg-surface-1">
                                {selectedSkill.content}
                            </pre>
                        </div>
                    ) : null}

                    {saveStatus ? <div className="text-[11px] text-text-secondary">{saveStatus}</div> : null}
                    {skillsStatus ? <div className="text-[11px] text-text-secondary">{skillsStatus}</div> : null}
                </div>
            </div>
        </div>
    );
}
