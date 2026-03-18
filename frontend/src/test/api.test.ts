import { vi } from 'vitest';
import { fetchWithTimeout } from '../lib/api';

describe('fetchWithTimeout', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('resolves normally when fetch succeeds within timeout', async () => {
        const mockResponse = new Response(JSON.stringify({ ok: true }), { status: 200 });
        const fetchMock = vi.fn().mockResolvedValue(mockResponse);
        vi.stubGlobal('fetch', fetchMock);

        const result = await fetchWithTimeout('/api/test', {}, 5000);
        expect(result.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledOnce();
    });

    it('rejects with timeout error when fetch takes too long', async () => {
        vi.useFakeTimers();

        // fetch that never resolves during the test
        const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
            return new Promise<Response>((_resolve, reject) => {
                // Listen for abort signal to reject appropriately
                const signal = options?.signal as AbortSignal | undefined;
                if (signal) {
                    signal.addEventListener('abort', () => {
                        reject(new DOMException('The operation was aborted.', 'AbortError'));
                    });
                }
            });
        });
        vi.stubGlobal('fetch', fetchMock);

        const promise = fetchWithTimeout('/api/slow', {}, 1000);

        // Advance past the timeout
        vi.advanceTimersByTime(1500);

        await expect(promise).rejects.toThrow('Request timed out after 1s');
    });

    it('abort signal is passed to fetch', async () => {
        const mockResponse = new Response('{}', { status: 200 });
        let capturedSignal: AbortSignal | undefined;

        const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
            capturedSignal = options?.signal as AbortSignal | undefined;
            return Promise.resolve(mockResponse);
        });
        vi.stubGlobal('fetch', fetchMock);

        await fetchWithTimeout('/api/check-signal', {}, 5000);

        expect(fetchMock).toHaveBeenCalledOnce();
        expect(capturedSignal).toBeInstanceOf(AbortSignal);
    });
});
