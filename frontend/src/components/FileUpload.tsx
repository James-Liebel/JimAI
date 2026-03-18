import { useState, useEffect } from 'react';
import { cn } from '../lib/utils';

interface Props {
    onUpload: (file: File) => Promise<void>;
}

export default function FileUpload({ onUpload }: Props) {
    const [isDragging, setIsDragging] = useState(false);
    const [uploadStatus, setUploadStatus] = useState<{
        name: string;
        state: 'uploading' | 'success' | 'error';
        chunks?: number;
        message?: string;
    } | null>(null);

    useEffect(() => {
        const onDragOver = (e: globalThis.DragEvent) => {
            e.preventDefault();
            setIsDragging(true);
        };
        const onDragLeave = (e: globalThis.DragEvent) => {
            e.preventDefault();
            // Only hide if leaving the window
            if (e.relatedTarget === null) {
                setIsDragging(false);
            }
        };
        const onDrop = async (e: globalThis.DragEvent) => {
            e.preventDefault();
            setIsDragging(false);
            const file = e.dataTransfer?.files[0];
            if (file) {
                setUploadStatus({ name: file.name, state: 'uploading' });
                try {
                    await onUpload(file);
                    setUploadStatus({ name: file.name, state: 'success' });
                    setTimeout(() => setUploadStatus(null), 3000);
                } catch (err) {
                    setUploadStatus({
                        name: file.name,
                        state: 'error',
                        message: err instanceof Error ? err.message : 'Upload failed',
                    });
                    setTimeout(() => setUploadStatus(null), 5000);
                }
            }
        };

        window.addEventListener('dragover', onDragOver);
        window.addEventListener('dragleave', onDragLeave);
        window.addEventListener('drop', onDrop);
        return () => {
            window.removeEventListener('dragover', onDragOver);
            window.removeEventListener('dragleave', onDragLeave);
            window.removeEventListener('drop', onDrop);
        };
    }, [onUpload]);

    return (
        <>
            {/* Drag overlay */}
            {isDragging && (
                <div className="fixed inset-0 z-50 drag-overlay flex items-center justify-center animate-fade-in">
                    <div className="bg-surface-2 rounded-2xl border-2 border-dashed border-accent p-12 text-center">
                        <div className="text-5xl mb-4">📄</div>
                        <p className="text-lg font-medium text-text-primary">
                            Drop file to upload
                        </p>
                        <p className="text-sm text-text-muted mt-1">
                            PDF, DOCX, code files, images
                        </p>
                    </div>
                </div>
            )}

            {/* Upload status toast */}
            {uploadStatus && (
                <div
                    className={cn(
                        'fixed bottom-20 right-4 z-50 animate-slide-up',
                        'bg-surface-2 border border-surface-3 rounded-lg px-4 py-3 shadow-xl',
                        'flex items-center gap-3',
                    )}
                >
                    {uploadStatus.state === 'uploading' && (
                        <>
                            <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                            <span className="text-sm text-text-secondary">
                                Uploading {uploadStatus.name}...
                            </span>
                        </>
                    )}
                    {uploadStatus.state === 'success' && (
                        <>
                            <span className="text-green-400">✓</span>
                            <span className="text-sm text-text-secondary">
                                {uploadStatus.name} indexed
                            </span>
                        </>
                    )}
                    {uploadStatus.state === 'error' && (
                        <>
                            <span className="text-red-400">✗</span>
                            <span className="text-sm text-text-secondary">
                                {uploadStatus.message || `Failed to upload ${uploadStatus.name}`}
                            </span>
                        </>
                    )}
                </div>
            )}
        </>
    );
}
