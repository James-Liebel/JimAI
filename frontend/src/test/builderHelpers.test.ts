import { describe, expect, it } from 'vitest';
import { deriveAgentActions, agentActionVerb } from '../components/builder/builderHelpers';
import type { AgentSpaceEvent } from '../lib/agentSpaceApi';

const started = (agent: string, action: Record<string, unknown>, ts = 1): AgentSpaceEvent => ({
    type: 'action.started',
    message: `${agent} executing ${action.type}`,
    data: { action },
    timestamp: ts,
});

const completed = (agent: string, action: Record<string, unknown>, result: Record<string, unknown>, ts = 2): AgentSpaceEvent => ({
    type: 'action.completed',
    message: `${agent} completed ${action.type}`,
    data: { action, result },
    timestamp: ts,
});

describe('deriveAgentActions', () => {
    it('marks an action running until its completion arrives', () => {
        const actions = deriveAgentActions([started('coder', { type: 'read_file', path: 'src/app.ts' })]);
        expect(actions[0].status).toBe('running');
    });

    it('resolves a completed action to done with its target path', () => {
        const action = { type: 'read_file', path: 'src/app.ts' };
        const actions = deriveAgentActions([started('coder', action), completed('coder', action, { success: true, content: 'abc' })]);
        expect(actions).toHaveLength(1);
        expect(actions[0]).toMatchObject({ status: 'done', type: 'read_file', target: 'src/app.ts' });
    });

    it('flags a failed shell action with its exit code detail', () => {
        const action = { type: 'run_shell', command: 'pytest' };
        const actions = deriveAgentActions([started('tester', action), completed('tester', action, { success: false, error: 'boom' })]);
        expect(actions[0].status).toBe('failed');
        expect(actions[0].detail).toBe('boom');
    });

    it('keeps repeated edits to the same file as distinct ordered cards', () => {
        const action = { type: 'write_file', path: 'a.ts' };
        const actions = deriveAgentActions([
            started('coder', action, 1),
            started('coder', action, 2),
            completed('coder', action, { success: true, mode: 'review' }, 3),
        ]);
        expect(actions).toHaveLength(2);
        expect(actions[0].status).toBe('done');
        expect(actions[1].status).toBe('running');
    });

    it('resolves a denied action to the denied status with its reason', () => {
        const action = { type: 'run_shell', command: 'rm -rf /' };
        const denied: AgentSpaceEvent = {
            type: 'action.denied',
            message: 'tester action run_shell denied: blocked',
            data: { action_type: 'run_shell', reason: 'blocked by policy' },
        };
        const actions = deriveAgentActions([started('tester', action), denied]);
        expect(actions[0].status).toBe('denied');
        expect(actions[0].detail).toBe('blocked by policy');
    });

    it('maps mutation action types to edit verbs', () => {
        expect(agentActionVerb('replace_in_file')).toBe('Edited');
        expect(agentActionVerb('run_shell')).toBe('Ran');
    });
});
