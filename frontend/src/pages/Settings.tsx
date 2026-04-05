import { useCallback, useEffect, useState } from 'react';
import * as agentApi from '../lib/agentSpaceApi';
import { getStoredGitHubToken, setStoredGitHubToken } from '../lib/githubApi';
import { PageHeader } from '../components/PageHeader';

export default function Settings() {
    const [settings, setSettings] = useState<Record<string, unknown>>({});
    const [logs, setLogs] = useState<agentApi.ActionLogEntry[]>([]);
    const [proactiveStatus, setProactiveStatus] = useState<Record<string, unknown>>({});
    const [freeStackStatus, setFreeStackStatus] = useState<agentApi.FreeStackStatus | null>(null);
    const [proactiveGoals, setProactiveGoals] = useState<agentApi.ProactiveGoal[]>([]);
    const [newGoalName, setNewGoalName] = useState('Auto Self-Improve');
    const [newGoalObjective, setNewGoalObjective] = useState('Run self-improvement analysis and propose updates');
    const [newGoalInterval, setNewGoalInterval] = useState('900');
    const [indexQuery, setIndexQuery] = useState('');
    const [indexResults, setIndexResults] = useState<Array<Record<string, unknown>>>([]);
    const [agentModelsText, setAgentModelsText] = useState('{}');
    const [jsonError, setJsonError] = useState<string | null>(null);
    const [notificationPermission, setNotificationPermission] = useState<'granted' | 'denied' | 'default' | 'unsupported'>('unsupported');
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        try {
            const [settingsData, logRows, proactiveData, goalRows, freeStackData] = await Promise.all([
                agentApi.getSettings(),
                agentApi.getActionLogs(80),
                agentApi.getProactiveStatus(),
                agentApi.listProactiveGoals(200),
                agentApi.getFreeStackStatus(true),
            ]);
            if (!settingsData.github_token && getStoredGitHubToken()) {
                settingsData.github_token = getStoredGitHubToken();
            }
            setSettings(settingsData);
            setLogs(logRows);
            setProactiveStatus(proactiveData);
            setProactiveGoals(goalRows);
            setFreeStackStatus(freeStackData);
            setError('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load settings.');
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        const raw = settings.agent_models;
        if (raw && typeof raw === 'object') {
            try {
                setAgentModelsText(JSON.stringify(raw, null, 2));
            } catch {
                setAgentModelsText('{}');
            }
        }
    }, [settings.agent_models]);

    useEffect(() => {
        if (typeof window === 'undefined' || !('Notification' in window)) {
            setNotificationPermission('unsupported');
            return;
        }
        setNotificationPermission(Notification.permission);
    }, []);

    const patchSetting = async (updates: Record<string, unknown>, successMessage = 'Settings updated.') => {
        setMessage('');
        setError('');
        setSaving(true);
        try {
            const updated = await agentApi.updateSettings(updates);
            setSettings(updated);
            setMessage(successMessage);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update settings.');
        } finally {
            setSaving(false);
        }
    };

    const requestNotificationPermission = async () => {
        setMessage('');
        setError('');
        if (typeof window === 'undefined' || !('Notification' in window)) {
            setError('Notifications are not supported in this browser.');
            return;
        }
        try {
            const permission = await Notification.requestPermission();
            setNotificationPermission(permission);
            if (permission === 'granted') {
                setMessage('Notification permission granted for this device.');
            } else {
                setError(`Notification permission is ${permission}.`);
            }
        } catch {
            setError('Failed to request notification permission.');
        }
    };

    const refreshFreeStackStatus = async () => {
        setMessage('');
        setError('');
        try {
            const data = await agentApi.getFreeStackStatus(true);
            setFreeStackStatus(data);
            setMessage('Free-stack status refreshed.');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to refresh free-stack status.');
        }
    };

    const syncFreeStack = async () => {
        setMessage('');
        setError('');
        try {
            const data = await agentApi.syncFreeStackSettings();
            setSettings(data.settings || {});
            setFreeStackStatus(data.status || null);
            setMessage('Free-stack settings synced from secure env.');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to sync free-stack settings.');
        }
    };

    const sendTestPhoneNotification = async () => {
        setMessage('');
        setError('');
        try {
            const result = await agentApi.sendFreeStackTestNotification({
                title: 'jimAI Test',
                message: 'Free-stack Gotify integration is working.',
                priority: 5,
            });
            if (result.skipped) {
                setMessage(`Notification skipped: ${String(result.error || 'disabled')}`);
            } else {
                setMessage('Test notification sent.');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send test notification.');
        }
    };

    const rebuildIndex = async () => {
        setMessage('');
        setError('');
        try {
            const data = await agentApi.rebuildIndex();
            setMessage(`Code index rebuilt: ${data.indexed_files} files.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to rebuild index.');
        }
    };

    const searchIndex = async () => {
        setMessage('');
        setError('');
        try {
            const data = await agentApi.searchIndex(indexQuery, 20);
            setIndexResults(data.results || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Index search failed.');
        }
    };

    const setProactiveRunning = async (enabled: boolean) => {
        setMessage('');
        setError('');
        try {
            if (enabled) await agentApi.startProactive();
            else await agentApi.stopProactive();
            const status = await agentApi.getProactiveStatus();
            setProactiveStatus(status);
            setMessage(`Proactive engine ${enabled ? 'started' : 'stopped'}.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed proactive toggle.');
        }
    };

    const tickProactive = async () => {
        setMessage('');
        setError('');
        try {
            const data = await agentApi.tickProactive();
            setMessage(`Proactive tick complete. triggered=${(data.triggered || []).length}`);
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed proactive tick.');
        }
    };

    const addGoal = async () => {
        setMessage('');
        setError('');
        try {
            await agentApi.createProactiveGoal({
                name: newGoalName,
                objective: newGoalObjective,
                interval_seconds: Number(newGoalInterval) || 900,
                enabled: true,
                run_template: {
                    autonomous: false,
                    review_gate: true,
                    subagents: [{ id: 'self-improver', role: 'coder', depends_on: [], actions: [{ type: 'self_improve' }] }],
                },
            });
            await load();
            setMessage('Proactive goal added.');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed adding proactive goal.');
        }
    };

    const runSelfImproveNow = async () => {
        setMessage('');
        setError('');
        try {
            const focus = String(settings.self_learning_focus ?? 'general').trim() || 'general';
            const run = await agentApi.runSelfImprove({
                prompt: `Run focused self-improvement for jimAI (${focus}).`,
                confirmed_suggestions: [`Prioritize self-learning focus area: ${focus}.`],
            });
            setMessage(`Self-improvement run queued: ${run.id}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Self-improvement run failed.');
        }
    };

    const resetRuntimeData = async () => {
        setMessage('');
        setError('');
        try {
            const result = await agentApi.resetAgentSpaceData({
                clear_reviews: true,
                clear_runs: true,
                clear_snapshots: true,
                clear_logs: true,
                clear_memory: true,
                clear_index: true,
                clear_chats: true,
                clear_runtime: true,
                clear_generated: true,
                clear_self_improvement: true,
                clear_proactive_goals: true,
                clear_teams: false,
                clear_exports: false,
                reset_settings: false,
            });
            await load();
            setMessage(`jimAI runtime data reset. Cleared: ${Object.keys(result.removed || {}).join(', ')}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to reset jimAI runtime data.');
        }
    };

    const saveAgentModelMap = async () => {
        setMessage('');
        setError('');
        try {
            const parsed = JSON.parse(agentModelsText || '{}');
            if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                setError('Agent model map must be a JSON object.');
                return;
            }
            const normalized: Record<string, string> = {};
            for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
                const k = String(key || '').trim();
                const v = String(value || '').trim();
                if (!k || !v) continue;
                normalized[k] = v;
            }
            const count = Object.keys(normalized).length;
            await patchSetting(
                { agent_models: normalized },
                count > 0 ? `Agent model map saved (${count} entries).` : 'Agent model map cleared.',
            );
        } catch {
            setError('Invalid JSON for agent model map.');
        }
    };

    return (
        <div className="h-full overflow-auto p-6 md:p-10">
            <div className="mx-auto w-full max-w-[min(112rem,calc(100%-2rem))] space-y-6">
            <section className="rounded-card border border-surface-4 bg-surface-1 p-6 md:p-8">
                <PageHeader
                    variant="embedded"
                    title="Settings"
                    description="Core controls for model, safety, and automation."
                    actions={
                        <button
                            type="button"
                            onClick={resetRuntimeData}
                            className="px-3 py-2 rounded-btn border border-accent-red/40 text-accent-red text-xs"
                        >
                            Reset Runtime Data (Clear Diffs/Runs)
                        </button>
                    }
                />

                <div className="mt-5 grid md:grid-cols-2 gap-4">
                    <InputField
                        label="Default Model"
                        value={String(settings.model ?? '')}
                        onChange={(value) => patchSetting({ model: value })}
                        placeholder="qwen2.5-coder:14b"
                    />
                    <SelectField
                        label="Command Profile"
                        value={String(settings.command_profile ?? 'safe')}
                        options={['safe', 'dev', 'unrestricted']}
                        onChange={(value) => patchSetting({ command_profile: value })}
                    />
                    <InputField
                        label="Max Actions"
                        value={String(settings.max_actions ?? 40)}
                        onChange={(value) => patchSetting({ max_actions: Number(value) || 40 })}
                    />
                    <InputField
                        label="Max Seconds"
                        value={String(settings.max_seconds ?? 1200)}
                        onChange={(value) => patchSetting({ max_seconds: Number(value) || 1200 })}
                    />
                    <InputField
                        label="Subagent Retries"
                        value={String(settings.subagent_retry_attempts ?? 2)}
                        onChange={(value) => patchSetting({ subagent_retry_attempts: Math.max(0, Number(value) || 0) })}
                    />
                </div>

                <div className="mt-4 grid md:grid-cols-3 gap-3">
                    <ToggleChip
                        label="Review Gate"
                        enabled={Boolean(settings.review_gate)}
                        onToggle={() => patchSetting({ review_gate: !settings.review_gate })}
                    />
                    <ToggleChip
                        label="Allow Shell"
                        enabled={Boolean(settings.allow_shell)}
                        onToggle={() => patchSetting({ allow_shell: !settings.allow_shell })}
                    />
                    <ToggleChip
                        label="Release GPU on OFF"
                        enabled={Boolean(settings.release_gpu_on_off)}
                        onToggle={() => patchSetting({ release_gpu_on_off: !settings.release_gpu_on_off })}
                    />
                </div>
                <div className="mt-4 grid md:grid-cols-2 gap-3">
                    <ToggleChip
                        label="Self Learning"
                        enabled={Boolean(settings.self_learning_enabled ?? true)}
                        onToggle={() => patchSetting({ self_learning_enabled: !(settings.self_learning_enabled ?? true) })}
                    />
                    <ToggleChip
                        label="Autonomous Web Research"
                        enabled={Boolean(settings.autonomous_web_research_enabled ?? true)}
                        onToggle={() => patchSetting({ autonomous_web_research_enabled: !(settings.autonomous_web_research_enabled ?? true) })}
                    />
                    <ToggleChip
                        label="Smart Chat Web Search"
                        enabled={Boolean(settings.chat_auto_web_research_enabled ?? true)}
                        onToggle={() => patchSetting({ chat_auto_web_research_enabled: !(settings.chat_auto_web_research_enabled ?? true) })}
                    />
                    <ToggleChip
                        label="Smart Run Research"
                        enabled={Boolean(settings.run_auto_force_research_enabled ?? true)}
                        onToggle={() => patchSetting({ run_auto_force_research_enabled: !(settings.run_auto_force_research_enabled ?? true) })}
                    />
                    <ToggleChip
                        label="Strict Verification"
                        enabled={Boolean(settings.strict_verification ?? false)}
                        onToggle={() => patchSetting({ strict_verification: !(settings.strict_verification ?? false) })}
                    />
                    <ToggleChip
                        label="Continue on Subagent Failure"
                        enabled={Boolean(settings.continue_on_subagent_failure ?? true)}
                        onToggle={() => patchSetting({ continue_on_subagent_failure: !(settings.continue_on_subagent_failure ?? true) })}
                    />
                    <ToggleChip
                        label="Deep Research Before Build"
                        enabled={Boolean(settings.deep_research_before_build_enabled ?? true)}
                        onToggle={() => patchSetting({ deep_research_before_build_enabled: !(settings.deep_research_before_build_enabled ?? true) })}
                    />
                    <ToggleChip
                        label="Overnight Autonomy"
                        enabled={Boolean(settings.overnight_autonomy_enabled ?? true)}
                        onToggle={() => patchSetting({ overnight_autonomy_enabled: !(settings.overnight_autonomy_enabled ?? true) })}
                    />
                    <ToggleChip
                        label="Auto Improve on Fail"
                        enabled={Boolean(settings.auto_self_improve_on_failure_enabled ?? true)}
                        onToggle={() =>
                            patchSetting({
                                auto_self_improve_on_failure_enabled: !(settings.auto_self_improve_on_failure_enabled ?? true),
                            })
                        }
                    />
                    <ToggleChip
                        label="Include Stopped Runs"
                        enabled={Boolean(settings.auto_self_improve_on_failure_include_stopped ?? false)}
                        onToggle={() =>
                            patchSetting({
                                auto_self_improve_on_failure_include_stopped: !(settings.auto_self_improve_on_failure_include_stopped ?? false),
                            })
                        }
                    />
                </div>
                <div className="mt-4 grid md:grid-cols-2 gap-4">
                    <InputField
                        label="Ollama URL"
                        value={String(settings.ollama_url ?? 'http://localhost:11434')}
                        onChange={(value) => patchSetting({ ollama_url: value.trim() || 'http://localhost:11434' })}
                        placeholder="http://localhost:11434"
                    />
                    <InputField
                        label="Anthropic API Key"
                        value={String(settings.anthropic_api_key ?? '')}
                        onChange={(value) => patchSetting({ anthropic_api_key: value.trim() })}
                        placeholder="Optional local key"
                        type="password"
                    />
                    <InputField
                        label="GitHub Token"
                        value={String(settings.github_token ?? '')}
                        onChange={(value) => {
                            const next = value.trim();
                            setStoredGitHubToken(next);
                            patchSetting({ github_token: next });
                        }}
                        placeholder="Used by the GitHub panel"
                        type="password"
                    />
                    <InputField
                        label="Self Learning Focus"
                        value={String(settings.self_learning_focus ?? 'general')}
                        onChange={(value) => patchSetting({ self_learning_focus: value || 'general' })}
                        placeholder="general"
                    />
                    <InputField
                        label="Deep Research Min Queries"
                        value={String(settings.deep_research_min_queries ?? 3)}
                        onChange={(value) => patchSetting({ deep_research_min_queries: Math.max(1, Number(value) || 1) })}
                        placeholder="3"
                    />
                    <InputField
                        label="Overnight Max Hours"
                        value={String(settings.overnight_max_hours ?? 10)}
                        onChange={(value) => patchSetting({ overnight_max_hours: Math.max(1, Number(value) || 1) })}
                        placeholder="10"
                    />
                    <InputField
                        label="Overnight Max Actions"
                        value={String(settings.overnight_max_actions ?? 320)}
                        onChange={(value) => patchSetting({ overnight_max_actions: Math.max(40, Number(value) || 40) })}
                        placeholder="320"
                    />
                    <InputField
                        label="Failure Improve Cooldown (s)"
                        value={String(settings.auto_self_improve_on_failure_cooldown_seconds ?? 180)}
                        onChange={(value) =>
                            patchSetting({
                                auto_self_improve_on_failure_cooldown_seconds: Math.max(0, Number(value) || 0),
                            })
                        }
                        placeholder="180"
                    />
                    <InputField
                        label="Failure Improve Max/Day"
                        value={String(settings.auto_self_improve_on_failure_max_per_day ?? 12)}
                        onChange={(value) =>
                            patchSetting({
                                auto_self_improve_on_failure_max_per_day: Math.max(0, Number(value) || 0),
                            })
                        }
                        placeholder="12"
                    />
                </div>
                <div className="mt-4 rounded-btn border border-surface-4 bg-surface-0 p-4">
                    <p className="text-[11px] uppercase tracking-wide text-text-secondary">Agent Model Map (JSON)</p>
                    <p className="text-[11px] text-text-muted mt-1">
                        Keys supported: `planner`, `verifier`, `coder`, `role:planner`, `id:agent-name`.
                    </p>
                    <textarea
                        rows={5}
                        value={agentModelsText}
                        onChange={(e) => {
                            setAgentModelsText(e.target.value);
                            if (jsonError) setJsonError(null);
                        }}
                        onBlur={(e) => {
                            try {
                                JSON.parse(e.target.value || '{}');
                                setJsonError(null);
                            } catch {
                                setJsonError('Invalid JSON format.');
                            }
                        }}
                        className={`mt-2 w-full bg-surface-1 border rounded-btn px-3 py-2 text-xs text-text-primary ${jsonError ? 'border-accent-red/60' : 'border-surface-4'}`}
                    />
                    {jsonError && (
                        <p className="mt-1 text-xs text-accent-red">{jsonError}</p>
                    )}
                    <button
                        type="button"
                        onClick={saveAgentModelMap}
                        disabled={saving || jsonError !== null}
                        className={`mt-3 px-3 py-2 rounded-btn border border-accent/40 text-accent text-xs ${(saving || jsonError !== null) ? 'opacity-60 cursor-not-allowed' : ''}`}
                    >
                        {saving ? 'Saving...' : 'Save Agent Model Map'}
                    </button>
                </div>
            </section>

            <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6 space-y-4">
                <h2 className="text-sm font-semibold text-text-primary">Phone Notifications</h2>
                <p className="text-xs text-text-secondary">
                    Send a notification to this device when long jimAI tasks finish.
                </p>
                <div className="grid md:grid-cols-2 gap-3">
                    <InputField
                        label="Long Task Threshold (seconds)"
                        value={String(settings.phone_notification_min_seconds ?? 120)}
                        onChange={(value) => patchSetting({ phone_notification_min_seconds: Math.max(0, Number(value) || 0) })}
                    />
                    <label className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2">
                        <p className="text-[11px] uppercase tracking-wide text-text-secondary">Device Permission</p>
                        <p className="mt-1 text-sm text-text-primary">{notificationPermission}</p>
                        <button
                            onClick={requestNotificationPermission}
                            type="button"
                            className="mt-2 px-3 py-2 rounded-btn border border-accent/40 text-accent text-xs"
                        >
                            Grant Notification Permission
                        </button>
                    </label>
                </div>
                <div className="grid md:grid-cols-2 gap-2">
                    <ToggleChip
                        label="Phone Notifications"
                        enabled={Boolean(settings.phone_notifications_enabled)}
                        onToggle={() => patchSetting({ phone_notifications_enabled: !settings.phone_notifications_enabled })}
                    />
                    <ToggleChip
                        label="Notify on Failure/Stop"
                        enabled={Boolean(settings.phone_notifications_on_failure ?? true)}
                        onToggle={() => patchSetting({ phone_notifications_on_failure: !(settings.phone_notifications_on_failure ?? true) })}
                    />
                </div>
            </section>

            <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6 space-y-4">
                <h2 className="text-sm font-semibold text-text-primary">Free Stack Integration</h2>
                <p className="text-xs text-text-secondary">
                    Connect jimAI to your local Postgres/Redis/Qdrant/MinIO/observability services and Gotify push notifications.
                </p>
                <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={refreshFreeStackStatus} className="px-3 py-2 rounded-btn border border-accent/40 text-accent text-xs">
                        Refresh Status
                    </button>
                    <button type="button" onClick={syncFreeStack} className="px-3 py-2 rounded-btn border border-accent-green/40 text-accent-green text-xs">
                        Sync From Secure Env
                    </button>
                    <button type="button" onClick={sendTestPhoneNotification} className="px-3 py-2 rounded-btn border border-accent-amber/40 text-accent-amber text-xs">
                        Send Test Notification
                    </button>
                </div>
                <div className="grid md:grid-cols-2 gap-3">
                    <ToggleChip
                        label="Free Stack Enabled"
                        enabled={Boolean(settings.free_stack_enabled ?? true)}
                        onToggle={() => patchSetting({ free_stack_enabled: !(settings.free_stack_enabled ?? true) })}
                    />
                    <ToggleChip
                        label="Gotify Push Enabled"
                        enabled={Boolean(settings.free_stack_gotify_enabled ?? false)}
                        onToggle={() => patchSetting({ free_stack_gotify_enabled: !(settings.free_stack_gotify_enabled ?? false) })}
                    />
                    <InputField
                        label="Secure Env Path"
                        value={String(settings.free_stack_env_path ?? freeStackStatus?.env_path ?? '')}
                        onChange={(value) => patchSetting({ free_stack_env_path: value.trim() })}
                        placeholder="data/agent_space/secure/free-stack.env"
                    />
                    <InputField
                        label="Gotify URL"
                        value={String(settings.free_stack_gotify_url ?? freeStackStatus?.gotify.url ?? '')}
                        onChange={(value) => patchSetting({ free_stack_gotify_url: value.trim() })}
                        placeholder="http://localhost:18080"
                    />
                    <InputField
                        label="Gotify App Token"
                        value={String(settings.free_stack_gotify_token ?? '')}
                        onChange={(value) => patchSetting({ free_stack_gotify_token: value.trim() })}
                        placeholder="paste token from Gotify app/application"
                    />
                </div>
                {freeStackStatus && (
                    <div className="space-y-2 max-h-[220px] overflow-auto">
                        {freeStackStatus.services.map((svc) => (
                            <div key={svc.key} className="rounded-btn border border-surface-4 bg-surface-0 p-3 text-xs">
                                <p className="text-text-primary">{svc.name}</p>
                                <p className="text-text-secondary mt-1">{svc.url}</p>
                                <p className="text-text-muted mt-1">
                                    {svc.reachable ? `online (${String(svc.http_status || 0)})` : `offline${svc.error ? ` • ${svc.error}` : ''}`}
                                </p>
                            </div>
                        ))}
                    </div>
                )}
            </section>

            <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6 space-y-4">
                <h2 className="text-sm font-semibold text-text-primary">Proactive & Self-Improvement</h2>
                <p className="text-xs text-text-secondary">
                    proactive: {String(Boolean(proactiveStatus.running))} • goals: {String(proactiveStatus.goal_count ?? 0)}
                </p>
                <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => setProactiveRunning(true)} className="px-3 py-2 rounded-btn border border-accent-green/40 text-accent-green text-xs">
                        Start Proactive
                    </button>
                    <button type="button" onClick={() => setProactiveRunning(false)} className="px-3 py-2 rounded-btn border border-accent-red/40 text-accent-red text-xs">
                        Stop Proactive
                    </button>
                    <button type="button" onClick={tickProactive} className="px-3 py-2 rounded-btn border border-accent/40 text-accent text-xs">
                        Tick Once
                    </button>
                    <button type="button" onClick={runSelfImproveNow} className="px-3 py-2 rounded-btn border border-accent-amber/40 text-accent-amber text-xs">
                        Run Self-Improve Now
                    </button>
                </div>
                <div className="grid md:grid-cols-3 gap-2">
                    <input value={newGoalName} onChange={(e) => setNewGoalName(e.target.value)} className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-xs text-text-primary" placeholder="Goal name" />
                    <input value={newGoalInterval} onChange={(e) => setNewGoalInterval(e.target.value)} className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-xs text-text-primary" placeholder="Interval seconds" />
                    <button type="button" onClick={addGoal} className="px-3 py-2 rounded-btn border border-accent-green/40 text-accent-green text-xs">Add Goal</button>
                </div>
                <textarea value={newGoalObjective} onChange={(e) => setNewGoalObjective(e.target.value)} rows={2} className="w-full bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-xs text-text-primary" />
                <div className="space-y-2 max-h-[180px] overflow-auto">
                    {proactiveGoals.map((goal) => (
                        <div key={goal.id} className="rounded-btn border border-surface-4 bg-surface-0 p-3 text-xs">
                            <p className="text-text-primary">{goal.name}</p>
                            <p className="text-text-secondary mt-1">{goal.objective}</p>
                            <p className="text-text-muted mt-1">every {goal.interval_seconds}s • enabled {String(goal.enabled)}</p>
                        </div>
                    ))}
                </div>
            </section>

            <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6 space-y-4">
                <h2 className="text-sm font-semibold text-text-primary">Local Code Index</h2>
                <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={rebuildIndex} className="px-3 py-2 rounded-btn border border-accent/40 text-accent">
                        Rebuild Index
                    </button>
                    <input
                        value={indexQuery}
                        onChange={(e) => setIndexQuery(e.target.value)}
                        placeholder="search query"
                        className="flex-1 min-w-[220px] bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-sm text-text-primary"
                    />
                    <button type="button" onClick={searchIndex} className="px-3 py-2 rounded-btn border border-accent-green/40 text-accent-green">
                        Search
                    </button>
                </div>
                <div className="space-y-2 max-h-[220px] overflow-auto">
                    {indexResults.map((row, idx) => (
                        <div key={idx} className="rounded-btn border border-surface-4 bg-surface-0 p-3">
                            <p className="text-sm text-text-primary">{String(row.path || '')}</p>
                            <p className="text-xs text-text-secondary mt-1">{String(row.excerpt || '').slice(0, 150)}</p>
                        </div>
                    ))}
                </div>
            </section>

            <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6">
                <h2 className="text-sm font-semibold text-text-primary">Action Logs</h2>
                <div className="mt-3 max-h-[300px] overflow-auto space-y-2">
                    {logs.map((row, idx) => (
                        <div key={idx} className="rounded-btn border border-surface-4 bg-surface-0 p-3 text-xs">
                            <p className="text-text-primary">
                                run {String(row.run_id || '').slice(0, 8)} • {String(row.agent_id || '')}
                            </p>
                            <p className="text-text-secondary mt-1">
                                {String((row.action?.type as string | undefined) || 'unknown action')}
                            </p>
                            <p className="text-text-muted mt-1">
                                {row.result && row.result.success === false ? 'failure' : 'success'}
                            </p>
                        </div>
                    ))}
                </div>
            </section>

            {message && <p className="text-sm text-accent-green">{message}</p>}
            {error && <p className="text-sm text-accent-red">{error}</p>}
            </div>
        </div>
    );
}

function InputField({
    label,
    value,
    onChange,
    placeholder = '',
    type = 'text',
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    type?: string;
}) {
    const [draft, setDraft] = useState(value);

    useEffect(() => {
        setDraft(value);
    }, [value]);

    const commit = () => {
        if (draft !== value) onChange(draft);
    };

    return (
        <label className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2">
            <p className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</p>
            <input
                type={type}
                value={draft}
                placeholder={placeholder}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        commit();
                        e.currentTarget.blur();
                    }
                }}
                className="mt-1 w-full bg-transparent text-sm text-text-primary outline-none"
            />
        </label>
    );
}

function SelectField({
    label,
    value,
    options,
    onChange,
}: {
    label: string;
    value: string;
    options: string[];
    onChange: (value: string) => void;
}) {
    return (
        <label className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2">
            <p className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</p>
            <select value={value} onChange={(e) => onChange(e.target.value)} className="mt-1 w-full bg-transparent text-sm text-text-primary outline-none">
                {options.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
        </label>
    );
}

function ToggleChip({
    label,
    enabled,
    onToggle,
}: {
    label: string;
    enabled: boolean;
    onToggle: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onToggle}
            className={`rounded-btn border px-3 py-2 text-left ${enabled ? 'border-accent-green/50 bg-accent-green/10' : 'border-surface-4 bg-surface-0'}`}
        >
            <p className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</p>
            <p className="text-sm text-text-primary mt-1">{enabled ? 'ON' : 'OFF'}</p>
        </button>
    );
}
