import { useCallback, useRef, useState } from 'react';

interface UseStreamOptions {
    onChunk?: (text: string) => void;
    onDone?: () => void;
    onError?: (error: Error) => void;
}

export function useStream(opts: UseStreamOptions) {
    const [isStreaming, setIsStreaming] = useState(false);
    const [error, setError] = useState<Error | null>(null);
    const abortRef = useRef<AbortController | null>(null);

    const start = useCallback(
        async (url: string, body: Record<string, unknown>) => {
            setIsStreaming(true);
            setError(null);
            abortRef.current = new AbortController();

            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                    signal: abortRef.current.signal,
                });

                if (!resp.ok) throw new Error(`Stream failed: ${resp.status}`);
                if (!resp.body) throw new Error('No response body');

                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.text) opts.onChunk?.(data.text);
                            if (data.done) opts.onDone?.();
                        } catch {
                            // skip
                        }
                    }
                }
            } catch (err) {
                if (err instanceof Error && err.name !== 'AbortError') {
                    setError(err);
                    opts.onError?.(err);
                }
            } finally {
                setIsStreaming(false);
                opts.onDone?.();
            }
        },
        [opts],
    );

    const cancel = useCallback(() => {
        abortRef.current?.abort();
        setIsStreaming(false);
    }, []);

    return { isStreaming, error, start, cancel };
}
