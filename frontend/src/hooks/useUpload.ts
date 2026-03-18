import { useCallback, useState } from 'react';
import * as api from '../lib/api';

export function useUpload(sessionId: string) {
    const [isUploading, setIsUploading] = useState(false);
    const [lastUpload, setLastUpload] = useState<{
        source: string;
        chunks: number;
    } | null>(null);

    const uploadFile = useCallback(
        async (file: File) => {
            setIsUploading(true);
            try {
                const result = await api.uploadFile(file, sessionId);
                setLastUpload({
                    source: result.source,
                    chunks: result.chunks_indexed,
                });
                return result;
            } finally {
                setIsUploading(false);
            }
        },
        [sessionId],
    );

    const uploadUrl = useCallback(
        async (url: string) => {
            setIsUploading(true);
            try {
                const result = await api.uploadUrl(url, sessionId);
                setLastUpload({
                    source: result.source,
                    chunks: result.chunks_indexed,
                });
                return result;
            } finally {
                setIsUploading(false);
            }
        },
        [sessionId],
    );

    return { isUploading, lastUpload, uploadFile, uploadUrl };
}
