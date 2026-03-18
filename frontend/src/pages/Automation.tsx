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

type FlowKind = 'trigger' | 'action' | 'logic' | 'ai' | 'integration' | 'research';

type FlowNodeData = {
    label: string;
    kind: FlowKind;
    nodeType: string;
    description: string;
};

const FLOW_NODE_LIBRARY: Record<FlowKind, { title: string; nodeType: string; color: string; description: string }> = {
    trigger: { title: 'Trigger', nodeType: 'jimai.trigger.manual', color: '#6f6f6f', description: 'Entry point.' },
    action: { title: 'Action', nodeType: 'jimai.action.transform', color: '#9f9f9f', description: 'Transform payload.' },
    logic: { title: 'Logic', nodeType: 'jimai.logic.condition', color: '#bfbfbf', description: 'Conditional gate.' },
    ai: { title: 'Local AI', nodeType: 'jimai.ai.ollama', color: '#dfdfdf', description: 'Local Ollama node.' },
    integration: { title: 'Integration', nodeType: 'jimai.integration.http', color: '#f0f0f0', description: 'HTTP integration.' },
    research: { title: 'Research', nodeType: 'jimai.research.search', color: '#cfcfcf', description: 'Web research node.' },
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
    { id: 'edge-1', source: 'trigger-1', target: 'ai-1', type: 'smoothstep', animated: true, style: { stroke: '#d9d9d9' } },
];

function nodeStyle(kind: FlowKind): Record<string, string | number> {
    return {
        border: `1px solid ${FLOW_NODE_LIBRARY[kind].color}`,
        borderRadius: 10,
        padding: 8,
        color: '#f5f5f5',
        background: '#0f0f0f',
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
                addEdge({ ...params, type: 'smoothstep', animated: true, style: { stroke: '#d9d9d9' } }, current),
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
        <div className="h-full overflow-auto p-5 md:p-8">
            <div className="mx-auto w-full max-w-7xl space-y-6">
                <section className="rounded-card border border-surface-3 bg-surface-1 p-5 md:p-6">
                    <h1 className="text-lg font-semibold text-text-primary">Automation (Open Workflow Studio)</h1>
                    <p className="text-xs text-text-secondary mt-2">Open-source native workflows, not connected to n8n runtime.</p>
                    <p className="text-xs text-text-secondary mt-2">
                        Engine: {status?.engine || 'jimai-open-workflow'} | workflows: {status?.workflow_count ?? 0}
                    </p>
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                        <input value={workflowName} onChange={(e) => setWorkflowName(e.target.value)} placeholder="Workflow name" className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary outline-none" />
                        <input value={workflowDescription} onChange={(e) => setWorkflowDescription(e.target.value)} placeholder="Description" className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary outline-none" />
                        <input value={workflowTags} onChange={(e) => setWorkflowTags(e.target.value)} placeholder="tags: automation, open-source" className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary outline-none md:col-span-2" />
                    </div>
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_auto_auto_auto] gap-2">
                        <select
                            value={selectedWorkflowId}
                            onChange={(e) => {
                                const id = e.target.value;
                                setSelectedWorkflowId(id);
                                if (id) loadWorkflow(id).catch(() => {});
                            }}
                            className="rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary outline-none"
                        >
                            <option value="">Select saved workflow</option>
                            {workflows.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                        </select>
                        <button type="button" onClick={() => saveWorkflow().catch(() => {})} disabled={working} className="px-4 py-2 rounded-btn border border-surface-4 text-sm text-text-primary disabled:opacity-40">Save</button>
                        <button type="button" onClick={() => runWorkflow().catch(() => {})} disabled={working} className="px-4 py-2 rounded-btn border border-surface-4 text-sm text-text-primary disabled:opacity-40">Run</button>
                        <button type="button" onClick={() => navigator.clipboard.writeText(graphJson).catch(() => {})} className="px-4 py-2 rounded-btn border border-surface-4 text-sm text-text-primary">Copy JSON</button>
                    </div>
                    {message && <p className="text-sm text-accent-green mt-2">{message}</p>}
                    {error && <p className="text-sm text-accent-red mt-2">{error}</p>}
                    {loading && <p className="text-xs text-text-secondary mt-2">Loading...</p>}
                </section>

                <section className="rounded-card border border-surface-3 bg-surface-1 p-4">
                    <div className="flex flex-wrap gap-2 mb-3">
                        {(['trigger', 'action', 'logic', 'ai', 'integration', 'research'] as FlowKind[]).map((kind) => (
                            <button key={kind} type="button" onClick={() => addNode(kind)} className="px-3 py-1.5 rounded-btn border text-xs text-text-primary" style={{ borderColor: FLOW_NODE_LIBRARY[kind].color }}>
                                + {FLOW_NODE_LIBRARY[kind].title}
                            </button>
                        ))}
                    </div>
                    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-3">
                        <div className="rounded-btn border border-surface-3 bg-surface-0 overflow-hidden"><div className="h-[520px]">
                            <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, n) => setSelectedNodeId(n.id)} fitView>
                                <MiniMap nodeColor={(n) => FLOW_NODE_LIBRARY[((n.data as FlowNodeData)?.kind || 'action') as FlowKind].color} pannable zoomable />
                                <Controls />
                                <Background gap={20} color="#1d1d1d" />
                            </ReactFlow>
                        </div></div>
                        <div className="space-y-3">
                            <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                <p className="text-[11px] text-text-secondary uppercase">Selected Node</p>
                                {selectedNode && (
                                    <div className="mt-2 space-y-2">
                                        <input value={selectedNode.data.label} onChange={(e) => setNodes((rows) => rows.map((r) => (r.id === selectedNode.id ? { ...r, data: { ...r.data, label: e.target.value } } : r)))} className="w-full rounded-btn border border-surface-4 bg-surface-1 px-2 py-1.5 text-xs text-text-primary outline-none" />
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
                                            className="w-full rounded-btn border border-surface-4 bg-surface-1 px-2 py-1.5 text-xs text-text-primary outline-none"
                                        >
                                            {(['trigger', 'action', 'logic', 'ai', 'integration', 'research'] as FlowKind[]).map((kind) => (
                                                <option key={kind} value={kind}>
                                                    {FLOW_NODE_LIBRARY[kind].title}
                                                </option>
                                            ))}
                                        </select>
                                        <input value={selectedNode.data.nodeType} onChange={(e) => setNodes((rows) => rows.map((r) => (r.id === selectedNode.id ? { ...r, data: { ...r.data, nodeType: e.target.value } } : r)))} className="w-full rounded-btn border border-surface-4 bg-surface-1 px-2 py-1.5 text-xs text-text-primary outline-none" />
                                        <textarea value={selectedNode.data.description} onChange={(e) => setNodes((rows) => rows.map((r) => (r.id === selectedNode.id ? { ...r, data: { ...r.data, description: e.target.value } } : r)))} rows={3} className="w-full rounded-btn border border-surface-4 bg-surface-1 px-2 py-1.5 text-xs text-text-primary outline-none resize-y" />
                                    </div>
                                )}
                            </div>
                            <textarea value={runInput} onChange={(e) => setRunInput(e.target.value)} rows={6} className="w-full rounded-btn border border-surface-4 bg-surface-0 px-2 py-1.5 text-[11px] text-text-primary font-mono outline-none resize-y" />
                        </div>
                    </div>
                </section>

                <section className="rounded-card border border-surface-3 bg-surface-1 p-4">
                    <h2 className="text-sm font-semibold text-text-primary">Run Output</h2>
                    <textarea value={runOutput} readOnly rows={12} className="mt-2 w-full rounded-btn border border-surface-4 bg-surface-0 px-2 py-1.5 text-[11px] text-text-primary font-mono outline-none resize-y" />
                </section>

                <section className="rounded-card border border-surface-3 bg-surface-1 p-4">
                    <h2 className="text-sm font-semibold text-text-primary">Templates</h2>
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                        {templates.map((template) => (
                            <div key={template.name} className="rounded-btn border border-surface-3 bg-surface-0 p-3 space-y-2">
                                <p className="text-sm text-text-primary">{template.name}</p>
                                <p className="text-xs text-text-secondary">{template.description}</p>
                                <button type="button" onClick={() => {
                                    const next = fromGraph(template.graph || {});
                                    setNodes(next.nodes);
                                    setEdges(next.edges);
                                    setWorkflowName(template.name);
                                    setWorkflowDescription(template.description || '');
                                    setSelectedWorkflowId('');
                                }} className="px-3 py-1.5 rounded-btn border border-surface-4 text-xs text-text-primary">Load Template</button>
                            </div>
                        ))}
                    </div>
                </section>

                <section className="rounded-card border border-surface-3 bg-surface-1 p-4">
                    <h2 className="text-sm font-semibold text-text-primary">Open-Source References</h2>
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                        {(status?.public_sources || []).map((source) => (
                            <div key={source.url} className="rounded-btn border border-surface-3 bg-surface-0 p-3 space-y-2">
                                <p className="text-sm text-text-primary">{source.name}</p>
                                <p className="text-[11px] text-text-muted">{source.license || ''}</p>
                                <p className="text-xs text-text-secondary">{source.why || ''}</p>
                                <button type="button" onClick={() => window.open(source.url, '_blank', 'noopener,noreferrer')} className="px-3 py-1.5 rounded-btn border border-surface-4 text-xs text-text-primary">Open Repo</button>
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}
