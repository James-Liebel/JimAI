import { vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Builder from '../pages/Builder';
import * as agentApi from '../lib/agentSpaceApi';

function renderBuilder() {
    return render(
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Builder />
        </MemoryRouter>,
    );
}

describe('Builder page', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
        vi.spyOn(agentApi, 'getSettings').mockResolvedValue({
            review_gate: true,
            allow_shell: false,
            command_profile: 'safe',
            continue_on_subagent_failure: true,
        });
        vi.spyOn(agentApi, 'listRuns').mockResolvedValue([]);
        vi.spyOn(agentApi, 'listRepoTree').mockResolvedValue({
            root: '.',
            depth: 8,
            limit: 10000,
            scanned: 1,
            truncated: false,
            tree: { name: '.', path: '.', type: 'directory', children: [] },
        });
        vi.spyOn(agentApi, 'builderPreview').mockResolvedValue({
            model: 'qwen3:8b',
            team_name: 'Auto Build Team',
            base_agent_count: 1,
            team_agent_count: 1,
            used_saved_teams: [],
            used_agent_packs: [],
            team_agents: [],
            option_help: {},
        });
        vi.spyOn(agentApi, 'builderLaunch').mockResolvedValue({
            run: {
                id: 'run-123',
                status: 'running',
                objective: 'Build a test app',
                created_at: 0,
                updated_at: 0,
                review_ids: [],
                snapshot_ids: [],
                action_count: 0,
            },
            team_name: 'Auto Build Team',
            team_agent_count: 1,
            objective: 'Build a test app',
            open_source_refs: [],
        });
        vi.spyOn(agentApi, 'selectSkills').mockResolvedValue({ selected_count: 0, selected: [], context: '' });
        vi.spyOn(agentApi, 'stopRun').mockResolvedValue({});
        vi.spyOn(agentApi, 'subscribeRunEvents').mockReturnValue(() => {});
        vi.spyOn(agentApi, 'toolsRead').mockResolvedValue({ path: '', content: '' });
        vi.spyOn(agentApi, 'toolsShell').mockResolvedValue({ exit_code: 0, stdout: '', stderr: '', success: true });
        vi.spyOn(agentApi, 'postRunMessage').mockResolvedValue({
            id: 'msg-1',
            timestamp: 0,
            from: 'user',
            to: 'planner',
            channel: 'change-request',
            content: 'test',
        });
        vi.spyOn(agentApi, 'exportBundle').mockResolvedValue({ count: 0, target_folder: 'export' });
        vi.spyOn(agentApi, 'getResearchStatus').mockResolvedValue({});
    });

    it('renders objective input', async () => {
        renderBuilder();
        await waitFor(() => {
            expect(screen.getByPlaceholderText(/describe the app to build/i)).not.toBeNull();
        });
    });

    it('launch button is disabled while form is submitting', async () => {
        let resolveLaunch!: (value: agentApi.BuilderLaunchResponse) => void;
        vi.spyOn(agentApi, 'builderLaunch').mockReturnValue(
            new Promise((resolve) => {
                resolveLaunch = resolve;
            }) as ReturnType<typeof agentApi.builderLaunch>,
        );

        renderBuilder();
        await waitFor(() => screen.getByPlaceholderText(/describe the app to build/i));

        const user = userEvent.setup();
        await user.type(screen.getByPlaceholderText(/describe the app to build/i), 'Build a todo app');

        const launchBtn = screen.getByRole('button', { name: /start autonomous build/i });
        await user.click(launchBtn);

        // During the pending launch the button should be disabled
        await waitFor(() => {
            const btn = screen.getByRole('button', { name: /launching/i });
            expect((btn as HTMLButtonElement).disabled).toBe(true);
        });

        // Resolve to clean up
        await act(async () => {
            resolveLaunch({
                run: {
                    id: 'run-123',
                    status: 'running',
                    objective: 'Build a todo app',
                    created_at: 0,
                    updated_at: 0,
                    review_ids: [],
                    snapshot_ids: [],
                    action_count: 0,
                },
                team_name: 'Auto Build Team',
                team_agent_count: 1,
                objective: 'Build a todo app',
                open_source_refs: [],
            });
            await Promise.resolve();
        });
    });

    it('launch button shows "Launching..." while pending', async () => {
        let resolveLaunch!: (value: agentApi.BuilderLaunchResponse) => void;
        vi.spyOn(agentApi, 'builderLaunch').mockReturnValue(
            new Promise((resolve) => {
                resolveLaunch = resolve;
            }) as ReturnType<typeof agentApi.builderLaunch>,
        );

        renderBuilder();
        await waitFor(() => screen.getByPlaceholderText(/describe the app to build/i));

        const user = userEvent.setup();
        await user.type(screen.getByPlaceholderText(/describe the app to build/i), 'Build a weather app');
        await user.click(screen.getByRole('button', { name: /start autonomous build/i }));

        await waitFor(() => {
            expect(screen.getByText('Launching...')).not.toBeNull();
        });

        await act(async () => {
            resolveLaunch({
                run: {
                    id: 'run-456',
                    status: 'running',
                    objective: 'Build a weather app',
                    created_at: 0,
                    updated_at: 0,
                    review_ids: [],
                    snapshot_ids: [],
                    action_count: 0,
                },
                team_name: 'Auto Build Team',
                team_agent_count: 1,
                objective: 'Build a weather app',
                open_source_refs: [],
            });
            await Promise.resolve();
        });
    });

    it('shows error state on failed launch', async () => {
        vi.spyOn(agentApi, 'builderLaunch').mockRejectedValue(new Error('Network error'));

        renderBuilder();
        await waitFor(() => screen.getByPlaceholderText(/describe the app to build/i));

        const user = userEvent.setup();
        await user.type(screen.getByPlaceholderText(/describe the app to build/i), 'Build a broken app');
        await user.click(screen.getByRole('button', { name: /start autonomous build/i }));

        await waitFor(() => {
            expect(screen.getByText('Network error')).not.toBeNull();
        });
    });
});
