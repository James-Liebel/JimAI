import { vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Settings from '../pages/Settings';
import * as agentApi from '../lib/agentSpaceApi';

function renderSettings() {
    return render(
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Settings />
        </MemoryRouter>,
    );
}

describe('Settings page', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
        vi.spyOn(agentApi, 'getSettings').mockResolvedValue({
            model: 'qwen2.5-coder:14b',
            agent_models: {},
            review_gate: true,
            allow_shell: false,
        });
        vi.spyOn(agentApi, 'getActionLogs').mockResolvedValue([]);
        vi.spyOn(agentApi, 'getProactiveStatus').mockResolvedValue({ running: false });
        vi.spyOn(agentApi, 'listProactiveGoals').mockResolvedValue([]);
        vi.spyOn(agentApi, 'getFreeStackStatus').mockResolvedValue({
            enabled: false,
            env_path: '',
            env_loaded: false,
            generated_at: 0,
            services: [],
            infra: { postgres: '', redis: '', minio_api: '' },
            gotify: { enabled: false, url: '', token_configured: false },
        });
        vi.spyOn(agentApi, 'updateSettings').mockResolvedValue({});
    });

    it('renders without crashing', async () => {
        renderSettings();
        await waitFor(() => {
            expect(screen.getByText('Settings')).not.toBeNull();
        });
    });

    it('shows JSON error when invalid JSON is typed in agentModels textarea', async () => {
        renderSettings();
        await waitFor(() => screen.getByText('Settings'));

        // The agent model map textarea has rows=5
        const textareas = screen.getAllByRole('textbox');
        const agentModelsTextarea = textareas.find(
            (el) => (el as HTMLTextAreaElement).rows === 5,
        ) as HTMLTextAreaElement;

        expect(agentModelsTextarea).toBeDefined();

        // Use fireEvent to avoid user-event special-character interpretation of '{'
        fireEvent.change(agentModelsTextarea, { target: { value: 'invalid json here' } });
        fireEvent.blur(agentModelsTextarea);

        await waitFor(() => {
            expect(screen.getByText('Invalid JSON format')).not.toBeNull();
        });
    });

    it('Save button is disabled when JSON is invalid', async () => {
        renderSettings();
        await waitFor(() => screen.getByText('Settings'));

        const textareas = screen.getAllByRole('textbox');
        const agentModelsTextarea = textareas.find(
            (el) => (el as HTMLTextAreaElement).rows === 5,
        ) as HTMLTextAreaElement;

        fireEvent.change(agentModelsTextarea, { target: { value: 'bad json here' } });
        fireEvent.blur(agentModelsTextarea);

        await waitFor(() => {
            screen.getByText('Invalid JSON format');
        });

        const saveButton = screen.getByRole('button', { name: /save agent model map/i });
        expect((saveButton as HTMLButtonElement).disabled).toBe(true);
    });

    it('clears JSON error when valid JSON is entered', async () => {
        renderSettings();
        await waitFor(() => screen.getByText('Settings'));

        const textareas = screen.getAllByRole('textbox');
        const agentModelsTextarea = textareas.find(
            (el) => (el as HTMLTextAreaElement).rows === 5,
        ) as HTMLTextAreaElement;

        // First trigger the error via blur
        fireEvent.change(agentModelsTextarea, { target: { value: 'bad json here' } });
        fireEvent.blur(agentModelsTextarea);

        await waitFor(() => {
            screen.getByText('Invalid JSON format');
        });

        // onChange handler calls setJsonError(null) when user types again
        fireEvent.change(agentModelsTextarea, { target: { value: '{}' } });

        await waitFor(() => {
            expect(screen.queryByText('Invalid JSON format')).toBeNull();
        });
    });
});
