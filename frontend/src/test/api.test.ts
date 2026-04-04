import { vi } from 'vitest';
import { fetchWithTimeout, getSpeedMode, setSpeedMode, uploadFile, uploadUrl } from '../lib/api';

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

    it('adds CSRF header for POST requests', async () => {
        const mockResponse = new Response('{}', { status: 200 });
        let capturedHeaders: Record<string, string> = {};

        const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
            capturedHeaders = options?.headers as Record<string, string>;
            return Promise.resolve(mockResponse);
        });
        vi.stubGlobal('fetch', fetchMock);

        await fetchWithTimeout('/api/data', { method: 'POST' }, 5000);

        expect(capturedHeaders['X-JimAI-CSRF']).toBe('1');
    });

    it('does not add CSRF header for GET requests', async () => {
        const mockResponse = new Response('{}', { status: 200 });
        let capturedHeaders: Record<string, string> = {};

        const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
            capturedHeaders = (options?.headers as Record<string, string>) ?? {};
            return Promise.resolve(mockResponse);
        });
        vi.stubGlobal('fetch', fetchMock);

        await fetchWithTimeout('/api/data', { method: 'GET' }, 5000);

        expect(capturedHeaders['X-JimAI-CSRF']).toBeUndefined();
    });

    it('propagates non-abort errors', async () => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
        vi.stubGlobal('fetch', fetchMock);

        await expect(fetchWithTimeout('/api/fail', {}, 5000)).rejects.toThrow('Failed to fetch');
    });
});

describe('getSpeedMode', () => {
    beforeEach(() => vi.restoreAllMocks());

    it('calls /api/settings/speed-mode and returns parsed JSON', async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ mode: 'balanced' }), { status: 200 }),
        );
        vi.stubGlobal('fetch', fetchMock);

        const result = await getSpeedMode();
        expect(result.mode).toBe('balanced');
        expect(fetchMock).toHaveBeenCalledOnce();
        expect((fetchMock.mock.calls[0][0] as string)).toMatch(/speed-mode/);
    });
});

describe('setSpeedMode', () => {
    beforeEach(() => vi.restoreAllMocks());

    it('sends POST with JSON body and returns response', async () => {
        let capturedBody = '';
        const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
            capturedBody = options.body as string;
            return Promise.resolve(new Response(JSON.stringify({ mode: 'fast' }), { status: 200 }));
        });
        vi.stubGlobal('fetch', fetchMock);

        const result = await setSpeedMode('fast');
        expect(result.mode).toBe('fast');
        expect(JSON.parse(capturedBody)).toEqual({ mode: 'fast' });
    });
});

describe('uploadFile', () => {
    beforeEach(() => vi.restoreAllMocks());

    it('returns source and chunks_indexed on success', async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ source: 'doc.pdf', chunks_indexed: 12 }), { status: 200 }),
        );
        vi.stubGlobal('fetch', fetchMock);

        const file = new File(['hello'], 'doc.pdf', { type: 'application/pdf' });
        const result = await uploadFile(file, 'session-1');
        expect(result.source).toBe('doc.pdf');
        expect(result.chunks_indexed).toBe(12);
    });

    it('throws on non-ok response using error field', async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ error: 'file too large' }), { status: 413 }),
        );
        vi.stubGlobal('fetch', fetchMock);

        const file = new File(['x'.repeat(1000)], 'big.pdf');
        await expect(uploadFile(file)).rejects.toThrow('file too large');
    });

    it('throws on success=false response', async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ success: false, error: 'unsupported format' }), { status: 200 }),
        );
        vi.stubGlobal('fetch', fetchMock);

        const file = new File(['data'], 'file.xyz');
        await expect(uploadFile(file)).rejects.toThrow('unsupported format');
    });
});

describe('uploadUrl', () => {
    beforeEach(() => vi.restoreAllMocks());

    it('sends url and session_id in request body', async () => {
        let capturedBody = '';
        const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
            capturedBody = options.body as string;
            return Promise.resolve(
                new Response(JSON.stringify({ source: 'https://example.com', chunks_indexed: 5 }), { status: 200 }),
            );
        });
        vi.stubGlobal('fetch', fetchMock);

        const result = await uploadUrl('https://example.com', 'my-session');
        expect(result.chunks_indexed).toBe(5);
        expect(JSON.parse(capturedBody)).toEqual({ url: 'https://example.com', session_id: 'my-session' });
    });

    it('throws on non-ok response', async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response('', { status: 404 }),
        );
        vi.stubGlobal('fetch', fetchMock);

        await expect(uploadUrl('https://missing.example.com')).rejects.toThrow('URL upload failed: 404');
    });
});
