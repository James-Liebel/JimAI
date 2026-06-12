import { useRef, useState, useCallback, useEffect, type KeyboardEvent, type ClipboardEvent } from 'react';
import { Mic, MicOff, Camera, Images, Paperclip, Send, Plus, Sparkles, Lock, ChevronDown } from 'lucide-react';
import { MODEL_OPTIONS } from '../lib/types';
import { cn, fileToBase64 } from '../lib/utils';
import { classifyLocally } from '../lib/classifier';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';

interface Props {
    onSend: (message: string, imageBase64?: string) => void;
    isStreaming: boolean;
    modelOverride: string;
    onModelOverrideChange: (override: string) => void;
    onSpeedModeChange?: (mode: 'turbo' | 'fast' | 'balanced' | 'deep') => void;
    onFileAttach: (file: File) => void;
    isMobile?: boolean;
    speedMode?: 'turbo' | 'fast' | 'balanced' | 'deep';
}

const ROLE_MODEL_MAP: Record<string, Record<string, string>> = {
    turbo:    { math: 'qwen2-math:7b',     code: 'qwen2.5-coder:3b',  chat: 'qwen2.5-coder:3b', vision: 'qwen2.5vl:7b', data: 'qwen2.5-coder:3b' },
    fast:     { math: 'qwen2-math:7b',     code: 'qwen2.5-coder:7b',  chat: 'qwen3:8b',          vision: 'qwen2.5vl:7b', data: 'qwen2.5-coder:7b' },
    balanced: { math: 'qwen3:14b',         code: 'qwen2.5-coder:14b', chat: 'qwen3:8b',          vision: 'qwen2.5vl:7b', data: 'qwen2.5-coder:14b' },
    deep:     { math: 'qwen2.5:32b-q3',   code: 'qwen2.5:32b-q3',    chat: 'qwen2.5:32b-q3',    vision: 'qwen2.5vl:7b', data: 'qwen2.5:32b-q3' },
};

function resolveModelLabel(role: string, speedMode: string): string {
    const models = ROLE_MODEL_MAP[speedMode] || ROLE_MODEL_MAP.balanced;
    const model = models[role] || models.chat;
    const suffix: Record<string, string> = { turbo: ' ⚡turbo', fast: ' (fast)', deep: ' (deep)' };
    return `${model}${suffix[speedMode] ?? ''}`;
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
    const galleryInputRef = useRef<HTMLInputElement>(null);
    const [text, setText] = useState('');
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const [pastedImage, setPastedImage] = useState<string | null>(null);
    const [routingPreview, setRoutingPreview] = useState('');
    const [showAttachMenu, setShowAttachMenu] = useState(false);
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
        // Phones have no Shift+Enter, so let Enter insert a newline and send via the
        // button. On desktop, Enter sends and Shift+Enter inserts a newline.
        if (isMobile) return;
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
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

    const handleGallerySelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            const b64 = await fileToBase64(file);
            setPastedImage(b64);
        }
        e.target.value = '';
    };

    const overrideOption = MODEL_OPTIONS.find((o) => o.value === modelOverride);
    const borderClass = modelOverride && overrideOption?.color ? overrideOption.color : 'border-surface-4';
    const validSpeedModes = new Set(['turbo', 'fast', 'balanced', 'deep']);
    const modelSelectValue = modelOverride || (validSpeedModes.has(speedMode) ? `__speed_${speedMode}` : '__speed_balanced');
    const SPEED_SHORT: Record<string, string> = { turbo: 'Turbo 3B', fast: 'Fast 7B', balanced: 'Balanced 14B', deep: 'Deep 32B' };
    const chipLabel = modelOverride
        ? overrideOption?.label ?? modelOverride
        : `Auto · ${SPEED_SHORT[speedMode] ?? 'Balanced 14B'}`;

    return (
        <div className="space-y-1.5">
            {/* Attached file pill */}
            {attachedFile && (
                <div className="flex w-fit items-center gap-2 rounded-card border border-surface-4 bg-surface-2 px-3 py-1.5 text-xs text-text-secondary animate-fade-in">
                    <span className="text-text-muted">📎</span>
                    <span>{attachedFile.name}</span>
                    <button
                        type="button"
                        onClick={() => setAttachedFile(null)}
                        className="ml-1 text-text-muted transition-colors hover:text-accent-red"
                    >
                        ×
                    </button>
                </div>
            )}

            {/* Pasted image thumbnail */}
            {pastedImage && (
                <div className="flex w-fit items-center gap-2 rounded-card border border-surface-4 bg-surface-2 px-3 py-1.5 text-xs text-text-secondary animate-fade-in">
                    <img
                        src={`data:image/png;base64,${pastedImage}`}
                        alt="Pasted"
                        className="h-8 w-8 rounded border border-surface-4 object-cover"
                    />
                    <span>Image attached → vision model</span>
                    <button
                        type="button"
                        onClick={() => setPastedImage(null)}
                        className="ml-1 text-text-muted transition-colors hover:text-accent-red"
                    >
                        ×
                    </button>
                </div>
            )}

            {/* Model selector + routing preview — sits directly above the chat bar */}
            <div className="flex items-center justify-between px-1">
                <div className={cn(
                    'text-text-muted flex items-center gap-1.5 flex-wrap',
                    isMobile ? 'text-xs' : 'text-[11px]',
                )}>
                    {routingPreview && !modelOverride && (
                        <>
                            {routingPreview === 'browser' && (
                                <span className="animate-fade-in flex items-center gap-1 text-cyan-400">
                                    → 🌐 browser
                                </span>
                            )}
                            {routingPreview === 'builder' && (
                                <span className="animate-fade-in flex items-center gap-1 text-accent-green">
                                    → 🔨 builder
                                </span>
                            )}
                            {!['browser', 'builder', 'chat model', 'code model', 'math model', 'vision model', 'math + code pipeline'].includes(routingPreview)
                             && !routingPreview.endsWith('model') && !routingPreview.includes('pipeline') && (
                                <span className="animate-fade-in text-cyan-400">
                                    → ⚙ {routingPreview}
                                </span>
                            )}
                            {(routingPreview.endsWith('model') || routingPreview.includes('pipeline')) && (
                                <span className="animate-fade-in">
                                    → {routingPreview.includes('pipeline')
                                        ? routingPreview
                                        : resolveModelLabel(routingPreview.replace(' model', ''), speedMode)}
                                </span>
                            )}
                        </>
                    )}
                    {modelOverride && (
                        <span className="animate-fade-in flex items-center gap-1">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>
                            → {overrideOption?.label} (manual)
                        </span>
                    )}
                </div>
                {/* Model chip: styled pill, with an invisible native select on top so
                    phones still get the OS picker and keyboards still tab to it. */}
                <div className={cn(
                    'relative flex shrink-0 items-center gap-1.5 rounded-full border bg-surface-2/90 transition-colors',
                    modelOverride
                        ? `${borderClass} text-text-primary`
                        : 'border-accent/25 bg-accent/[0.07] text-text-secondary',
                    isMobile ? 'px-3 py-1.5' : 'px-2.5 py-1',
                )}>
                    {modelOverride ? (
                        <Lock size={isMobile ? 12 : 10} className="shrink-0 opacity-70" />
                    ) : (
                        <Sparkles size={isMobile ? 12 : 10} className="shrink-0 text-accent" />
                    )}
                    <span className={cn('whitespace-nowrap font-medium', isMobile ? 'text-xs' : 'text-[11px]')}>
                        {chipLabel}
                    </span>
                    <ChevronDown size={isMobile ? 12 : 10} className="shrink-0 opacity-60" />
                    <select
                        aria-label="Model routing"
                        value={modelSelectValue}
                        onChange={(e) => {
                            const value = e.target.value;
                            if (['__speed_turbo', '__speed_fast', '__speed_balanced', '__speed_deep'].includes(value)) {
                                const next = value.replace('__speed_', '') as 'turbo' | 'fast' | 'balanced' | 'deep';
                                onModelOverrideChange('');
                                onSpeedModeChange?.(next);
                                return;
                            }
                            onModelOverrideChange(value);
                        }}
                        className="absolute -inset-y-2 -inset-x-1 w-[calc(100%+0.5rem)] cursor-pointer appearance-none opacity-0"
                    >
                        <option value="__speed_turbo">⚡ Auto Routing (Turbo 3B)</option>
                        <option value="__speed_fast">Auto Routing (Fast 7B)</option>
                        <option value="__speed_balanced">Auto Routing (Balanced 14B)</option>
                        <option value="__speed_deep">Auto Routing (Deep 32B)</option>
                        {MODEL_OPTIONS.filter((opt) => opt.value !== '').map((opt) => (
                            <option key={opt.value} value={opt.value}>
                                {opt.label} (manual)
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Main input area */}
            <div className={cn(
                'flex min-w-0 items-end gap-1.5 rounded-panel border bg-surface-1 p-2 shadow-elevation-1 transition-colors',
                borderClass,
                'focus-within:border-white/45 focus-within:shadow-focus-ring',
                isMobile && 'min-h-[52px]',
            )}>
                {!isMobile && (
                    <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="shrink-0 rounded p-2 text-text-muted transition-colors hover:bg-surface-2 hover:text-text-secondary"
                        title="Attach file"
                    >
                        <Paperclip size={16} />
                    </button>
                )}
                <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    onChange={handleFileSelect}
                    accept=".pdf,.docx,.doc,.txt,.md,.py,.ts,.tsx,.js,.jsx,.json,.csv,.ipynb,.tex,.r,.sql,.xml,.html,.yaml,.yml,.toml,.rs,.go,.java,.c,.cpp,.h,.sh,.bat,.ps1,image/*,.png,.jpg,.jpeg,.jpe,.webp,.gif,.bmp,.heic,.tiff,.tif"
                />

                {isMobile && (
                    <div className="relative shrink-0">
                        <button
                            type="button"
                            onClick={() => setShowAttachMenu((v) => !v)}
                            className="rounded p-2.5 text-text-muted transition-colors hover:bg-surface-2 hover:text-text-secondary"
                            title="Add attachment"
                        >
                            <Plus size={22} />
                        </button>
                        {showAttachMenu && (
                            <>
                                {/* dismiss backdrop */}
                                <div
                                    className="fixed inset-0 z-[55]"
                                    onClick={() => setShowAttachMenu(false)}
                                />
                                <div className="absolute bottom-full left-0 z-[56] mb-1 flex flex-col overflow-hidden rounded-lg border border-surface-5 bg-surface-1 shadow-xl">
                                    <button
                                        type="button"
                                        className="flex items-center gap-2.5 px-4 py-3 text-sm text-text-primary hover:bg-surface-2 active:bg-surface-3"
                                        onClick={() => { setShowAttachMenu(false); cameraInputRef.current?.click(); }}
                                    >
                                        <Camera size={16} className="shrink-0 text-text-muted" />
                                        Take Photo
                                    </button>
                                    <button
                                        type="button"
                                        className="flex items-center gap-2.5 px-4 py-3 text-sm text-text-primary hover:bg-surface-2 active:bg-surface-3 border-t border-surface-5"
                                        onClick={() => { setShowAttachMenu(false); galleryInputRef.current?.click(); }}
                                    >
                                        <Images size={16} className="shrink-0 text-text-muted" />
                                        Choose Photo
                                    </button>
                                    <button
                                        type="button"
                                        className="flex items-center gap-2.5 border-t border-surface-5 px-4 py-3 text-sm text-text-primary hover:bg-surface-2 active:bg-surface-3"
                                        onClick={() => { setShowAttachMenu(false); fileInputRef.current?.click(); }}
                                    >
                                        <Paperclip size={16} className="shrink-0 text-text-muted" />
                                        Attach File
                                    </button>
                                </div>
                            </>
                        )}
                        <input
                            ref={cameraInputRef}
                            type="file"
                            accept="image/*"
                            capture="environment"
                            className="hidden"
                            onChange={handleCameraCapture}
                        />
                        <input
                            ref={galleryInputRef}
                            type="file"
                            accept="image/*"
                            className="hidden"
                            onChange={handleGallerySelect}
                        />
                    </div>
                )}

                <textarea
                    ref={textareaRef}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    onPaste={handlePaste}
                    placeholder={isMobile ? 'Ask anything…' : 'Ask anything… Shift+Enter for new line'}
                    rows={1}
                    className={cn(
                        'flex-1 bg-transparent text-text-primary resize-none outline-none placeholder:text-text-muted',
                        isMobile ? 'text-base min-h-[44px] py-2' : 'text-sm min-h-[36px] py-1.5',
                        'max-h-[180px]',
                    )}
                />

                {isMobile && (
                    <button
                        type="button"
                        onClick={isListening ? stopListening : startListening}
                        className={cn(
                            'shrink-0 rounded p-2.5 transition-colors',
                            isListening
                                ? 'animate-pulse-slow bg-accent-red/10 text-accent-red'
                                : 'text-text-muted hover:bg-surface-2 hover:text-text-secondary',
                        )}
                        title={isListening ? 'Stop listening' : 'Voice input'}
                    >
                        {isListening ? <MicOff size={20} /> : <Mic size={20} />}
                    </button>
                )}

                <button
                    type="button"
                    onClick={handleSend}
                    disabled={isStreaming || (!text.trim() && !pastedImage)}
                    className={cn(
                        'shrink-0 transition-colors',
                        isMobile ? 'rounded-full p-2.5' : 'rounded p-2',
                        isStreaming || (!text.trim() && !pastedImage)
                            ? isMobile
                                ? 'cursor-not-allowed bg-surface-3 text-text-muted'
                                : 'cursor-not-allowed text-text-muted'
                            : isMobile
                                ? 'bg-accent text-white hover:bg-accent/90'
                                : 'text-accent hover:bg-white/5',
                    )}
                    title={isMobile ? 'Send' : 'Send (Enter)'}
                >
                    <Send size={isMobile ? 20 : 18} />
                </button>
            </div>
        </div>
    );
}
