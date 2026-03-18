import { vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ErrorBoundary from '../components/ErrorBoundary';

// Component that throws on demand
const EXPECTED_ERROR_MESSAGE = 'Test render error';

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
    if (shouldThrow) {
        throw new Error(EXPECTED_ERROR_MESSAGE);
    }
    return <div>Normal child content</div>;
}

describe('ErrorBoundary', () => {
    let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
    let windowErrorHandler: ((event: ErrorEvent) => void) | null = null;

    beforeEach(() => {
        const originalConsoleError = console.error;
        consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation((...args) => {
            const joined = args.map((value) => String(value ?? '')).join(' ');
            if (joined.includes('[ErrorBoundary] Caught render error:') || joined.includes(EXPECTED_ERROR_MESSAGE)) {
                return;
            }
            originalConsoleError(...args);
        });
        windowErrorHandler = (event: ErrorEvent) => {
            if (event.error instanceof Error && event.error.message === EXPECTED_ERROR_MESSAGE) {
                event.preventDefault();
            }
        };
        window.addEventListener('error', windowErrorHandler);
    });

    afterEach(() => {
        if (windowErrorHandler) {
            window.removeEventListener('error', windowErrorHandler);
            windowErrorHandler = null;
        }
        consoleErrorSpy.mockRestore();
    });

    it('renders children normally when no error', () => {
        render(
            <ErrorBoundary>
                <ThrowingChild shouldThrow={false} />
            </ErrorBoundary>,
        );
        expect(screen.getByText('Normal child content')).not.toBeNull();
    });

    it('renders error screen when child throws', () => {
        render(
            <ErrorBoundary>
                <ThrowingChild shouldThrow={true} />
            </ErrorBoundary>,
        );
        expect(screen.queryByText('Normal child content')).toBeNull();
        expect(screen.getByRole('button', { name: /reload app/i })).not.toBeNull();
    });

    it('error screen contains "Something went wrong" text', () => {
        render(
            <ErrorBoundary>
                <ThrowingChild shouldThrow={true} />
            </ErrorBoundary>,
        );
        expect(screen.getByText('Something went wrong')).not.toBeNull();
    });

    it('"Reload App" button calls window.location.reload', async () => {
        const reloadMock = vi.fn();
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: { ...window.location, reload: reloadMock },
        });

        render(
            <ErrorBoundary>
                <ThrowingChild shouldThrow={true} />
            </ErrorBoundary>,
        );

        const user = userEvent.setup();
        const reloadBtn = screen.getByRole('button', { name: /reload app/i });
        await user.click(reloadBtn);

        expect(reloadMock).toHaveBeenCalledOnce();
    });
});
