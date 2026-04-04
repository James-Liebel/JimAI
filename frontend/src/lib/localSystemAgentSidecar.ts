import { v4 as uuid } from 'uuid';
import { confirmSystemAgent, streamSystemAgent, type SystemAgentEvent } from './systemAgentApi';

/**
 * Runs the host system agent in autonomous mode and auto-approves confirmation prompts
 * so filesystem / shell steps can proceed without a separate System page.
 */
export async function runLocalSystemAgentAuto(task: string, onAppend: (text: string) => void): Promise<void> {
    const sessionId = `chat-fs-${uuid()}`;
    await streamSystemAgent(task, sessionId, 'autonomous', (event: SystemAgentEvent) => {
        if (event.type === 'confirmation_needed') {
            void confirmSystemAgent(sessionId, true).catch(() => {
                onAppend('\n[Could not auto-confirm step — try a narrower request.]\n');
            });
            return;
        }
        if (event.type === 'text' && event.data?.text) {
            onAppend(String(event.data.text));
        }
        if (event.type === 'plan' && Array.isArray(event.data?.steps)) {
            const n = event.data.steps.length;
            onAppend(`\n— Plan: ${n} step(s)\n`);
        }
        if (event.type === 'step_start') {
            const d = event.data;
            onAppend(`\n▸ ${d.tool}: ${d.description || ''}\n`);
        }
        if (event.type === 'step_result') {
            const ok = event.data?.success;
            const snippet = typeof event.data?.result === 'object' ? JSON.stringify(event.data.result).slice(0, 800) : String(event.data?.result ?? '');
            onAppend(ok ? `\n✓ ${snippet}${snippet.length >= 800 ? '…' : ''}\n` : `\n✗ ${event.data?.reason || 'skipped'}\n`);
        }
        if (event.type === 'step_error') {
            onAppend(`\nError (${event.data?.tool}): ${event.data?.error}\n`);
        }
        if (event.type === 'complete') {
            onAppend(event.data?.success ? '\n— Local agent finished.\n' : '\n— Local agent stopped.\n');
        }
    });
}
