import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
    addEdge,
    Background,
    Controls,
    MiniMap,
    type Connection,
    type Edge,
    type Node,
    useEdgesState,
    useNodesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import * as agentApi from '../lib/agentSpaceApi';
import { PageHeader } from '../components/PageHeader';

type FlowKind = 'trigger' | 'action' | 'logic' | 'ai' | 'integration' | 'research';

type FlowNodeData = {
    label: string;
    kind: FlowKind;
    nodeType: string;
    description: string;
};

const FLOW_NODE_LIBRARY: Record<FlowKind, { title: string; nodeType: string; color: string; description: string }> = {
    trigger: { title: 'Trigger', nodeType: 'jimai.trigger.manual', color: '#3B82F6', description: 'Entry point.' },
    action: { title: 'Action', nodeType: 'jimai.action.transform', color: '#8888A0', description: 'Transform payload.' },
    logic: { title: 'Logic', nodeType: 'jimai.logic.condition', color: '#F59E0B', description: 'Conditional gate.' },
    ai: { title: 'Local AI', nodeType: 'jimai.ai.ollama', color: '#22C55E', description: 'Local Ollama node.' },
    integration: { title: 'Integration', nodeType: 'jimai.integration.http', color: '#A855F7', description: 'HTTP integration.' },
    research: { title: 'Research', nodeType: 'jimai.research.search', color: '#00D4FF', description: 'Web research node.' },
};

const INITIAL_FLOW_NODES: Node<FlowNodeData>[] = [
    {
        id: 'trigger-1',
        position: { x: 80, y: 80 },
        data: {
            label: 'Manual Trigger',
            kind: 'trigger',
            nodeType: FLOW_NODE_LIBRARY.trigger.nodeType,
            description: FLOW_NODE_LIBRARY.trigger.description,
        },
    },
    {
        id: 'ai-1',
        position: { x: 360, y: 80 },
        data: {
            label: 'Local AI Summary',
            kind: 'ai',
            nodeType: FLOW_NODE_LIBRARY.ai.nodeType,
            description: FLOW_NODE_LIBRARY.ai.description,
        },
    },
];

const INITIAL_FLOW_EDGES: Edge[] = [
    { id: 'edge-1', source: 'trigger-1', target: 'ai-1', type: 'smoothstep', animated: true, style: { stroke: '#3B82F6', strokeWidth: 1.5, opacity: 0.7 } },
];

function nodeStyle(kind: FlowKind): Record<string, string | number> {
    const color = FLOW_NODE_LIBRARY[kind].color;
    return {
        border: `1px solid ${color}40`,
        borderRadius: 8,
        padding: '10px 14px',
        color: '#F0F0F5',
        background: '#1A1A1E',
        boxShadow: `0 0 0 1px ${color}18, 0 2px 8px rgba(0,0,0,0.4)`,
        fontSize: '12px',
        fontFamily: '"Outfit", sans-serif',
        minWidth: 140,
    };
}

function inferKind(nodeType: string, fallback = ''): FlowKind {
    const maybe = fallback.trim().toLowerCase();
    if (['trigger', 'action', 'logic', 'ai', 'integration', 'research'].includes(maybe)) return maybe as FlowKind;
    const t = nodeType.toLowerCase();
    if (t.includes('trigger') || t.includes('webhook') || t.includes('cron')) return 'trigger';
    if (t.includes('logic') || t.includes('if') || t.includes('condition')) return 'logic';
    if (t.includes('research') || t.includes('search')) return 'research';
    if (t.includes('ai') || t.includes('ollama')) return 'ai';
    if (t.includes('integration') || t.includes('http')) return 'integration';
    return 'action';
}

function toGraph(name: string, description: string, nodes: Node<FlowNodeData>[], edges: Edge[]): Record<string, unknown> {
    return {
        schema: 'jimai.workflow.v1',
        name: name || 'jimAI Open Workflow',
        notes: description || '',
        nodes: nodes.map((node) => ({
            id: node.id,
            label: node.data.label,
            kind: node.data.kind,
            type: node.data.nodeType,
            description: node.data.description,
            position: { x: Math.round(node.position.x), y: Math.round(node.position.y) },
            config: {},
        })),
        edges: edges.map((edge) => ({
            id: edge.id || `${edge.source}-${edge.target}`,
            source: edge.source,
            target: edge.target,
        })),
    };
}

function fromGraph(graph: Record<string, unknown>): { nodes: Node<FlowNodeData>[]; edges: Edge[] } {
    const rawNodes = Array.isArray(graph.nodes) ? (graph.nodes as Array<Record<string, unknown>>) : [];
    const rawEdges = Array.isArray(graph.edges) ? (graph.edges as Array<Record<string, unknown>>) : [];
    if (rawNodes.length === 0) return { nodes: INITIAL_FLOW_NODES, edges: INITIAL_FLOW_EDGES };
    const nodes: Node<FlowNodeData>[] = rawNodes.map((raw, idx) => {
        const id = String(raw.id || `node-${idx + 1}`);
        const nodeType = String(raw.type || FLOW_NODE_LIBRARY.action.nodeType);
        const kind = inferKind(nodeType, String(raw.kind || ''));
        const pos = raw.position as { x?: number; y?: number } | undefined;
        const x = Number(pos?.x || 80 + (idx % 4) * 220);
        const y = Number(pos?.y || 80 + Math.floor(idx / 4) * 160);
        return {
            id,
            position: { x, y },
            data: {
                label: String(raw.label || raw.name || `${FLOW_NODE_LIBRARY[kind].title} ${idx + 1}`),
                kind,
                nodeType,
                description: String(raw.description || FLOW_NODE_LIBRARY[kind].description),
            },
            style: nodeStyle(kind),
        };
    });
    const edges: Edge[] = rawEdges
        .map((raw, idx) => {
            const source = String(raw.source || '');
            const target = String(raw.target || '');
            if (!source || !target) return null;
            return {
                id: String(raw.id || `edge-${idx + 1}`),
                source,
                target,
                type: 'smoothstep',
                animated: true,
                style: { stroke: '#d9d9d9' },
            } as Edge;
        })
        .filter((row): row is Edge => row !== null);
    return { nodes, edges };
}

export default function Automation() {
    const [status, setStatus] = useState<agentApi.AutomationWorkflowStatus | null>(null);
    const [templates, setTemplates] = useState<agentApi.AutomationWorkflowTemplate[]>([]);
    const [workflows, setWorkflows] = useState<agentApi.AutomationWorkflowSummary[]>([]);
    const [selectedWorkflowId, setSelectedWorkflowId] = useState('');
    const [workflowName, setWorkflowName] = useState('jimAI Open Workflow');
    const [workflowDescription, setWorkflowDescription] = useState('');
    const [workflowTags, setWorkflowTags] = useState('automation, open-source');
    const [runInput, setRunInput] = useState('{\n  "message": "run workflow"\n}');
    const [runOutput, setRunOutput] = useState('');
    const [selectedNodeId, setSelectedNodeId] = useState(INITIAL_FLOW_NODES[0]?.id || '');
    const [nodes, setNodes, onNodesChange] = useNodesState<FlowNodeData>(INITIAL_FLOW_NODES);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(INITIAL_FLOW_EDGES);
    const [loading, setLoading] = useState(true);
    const [working, setWorking] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const refresh = useCallback(async () => {
        const [s, t, w] = await Promise.all([
            agentApi.getAutomationWorkflowStatus(),
            agentApi.listAutomationWorkflowTemplates(),
            agentApi.listAutomationWorkflows(200),
        ]);
        setStatus(s);
        setTemplates(t);
        setWorkflows(w);
    }, []);

    useEffect(() => {
        setLoading(true);
        refresh()
            .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load workflows.'))
            .finally(() => setLoading(false));
    }, [refresh]);

    const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) || null, [nodes, selectedNodeId]);
    const graph = useMemo(() => toGraph(workflowName.trim(), workflowDescription.trim(), nodes, edges), [workflowDescription, workflowName, nodes, edges]);
    const graphJson = useMemo(() => JSON.stringify(graph, null, 2), [graph]);

    const onConnect = useCallback(
        (params: Connection) =>
            setEdges((current) =>
                addEdge({ ...params, type: 'smoothstep', animated: true, style: { stroke: '#3B82F6', strokeWidth: 1.5, opacity: 0.7 } }, current),
            ),
        [setEdges],
    );

    const addNode = useCallback(
        (kind: FlowKind) => {
            const cfg = FLOW_NODE_LIBRARY[kind];
            setNodes((current) => {
                const idx = current.length + 1;
                const node: Node<FlowNodeData> = {
                    id: `${kind}-${Date.now()}-${idx}`,
                    position: { x: 80 + ((idx - 1) % 4) * 220, y: 80 + Math.floor((idx - 1) / 4) * 160 },
                    data: { label: `${cfg.title} ${idx}`, kind, nodeType: cfg.nodeType, description: cfg.description },
                    style: nodeStyle(kind),
                };
                return [...current, node];
            });
        },
        [setNodes],
    );

    const saveWorkflow = useCallback(async () => {
        setWorking(true);
        setError('');
        setMessage('');
        try {
            const saved = await agentApi.upsertAutomationWorkflow({
                id: selectedWorkflowId || undefined,
                name: workflowName.trim() || 'jimAI Open Workflow',
                description: workflowDescription,
                tags: workflowTags.split(',').map((v) => v.trim()).filter(Boolean),
                graph,
                public_sources: status?.public_sources || [],
            });
            setSelectedWorkflowId(saved.id);
            await refresh();
            setMessage(`Saved workflow: ${saved.name}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Save failed.');
        } finally {
            setWorking(false);
        }
    }, [graph, refresh, selectedWorkflowId, status?.public_sources, workflowDescription, workflowName, workflowTags]);

    const loadWorkflow = useCallback(
        async (workflowId: string) => {
            if (!workflowId) return;
            setWorking(true);
            setError('');
            setMessage('');
            try {
                const row = await agentApi.getAutomationWorkflow(workflowId);
                const next = fromGraph(row.graph || {});
                setSelectedWorkflowId(row.id);
                setWorkflowName(row.name || 'jimAI Open Workflow');
                setWorkflowDescription(row.description || '');
                setWorkflowTags((row.tags || []).join(', '));
                setNodes(next.nodes);
                setEdges(next.edges);
                setSelectedNodeId(next.nodes[0]?.id || '');
                setMessage(`Loaded: ${row.name}`);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Load failed.');
            } finally {
                setWorking(false);
            }
        },
        [setEdges, setNodes],
    );

    const runWorkflow = useCallback(async () => {
        setWorking(true);
        setError('');
        setMessage('');
        try {
            let workflowId = selectedWorkflowId;
            if (!workflowId) {
                const saved = await agentApi.upsertAutomationWorkflow({
                    name: workflowName.trim() || 'jimAI Open Workflow',
                    description: workflowDescription,
                    tags: workflowTags.split(',').map((v) => v.trim()).filter(Boolean),
                    graph,
                    public_sources: status?.public_sources || [],
                });
                workflowId = saved.id;
                setSelectedWorkflowId(saved.id);
            }
            const parsed = runInput.trim() ? JSON.parse(runInput) : {};
            const result = await agentApi.runAutomationWorkflow(workflowId, { input: parsed, continue_on_error: true, max_steps: 200 });
            setRunOutput(JSON.stringify(result, null, 2));
            await refresh();
            setMessage(`Run status: ${result.status}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Run failed.');
        } finally {
            setWorking(false);
        }
    }, [graph, refresh, runInput, selectedWorkflowId, status?.public_sources, workflowDescription, workflowName, workflowTags]);

    return (
        <div className="h-full overflow-auto p-6 md:p-8">
            <div className="mx-auto w-full max-w-[min(120rem,calc(100%-2rem))] space-y-5">
                <PageHeader
                    title="Workflow Studio"
                    description="Open-source native workflows — local jimAI runtime, not n8n."
                    meta={
                        <span className="font-mono text-[11px]">
                            engine: {status?.engine || 'jimai-open-workflow'} &nbsp;·&nbsp; workflows: {status?.workflow_count ?? 0}
                        </span>
                    }
                />

                {/* Workflow config */}
                <section className="rounded-card border border-surface-4 bg-surface-1 p-5">
                    <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
                        <input
                            value={workflowName}
                            onChange={(e) => setWorkflowName(e.target.value)}
                            placeholder="Workflow name"
                            className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary"
                        />
                        <input
                            value={workflowDescription}
                            onChange={(e) => setWorkflowDescription(e.target.value)}
                            placeholder="Description"
                            className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary"
                        />
                        <input
                            value={workflowTags}
                            onChange={(e) => setWorkflowTags(e.target.value)}
                            placeholder="Tags: automation, open-source"
                            className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary md:col-span-2"
                        />
                    </div>
                    <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
                        <select
                            value={selectedWorkflowId}
                            onChange={(e) => {
                                const id = e.target.value;
                                setSelectedWorkflowId(id);
                                if (id) loadWorkflow(id).catch(() => {});
                            }}
                            className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary"
                        >
                            <option value="">Select saved workflow…</option>
                            {workflows.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                        </select>
                        <button
                            type="button"
                            onClick={() => saveWorkflow().catch(() => {})}
                            disabled={working}
                            className="rounded-btn border border-surface-4 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary disabled:opacity-40"
                        >
                            Save
                        </button>
                        <button
                            type="button"
                            onClick={() => runWorkflow().catch(() => {})}
                            disabled={working}
                            className="rounded-btn bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
                        >
                            Run
                        </button>
                        <button
                            type="button"
                            onClick={() => navigator.clipboard.writeText(graphJson).catch(() => {})}
                            className="rounded-btn border border-surface-4 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary"
                        >
                            Copy JSON
                        </button>
                    </div>
                    {message && <p className="mt-2 text-xs font-medium text-accent-green">{message}</p>}
                    {error && <p className="mt-2 text-xs text-accent-red">{error}</p>}
                    {loading && <p className="mt-2 text-xs text-text-muted">Loading…</p>}
                </section>

                {/* Canvas + Node config */}
                <section className="rounded-card border border-surface-4 bg-surface-1 p-4">
                    {/* Node library */}
                    <div className="mb-3 flex flex-wrap gap-1.5">
                        {(['trigger', 'action', 'logic', 'ai', 'integration', 'research'] as FlowKind[]).map((kind) => (
                            <button
                                key={kind}
                                type="button"
                                onClick={() => addNode(kind)}
                                className="rounded-badge border px-3 py-1 text-xs font-medium transition-colors hover:opacity-80"
                                style={{ borderColor: `${FLOW_NODE_LIBRARY[kind].color}50`, color: FLOW_NODE_LIBRARY[kind].color, background: `${FLOW_NODE_LIBRARY[kind].color}12` }}
                            >
                                + {FLOW_NODE_LIBRARY[kind].title}
                            </button>
                        ))}
                    </div>

                    <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                        {/* Canvas */}
                        <div className="overflow-hidden rounded-btn border border-surface-4 bg-surface-0">
                            <div className="h-[520px]">
                                <ReactFlow
                                    nodes={nodes}
                                    edges={edges}
                                    onNodesChange={onNodesChange}
                                    onEdgesChange={onEdgesChange}
                                    onConnect={onConnect}
                                    onNodeClick={(_, n) => setSelectedNodeId(n.id)}
                                    fitView
                                >
                                    <MiniMap
                                        nodeColor={(n) => FLOW_NODE_LIBRARY[((n.data as FlowNodeData)?.kind || 'action') as FlowKind].color}
                                        pannable
                                        zoomable
                                    />
                                    <Controls />
                                    <Background gap={24} color="#2A2A30" variant={'dots' as never} />
                                </ReactFlow>
                            </div>
                        </div>

                        {/* Right panel: node config + run input */}
                        <div className="space-y-3">
                            <div className="rounded-btn border border-surface-4 bg-surface-0 p-3">
                                <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                                    Selected Node
                                </p>
                                {selectedNode ? (
                                    <div className="space-y-2">
                                        <input
                                            value={selectedNode.data.label}
                                            onChange={(e) => setNodes((rows) => rows.map((r) => (r.id === selectedNode.id ? { ...r, data: { ...r.data, label: e.target.value } } : r)))}
                                            className="w-full rounded-btn border border-surface-4 bg-surface-1 px-2.5 py-1.5 text-xs text-text-primary"
                                        />
                                        <select
                                            value={selectedNode.data.kind}
                                            onChange={(e) => {
                                                const kind = e.target.value as FlowKind;
                                                const lib = FLOW_NODE_LIBRARY[kind];
                                                setNodes((rows) =>
                                                    rows.map((r) =>
                                                        r.id === selectedNode.id
                                                            ? { ...r, data: { ...r.data, kind, nodeType: lib.nodeType }, style: nodeStyle(kind) }
                                                            : r,
                                                    ),
                                                );
                                            }}
                                            className="w-full rounded-btn border border-surface-4 bg-surface-1 px-2.5 py-1.5 text-xs text-text-primary"
                                        >
                                            {(['trigger', 'action', 'logic', 'ai', 'integration', 'research'] as FlowKind[]).map((kind) => (
                                                <option key={kind} value={kind}>{FLOW_NODE_LIBRARY[kind].title}</option>
                                            ))}
                                        </select>
                                        <input
                                            value={selectedNode.data.nodeType}
                                            onChange={(e) => setNodes((rows) => rows.map((r) => (r.id === selectedNode.id ? { ...r, data: { ...r.data, nodeType: e.target.value } } : r)))}
                                            className="w-full rounded-btn border border-surface-4 bg-surface-1 px-2.5 py-1.5 font-mono text-[11px] text-text-muted"
                                            placeholder="node type"
                                        />
                                        <textarea
                                            value={selectedNode.data.description}
                                            onChange={(e) => setNodes((rows) => rows.map((r) => (r.id === selectedNode.id ? { ...r, data: { ...r.data, description: e.target.value } } : r)))}
                                            rows={3}
                                            className="w-full resize-y rounded-btn border border-surface-4 bg-surface-1 px-2.5 py-1.5 text-xs text-text-primary"
                                        />
                                    </div>
                                ) : (
                                    <p className="text-xs text-text-muted">Click a node on the canvas to inspect.</p>
                                )}
                            </div>

                            <div>
                                <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Run Input (JSON)</p>
                                <textarea
                                    value={runInput}
                                    onChange={(e) => setRunInput(e.target.value)}
                                    rows={7}
                                    className="w-full resize-y rounded-btn border border-surface-4 bg-surface-0 px-2.5 py-2 font-mono text-[11px] text-text-primary"
                                />
                            </div>
                        </div>
                    </div>
                </section>

                {/* Run output */}
                <section className="rounded-card border border-surface-4 bg-surface-1 p-4">
                    <h2 className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Run Output</h2>
                    <textarea
                        value={runOutput}
                        readOnly
                        rows={10}
                        className="w-full resize-y rounded-btn border border-surface-4 bg-surface-0 px-2.5 py-2 font-mono text-[11px] text-text-primary"
                    />
                </section>

                {/* Templates */}
                {templates.length > 0 && (
                    <section className="rounded-card border border-surface-4 bg-surface-1 p-4">
                        <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Templates</h2>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            {templates.map((template) => (
                                <div key={template.name} className="rounded-btn border border-surface-4 bg-surface-0 p-3">
                                    <p className="text-sm font-medium text-text-primary">{template.name}</p>
                                    <p className="mt-1 text-xs text-text-secondary">{template.description}</p>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            const next = fromGraph(template.graph || {});
                                            setNodes(next.nodes);
                                            setEdges(next.edges);
                                            setWorkflowName(template.name);
                                            setWorkflowDescription(template.description || '');
                                            setSelectedWorkflowId('');
                                        }}
                                        className="mt-3 rounded-btn border border-surface-4 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary"
                                    >
                                        Load template
                                    </button>
                                </div>
                            ))}
                        </div>
                    </section>
                )}

                {/* Open-source references */}
                {(status?.public_sources || []).length > 0 && (
                    <section className="rounded-card border border-surface-4 bg-surface-1 p-4">
                        <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Open-Source References</h2>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            {(status?.public_sources || []).map((source) => (
                                <div key={source.url} className="rounded-btn border border-surface-4 bg-surface-0 p-3">
                                    <p className="text-sm font-medium text-text-primary">{source.name}</p>
                                    <p className="mt-0.5 font-mono text-[10px] text-text-muted">{source.license || ''}</p>
                                    <p className="mt-1 text-xs text-text-secondary">{source.why || ''}</p>
                                    <button
                                        type="button"
                                        onClick={() => window.open(source.url, '_blank', 'noopener,noreferrer')}
                                        className="mt-3 rounded-btn border border-surface-4 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary"
                                    >
                                        Open repo ↗
                                    </button>
                                </div>
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </div>
    );
}
