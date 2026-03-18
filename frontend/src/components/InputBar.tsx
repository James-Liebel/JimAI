import { useRef, useState, useCallback, useEffect, type KeyboardEvent, type ClipboardEvent } from 'react';
import { Mic, MicOff, Camera, Paperclip, Send } from 'lucide-react';
import { MODEL_OPTIONS } from '../lib/types';
import { cn, fileToBase64 } from '../lib/utils';
import { classifyLocally } from '../lib/classifier';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';

interface Props {
    onSend: (message: string, imageBase64?: string) => void;
    isStreaming: boolean;
    modelOverride: string;
    onModelOverrideChange: (override: string) => void;
    onSpeedModeChange?: (mode: 'fast' | 'balanced' | 'deep') => void;
    onFileAttach: (file: File) => void;
    isMobile?: boolean;
    speedMode?: 'fast' | 'balanced' | 'deep';
}

const ROLE_MODEL_MAP: Record<string, Record<string, string>> = {
    fast:     { math: 'qwen2-math:7b',    code: 'qwen2.5-coder:7b', chat: 'qwen3:8b', vision: 'qwen2.5vl:7b', data: 'qwen2.5-coder:7b' },
    balanced: { math: 'deepseek-r1:14b',   code: 'qwen2.5-coder:14b', chat: 'qwen3:8b', vision: 'qwen2.5vl:7b', data: 'qwen2.5-coder:14b' },
    deep:     { math: 'qwen2.5:32b',       code: 'qwen2.5:32b',       chat: 'qwen2.5:32b', vision: 'qwen2.5vl:7b', data: 'qwen2.5:32b' },
};

function resolveModelLabel(role: string, speedMode: string): string {
    const models = ROLE_MODEL_MAP[speedMode] || ROLE_MODEL_MAP.balanced;
    const model = models[role] || models.chat;
    const suffix = speedMode === 'fast' ? ' (fast)' : speedMode === 'deep' ? ' (deep)' : '';
    return `${model}${suffix}`;
}

export default function InputBar({
    onSend,
    isStreaming,
    modelOverride,
    onModelOverrideChange,
    onSpeedModeChange,
    onFileAttach,
    isMobile = false,
    speedMode = 'balanced',
}: Props) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const cameraInputRef = useRef<HTMLInputElement>(null);
    const [text, setText] = useState('');
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const [pastedImage, setPastedImage] = useState<string | null>(null);
    const [routingPreview, setRoutingPreview] = useState('');
    const debounceRef = useRef<ReturnType<typeof setTimeout>>();

    const handleSpeechResult = useCallback((transcript: string) => {
        setText(transcript);
    }, []);

    const { isListening, start: startListening, stop: stopListening } = useSpeechRecognition(handleSpeechResult);

    useEffect(() => {
        const el = textareaRef.current;
        if (el) {
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 180) + 'px';
        }
    }, [text]);

    useEffect(() => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            if (text.trim()) {
                const prediction = classifyLocally(text, !!pastedImage);
                setRoutingPreview(prediction);
            } else {
                setRoutingPreview('');
            }
        }, 200);
        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, [text, pastedImage]);

    const handleSend = useCallback(async () => {
        const trimmed = text.trim();
        if (!trimmed && !pastedImage) return;
        if (isStreaming) return;

        onSend(trimmed, pastedImage ?? undefined);
        setText('');
        setPastedImage(null);
        setAttachedFile(null);
        setRoutingPreview('');
        setTimeout(() => textareaRef.current?.focus(), 100);
    }, [text, pastedImage, isStreaming, onSend]);

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (isMobile) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
            }
        } else {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                handleSend();
            }
        }
    };

    const handlePaste = async (e: ClipboardEvent<HTMLTextAreaElement>) => {
        const items = e.clipboardData.items;
        for (const item of items) {
            if (item.type.startsWith('image/')) {
                e.preventDefault();
                const file = item.getAsFile();
                if (file) {
                    const b64 = await fileToBase64(file);
                    setPastedImage(b64);
                }
                return;
            }
        }
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setAttachedFile(file);
            onFileAttach(file);
        }
        e.target.value = '';
    };

    const handleCameraCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            const b64 = await fileToBase64(file);
            setPastedImage(b64);
        }
        e.target.value = '';
    };

    const overrideOption = MODEL_OPTIONS.find((o) => o.value === modelOverride);
    const borderClass = modelOverride && overrideOption?.color ? overrideOption.color : 'border-surface-3';
    const modelSelectValue = modelOverride || `__speed_${speedMode}`;

    return (
        <div className="space-y-2">
            {/* Attached file pill */}
            {attachedFile && (
                <div className="flex items-center gap-2 bg-surface-2 rounded px-3 py-1.5 text-xs text-text-secondary w-fit animate-fade-in">
                    <span className="text-text-muted">📎</span>
                    <span>{attachedFile.name}</span>
                    <button
                        onClick={() => setAttachedFile(null)}
                        className="text-text-muted hover:text-accent-red transition-colors ml-1"
                    >
                        ×
                    </button>
                </div>
            )}

            {/* Pasted image thumbnail */}
            {pastedImage && (
                <div className="flex items-center gap-2 bg-surface-2 rounded px-3 py-1.5 text-xs text-text-secondary w-fit animate-fade-in">
                    <img
                        src={`data:image/png;base64,${pastedImage}`}
                        alt="Pasted"
                        className="w-8 h-8 rounded object-cover"
                    />
                    <span>Image attached → vision model</span>
                    <button
                        onClick={() => setPastedImage(null)}
                        className="text-text-muted hover:text-accent-red transition-colors ml-1"
                    >
                        ×
                    </button>
                </div>
            )}

            {/* Main input area */}
            <div className={cn(
                'flex items-end gap-1.5 bg-surface-1 rounded-lg border-2 p-2 transition-colors',
                borderClass,
                'focus-within:border-accent',
                isMobile && 'min-h-[52px]',
            )}>
                <button
                    onClick={() => fileInputRef.current?.click()}
                    className={cn(
                        'rounded text-text-muted hover:text-text-secondary hover:bg-surface-2 transition-colors flex-shrink-0',
                        isMobile ? 'p-2.5' : 'p-2',
                    )}
                    title="Attach file"
                >
                    <Paperclip size={isMobile ? 20 : 16} />
                </button>
                <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    onChange={handleFileSelect}
                    accept=".pdf,.docx,.doc,.txt,.md,.py,.ts,.tsx,.js,.jsx,.json,.csv,.ipynb,.tex,.r,.sql,.xml,.html,.yaml,.yml,.toml,.rs,.go,.java,.c,.cpp,.h,.sh,.bat,.ps1,image/*,.png,.jpg,.jpeg,.jpe,.webp,.gif,.bmp,.heic,.tiff,.tif"
                />

                {isMobile && (
                    <>
                        <button
                            onClick={() => cameraInputRef.current?.click()}
                            className="p-2.5 rounded text-text-muted hover:text-text-secondary hover:bg-surface-2 transition-colors flex-shrink-0"
                            title="Take photo"
                        >
                            <Camera size={20} />
                        </button>
                        <input
                            ref={cameraInputRef}
                            type="file"
                            accept="image/*"
                            capture="environment"
                            className="hidden"
                            onChange={handleCameraCapture}
                        />
                    </>
                )}

                <textarea
                    ref={textareaRef}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    onPaste={handlePaste}
                    placeholder={isMobile ? 'Ask anything...' : 'Just type anything... Ctrl+Enter to send'}
                    rows={1}
                    className={cn(
                        'flex-1 bg-transparent text-text-primary resize-none outline-none placeholder:text-text-muted',
                        isMobile ? 'text-base min-h-[44px] py-2' : 'text-sm min-h-[36px] py-1.5',
                        'max-h-[180px]',
                    )}
                />

                {isMobile && (
                    <button
                        onClick={isListening ? stopListening : startListening}
                        className={cn(
                            'p-2.5 rounded transition-all flex-shrink-0',
                            isListening
                                ? 'text-accent-red bg-accent-red/10 animate-pulse-slow'
                                : 'text-text-muted hover:text-text-secondary hover:bg-surface-2',
                        )}
                        title={isListening ? 'Stop listening' : 'Voice input'}
                    >
                        {isListening ? <MicOff size={20} /> : <Mic size={20} />}
                    </button>
                )}

                <button
                    onClick={handleSend}
                    disabled={isStreaming || (!text.trim() && !pastedImage)}
                    className={cn(
                        'rounded transition-all flex-shrink-0',
                        isMobile ? 'p-2.5' : 'p-2',
                        isStreaming || (!text.trim() && !pastedImage)
                            ? 'text-text-muted cursor-not-allowed'
                            : 'text-accent hover:bg-accent/10',
                    )}
                    title={isMobile ? 'Send' : 'Send (Ctrl+Enter)'}
                >
                    <Send size={isMobile ? 20 : 18} />
                </button>
            </div>

            {/* Routing preview + override dropdown */}
            <div className="flex items-center justify-between px-1">
                <div className={cn(
                    'text-text-muted flex items-center gap-1.5',
                    isMobile ? 'text-xs' : 'text-[11px]',
                )}>
                    {routingPreview && !modelOverride && (
                        <span className="animate-fade-in">
                            → {routingPreview.includes('pipeline')
                                ? routingPreview
                                : resolveModelLabel(
                                    routingPreview.replace(' model', ''),
                                    speedMode,
                                )}
                        </span>
                    )}
                    {modelOverride && (
                        <span className="animate-fade-in flex items-center gap-1">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>
                            → {overrideOption?.label} (manual)
                        </span>
                    )}
                </div>
                <select
                    value={modelSelectValue}
                    onChange={(e) => {
                        const value = e.target.value;
                        if (value === '__speed_fast' || value === '__speed_balanced' || value === '__speed_deep') {
                            const next = value.replace('__speed_', '') as 'fast' | 'balanced' | 'deep';
                            onModelOverrideChange('');
                            onSpeedModeChange?.(next);
                            return;
                        }
                        onModelOverrideChange(value);
                    }}
                    className={cn(
                        'bg-surface-2 text-text-primary border border-surface-3 rounded outline-none cursor-pointer hover:border-surface-4 transition-colors',
                        isMobile ? 'text-xs px-3 py-1.5 min-h-[36px]' : 'text-[11px] px-2 py-0.5',
                    )}
                >
                    <option value="__speed_fast">Auto Routing (Fast)</option>
                    <option value="__speed_balanced">Auto Routing (Balanced)</option>
                    <option value="__speed_deep">Auto Routing (Deep)</option>
                    {MODEL_OPTIONS.filter((opt) => opt.value !== '').map((opt) => (
                        <option key={opt.value} value={opt.value}>
                            {opt.label} (manual)
                        </option>
                    ))}
                </select>
            </div>
        </div>
    );
}
