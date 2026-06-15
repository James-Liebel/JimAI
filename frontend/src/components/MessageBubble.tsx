import { useState } from 'react';
import { ThumbsUp, ThumbsDown, Check, AlertTriangle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
// Ship KaTeX's stylesheet with this (lazy) chunk instead of a render-blocking
// CDN <link> in index.html: math styling loads with MessageBubble — off the
// startup critical path — and stays fully local (no CDN dependency).
import 'katex/dist/katex.min.css';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import hljsStyle from 'react-syntax-highlighter/dist/esm/styles/hljs/vs2015';

// highlight.js "Light" build with a curated language set. This avoids the
// Prism/refractor path (the ~673KB chunk + the prismjs DOM-clobbering advisory);
// hljs core plus these grammars is a small fraction of that size.
import jsLang from 'react-syntax-highlighter/dist/esm/languages/hljs/javascript';
import tsLang from 'react-syntax-highlighter/dist/esm/languages/hljs/typescript';
import pyLang from 'react-syntax-highlighter/dist/esm/languages/hljs/python';
import jsonLang from 'react-syntax-highlighter/dist/esm/languages/hljs/json';
import bashLang from 'react-syntax-highlighter/dist/esm/languages/hljs/bash';
import shellLang from 'react-syntax-highlighter/dist/esm/languages/hljs/shell';
import cssLang from 'react-syntax-highlighter/dist/esm/languages/hljs/css';
import xmlLang from 'react-syntax-highlighter/dist/esm/languages/hljs/xml';
import sqlLang from 'react-syntax-highlighter/dist/esm/languages/hljs/sql';
import mdLang from 'react-syntax-highlighter/dist/esm/languages/hljs/markdown';
import yamlLang from 'react-syntax-highlighter/dist/esm/languages/hljs/yaml';
import rustLang from 'react-syntax-highlighter/dist/esm/languages/hljs/rust';
import goLang from 'react-syntax-highlighter/dist/esm/languages/hljs/go';
import javaLang from 'react-syntax-highlighter/dist/esm/languages/hljs/java';
import cLang from 'react-syntax-highlighter/dist/esm/languages/hljs/c';
import cppLang from 'react-syntax-highlighter/dist/esm/languages/hljs/cpp';
import dockerLang from 'react-syntax-highlighter/dist/esm/languages/hljs/dockerfile';
import powershellLang from 'react-syntax-highlighter/dist/esm/languages/hljs/powershell';
import diffLang from 'react-syntax-highlighter/dist/esm/languages/hljs/diff';
import textLang from 'react-syntax-highlighter/dist/esm/languages/hljs/plaintext';

SyntaxHighlighter.registerLanguage('javascript', jsLang);
SyntaxHighlighter.registerLanguage('js', jsLang);
SyntaxHighlighter.registerLanguage('jsx', jsLang);
SyntaxHighlighter.registerLanguage('typescript', tsLang);
SyntaxHighlighter.registerLanguage('ts', tsLang);
SyntaxHighlighter.registerLanguage('tsx', tsLang);
SyntaxHighlighter.registerLanguage('python', pyLang);
SyntaxHighlighter.registerLanguage('py', pyLang);
SyntaxHighlighter.registerLanguage('json', jsonLang);
SyntaxHighlighter.registerLanguage('bash', bashLang);
SyntaxHighlighter.registerLanguage('sh', bashLang);
SyntaxHighlighter.registerLanguage('shell', shellLang);
SyntaxHighlighter.registerLanguage('css', cssLang);
SyntaxHighlighter.registerLanguage('html', xmlLang);
SyntaxHighlighter.registerLanguage('xml', xmlLang);
SyntaxHighlighter.registerLanguage('markup', xmlLang);
SyntaxHighlighter.registerLanguage('sql', sqlLang);
SyntaxHighlighter.registerLanguage('markdown', mdLang);
SyntaxHighlighter.registerLanguage('md', mdLang);
SyntaxHighlighter.registerLanguage('yaml', yamlLang);
SyntaxHighlighter.registerLanguage('yml', yamlLang);
SyntaxHighlighter.registerLanguage('rust', rustLang);
SyntaxHighlighter.registerLanguage('rs', rustLang);
SyntaxHighlighter.registerLanguage('go', goLang);
SyntaxHighlighter.registerLanguage('java', javaLang);
SyntaxHighlighter.registerLanguage('c', cLang);
SyntaxHighlighter.registerLanguage('cpp', cppLang);
SyntaxHighlighter.registerLanguage('c++', cppLang);
SyntaxHighlighter.registerLanguage('docker', dockerLang);
SyntaxHighlighter.registerLanguage('dockerfile', dockerLang);
SyntaxHighlighter.registerLanguage('powershell', powershellLang);
SyntaxHighlighter.registerLanguage('ps1', powershellLang);
SyntaxHighlighter.registerLanguage('diff', diffLang);
SyntaxHighlighter.registerLanguage('text', textLang);
SyntaxHighlighter.registerLanguage('plaintext', textLang);
import type { Message, JudgeResult, ConsistencyResult } from '../lib/types';
import RouterBadge from './RouterBadge';
import { cn, formatTimestamp, preprocessLatex } from '../lib/utils';
import { useMediaQuery } from '../hooks/useMediaQuery';
import * as api from '../lib/api';

interface Props {
    message: Message;
}

function normalizeSourceScore(score: number): number {
    if (!Number.isFinite(score)) return 0;
    if (score > 1) return Math.max(0, Math.min(1, score / 100));
    return Math.max(0, Math.min(1, score));
}

function normalizeSourceUrl(source: { source?: string; url?: string }): string {
    const candidate = String(source.url || source.source || '').trim();
    return /^https?:\/\//i.test(candidate) ? candidate : '';
}

function sourceDisplayLabel(source: { source?: string; url?: string }): string {
    const url = normalizeSourceUrl(source);
    if (!url) return String(source.source || 'source');
    try {
        return new URL(url).hostname.replace(/^www\./i, '');
    } catch {
        return url;
    }
}

export default function MessageBubble({ message }: Props) {
    const [showSources, setShowSources] = useState(false);
    const [feedbackState, setFeedbackState] = useState<'none' | 'noting-up' | 'noting-down' | 'done'>('none');
    const [note, setNote] = useState('');
    const [correction, setCorrection] = useState('');
    const isMobile = useMediaQuery('(max-width: 768px)');

    const isUser = message.role === 'user';
    const hasSources = message.sources && message.sources.length > 0;
    const routing = message.routing;
    const autoWebAttempted = Boolean(routing?.auto_web_research_attempted);
    const autoWebOk = Boolean(routing?.auto_web_research_ok);
    const autoWebResults = Number(routing?.auto_web_research_results || 0);
    const autoWebQueries = Number(routing?.auto_web_research_query_count || 0);
    const autoWebPages = Number(routing?.auto_web_research_fetched_pages || 0);
    const rankedSources = (message.sources || [])
        .slice()
        .sort((left, right) => normalizeSourceScore(right.score) - normalizeSourceScore(left.score));

    const handleThumbsUp = () => {
        setFeedbackState('noting-up');
    };

    const handleThumbsDown = () => {
        setFeedbackState('noting-down');
    };

    const handleSubmitFeedback = async () => {
        const isPositive = feedbackState === 'noting-up';
        await api.submitFeedback(
            message.content,
            isPositive ? '' : message.content,
            correction,
            message.mode,
            isPositive,
            note,
        );
        setFeedbackState('done');
        setNote('');
        setCorrection('');
    };

    const handleSkipNote = async () => {
        const isPositive = feedbackState === 'noting-up';
        await api.submitFeedback(
            message.content,
            isPositive ? '' : message.content,
            '',
            message.mode,
            isPositive,
            '',
        );
        setFeedbackState('done');
    };

    return (
        <div className={cn('group animate-slide-up', isUser ? 'flex justify-end' : 'flex justify-start')}>
            <div
                className={cn(
                    'transition-colors',
                    // User turns get a soft filled bubble; assistant turns render flat
                    // on the page (no card/border/shadow) the way Claude/ChatGPT do.
                    isUser
                        ? 'rounded-2xl bg-surface-2 px-4 py-2.5 text-text-primary'
                        : 'w-full text-text-primary',
                    isUser && (isMobile ? 'max-w-[90%]' : 'max-w-[min(42rem,80%)]'),
                    !isUser && (isMobile ? 'max-w-full' : 'max-w-[min(50rem,100%)]'),
                )}
            >
                <div
                    className={cn(
                        isUser ? 'max-w-none' : 'prose prose-invert prose-sm max-w-none break-words',
                        message.isStreaming && !isUser && 'streaming-cursor',
                    )}
                >
                    {isUser ? (
                        <p className="m-0 whitespace-pre-wrap break-words text-[15px] leading-relaxed text-text-primary">{message.content}</p>
                    ) : (
                        <>
                        {message.browserScreenshotBase64 && (
                            <div className="mb-3 space-y-1">
                                {message.browserScreenshotUrl && (
                                    <p className="m-0 text-[11px] text-text-muted">
                                        Headless capture:{' '}
                                        <a
                                            href={message.browserScreenshotUrl}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="text-accent underline-offset-2 hover:underline"
                                        >
                                            {message.browserScreenshotUrl}
                                        </a>
                                    </p>
                                )}
                                <img
                                    src={`data:image/png;base64,${message.browserScreenshotBase64}`}
                                    alt="Browser viewport capture"
                                    className="max-h-[min(70vh,520px)] w-auto max-w-full border border-surface-4 object-contain"
                                />
                            </div>
                        )}
                        <ReactMarkdown
                            remarkPlugins={[remarkMath]}
                            rehypePlugins={[rehypeKatex]}
                            components={{
                                code({ className, children, ...props }) {
                                    const match = /language-(\w+)/.exec(className || '');
                                    const codeString = String(children).replace(/\n$/, '');
                                    const isPython = match && (match[1] === 'python' || match[1] === 'py');

                                    if (match) {
                                        return (
                                            <CodeBlock
                                                code={codeString}
                                                language={match[1]}
                                                showRun={!!isPython}
                                            />
                                        );
                                    }
                                    return (
                                        <code className="bg-surface-3 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
                                            {children}
                                        </code>
                                    );
                                },
                            }}
                        >
                            {preprocessLatex(message.content) || (message.isStreaming ? '' : '*Empty response*')}
                        </ReactMarkdown>
                        </>
                    )}
                </div>

                {/* Sources accordion */}
                {!isUser && (hasSources || autoWebAttempted) && (
                    <div className="mt-2 pt-2 border-t border-surface-5 space-y-2">
                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            {hasSources && (
                                <span className="rounded-badge border border-accent/30 bg-accent/10 px-2 py-1 text-accent">
                                    Web-backed · {message.sources!.length} source{message.sources!.length === 1 ? '' : 's'}
                                </span>
                            )}
                            {autoWebAttempted && (
                                <span
                                    className={cn(
                                        'rounded-badge border px-2 py-1',
                                        autoWebOk
                                            ? 'border-accent-green/30 bg-accent-green/10 text-accent-green'
                                            : 'border-accent-amber/30 bg-accent-amber/10 text-accent-amber',
                                    )}
                                    >
                                        {autoWebOk ? `Auto lookup used${autoWebResults > 0 ? ` · ${autoWebResults} results` : ''}` : 'Auto lookup attempted'}
                                    </span>
                                )}
                            {autoWebQueries > 0 && (
                                <span className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-1 text-text-secondary">
                                    {autoWebQueries} quer{autoWebQueries === 1 ? 'y' : 'ies'}
                                </span>
                            )}
                            {autoWebPages > 0 && (
                                <span className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-1 text-text-secondary">
                                    {autoWebPages} page{autoWebPages === 1 ? '' : 's'} read
                                </span>
                            )}
                            {!hasSources && autoWebAttempted && !autoWebOk && (
                                <span className="text-text-muted">
                                    answer may rely more heavily on model knowledge
                                </span>
                            )}
                        </div>
                        {hasSources && (
                            <div className="flex flex-wrap gap-1.5">
                                {rankedSources.slice(0, 3).map((s, i) => (
                                    normalizeSourceUrl(s) ? (
                                        <a
                                        key={`${s.source}-${i}`}
                                        href={normalizeSourceUrl(s)}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-1 text-[11px] text-text-secondary hover:text-text-primary"
                                        title={s.text}
                                    >
                                        #{i + 1} {sourceDisplayLabel(s)}
                                        </a>
                                    ) : (
                                        <button
                                            key={`${s.source}-${i}`}
                                            type="button"
                                            onClick={() => setShowSources((prev) => !prev)}
                                            className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-1 text-[11px] text-text-secondary hover:text-text-primary"
                                            title={s.text}
                                        >
                                            #{i + 1} {sourceDisplayLabel(s)}
                                        </button>
                                    )
                                ))}
                                {rankedSources.length > 3 && (
                                    <button
                                        type="button"
                                        onClick={() => setShowSources((prev) => !prev)}
                                        className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-1 text-[11px] text-text-muted hover:text-text-primary"
                                    >
                                        +{rankedSources.length - 3} more
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                )}
                {hasSources && showSources && (
                    <div className="mt-1.5 space-y-1">
                        {rankedSources.map((s, i) => (
                            <div key={i} className="text-[11px] text-text-muted bg-surface-2 rounded p-2">
                                <span className="font-medium text-text-secondary">#{i + 1} {sourceDisplayLabel(s)}</span>
                                {typeof s.score === 'number' && Number.isFinite(s.score) && (
                                    <span className="opacity-60 ml-1">
                                        ({(normalizeSourceScore(s.score) * 100).toFixed(0)}%)
                                    </span>
                                )}
                                <p className="mt-0.5 opacity-75 line-clamp-2">{s.text}</p>
                                {normalizeSourceUrl(s) && (
                                    <a href={normalizeSourceUrl(s)} target="_blank" rel="noreferrer" className="mt-1 inline-block text-accent hover:underline">
                                        {normalizeSourceUrl(s)}
                                    </a>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Review verdict (layered confirmation) */}
                {message.routing?.review && !isUser && (
                    <details className="mt-2 pt-2 border-t border-surface-5">
                        <summary className="flex items-center gap-1 text-[11px] text-text-muted cursor-pointer hover:text-text-secondary">
                            <Check size={11} /> Review
                        </summary>
                        <p className="mt-1 text-[11px] text-text-muted whitespace-pre-wrap">{message.routing.review}</p>
                    </details>
                )}

                {/* Judge panel (model-as-judge verification) */}
                {message.routing?.judge?.ran && !isUser && (
                    <JudgePanel judge={message.routing.judge} />
                )}

                {/* Self-consistency badge (math) */}
                {message.routing?.consistency && message.routing.consistency.n_samples != null && message.routing.consistency.n_samples > 1 && !isUser && (
                    <div className="mt-2 pt-2 border-t border-surface-5 flex items-center gap-2">
                        <ConsistencyBadge consistency={message.routing.consistency} />
                    </div>
                )}

                {/* Router badge (model + compare/judge when used) */}
                {message.routing && !isUser && (
                    <div className="mt-2 pt-2 border-t border-surface-5 flex items-center justify-between flex-wrap gap-1">
                        <RouterBadge routing={message.routing} />
                        <span className="text-[10px] text-text-muted">{formatTimestamp(message.timestamp)}</span>
                    </div>
                )}

                {/* Feedback */}
                {!isUser && !message.isStreaming && (
                    <div className="mt-1.5">
                        {feedbackState === 'none' && (
                            <div className={cn(
                                'flex gap-0.5 transition-opacity',
                                isMobile ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
                            )}>
                                <button onClick={handleThumbsUp} className={cn('rounded text-text-muted transition-colors hover:bg-surface-3 hover:text-status-success', isMobile ? 'p-2' : 'p-1.5')} title="Good response" aria-label="Good response"><ThumbsUp size={isMobile ? 16 : 14} /></button>
                                <button onClick={handleThumbsDown} className={cn('rounded text-text-muted transition-colors hover:bg-surface-3 hover:text-status-error', isMobile ? 'p-2' : 'p-1.5')} title="Bad response" aria-label="Bad response"><ThumbsDown size={isMobile ? 16 : 14} /></button>
                            </div>
                        )}

                        {(feedbackState === 'noting-up' || feedbackState === 'noting-down') && (
                            <div className="w-full animate-fade-in mt-1 space-y-2">
                                <div className={cn(
                                    'flex items-center gap-1.5 text-xs font-medium',
                                    feedbackState === 'noting-up' ? 'text-status-success' : 'text-status-error',
                                )}>
                                    {feedbackState === 'noting-up' ? <ThumbsUp size={13} /> : <ThumbsDown size={13} />}
                                    {feedbackState === 'noting-up' ? 'Good response' : 'Bad response'}
                                </div>

                                <textarea
                                    value={note}
                                    onChange={(e) => setNote(e.target.value)}
                                    placeholder={feedbackState === 'noting-up'
                                        ? 'What was good about this? (optional)'
                                        : 'What was wrong? (optional)'}
                                    className={cn(
                                        'w-full bg-surface-2 text-text-primary rounded p-2 resize-none border border-surface-4 focus:border-accent outline-none',
                                        isMobile ? 'text-sm min-h-[44px]' : 'text-xs',
                                    )}
                                    rows={2}
                                />

                                {feedbackState === 'noting-down' && (
                                    <textarea
                                        value={correction}
                                        onChange={(e) => setCorrection(e.target.value)}
                                        placeholder="What should it have said instead? (optional)"
                                        className={cn(
                                            'w-full bg-surface-2 text-text-primary rounded p-2 resize-none border border-surface-4 focus:border-accent outline-none',
                                            isMobile ? 'text-sm min-h-[44px]' : 'text-xs',
                                        )}
                                        rows={2}
                                    />
                                )}

                                <div className="flex gap-2">
                                    <button
                                        onClick={handleSubmitFeedback}
                                        className={cn(
                                            'bg-accent rounded-btn font-medium text-white hover:bg-accent-hover transition-colors',
                                            isMobile ? 'text-sm px-4 py-2' : 'text-xs px-3 py-1',
                                        )}
                                    >
                                        Submit
                                    </button>
                                    <button
                                        onClick={handleSkipNote}
                                        className={cn(
                                            'text-text-muted hover:text-text-secondary transition-colors',
                                            isMobile ? 'text-sm px-4 py-2' : 'text-xs px-2 py-1',
                                        )}
                                    >
                                        Skip
                                    </button>
                                </div>
                            </div>
                        )}

                        {feedbackState === 'done' && (
                            <span className={cn('text-text-muted animate-fade-in', isMobile ? 'text-xs' : 'text-[11px]')}>
                                Feedback saved
                            </span>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

function JudgePanel({ judge }: { judge: JudgeResult }) {
    const [open, setOpen] = useState(false);
    if (judge.passed && judge.confidence === 'high' && judge.issues.length === 0) {
        return (
            <div className="mt-2 pt-2 border-t border-surface-5 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-accent-green" title={`Verified by ${judge.judge_model} — no issues`} />
                <span className="text-[11px] text-text-muted">Verified by {judge.judge_model}</span>
            </div>
        );
    }
    if (judge.passed && (judge.confidence !== 'high' || judge.suggestions.length > 0)) {
        return (
            <div className="mt-2 pt-2 border-t border-surface-5">
                <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 text-[11px] text-status-warning hover:text-status-warning/80">
                    <span className="w-2 h-2 rounded-full bg-status-warning" />
                    Suggestions available — click to expand
                </button>
                {open && (
                    <ul className="mt-1.5 ml-4 text-[11px] text-text-muted list-disc space-y-0.5">
                        {judge.suggestions.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                )}
            </div>
        );
    }
    if (!judge.passed && judge.was_revised) {
        return (
            <details className="mt-2 pt-2 border-t border-surface-5">
                <summary className="flex items-center gap-1 text-[11px] text-status-warning cursor-pointer">
                    <AlertTriangle size={11} /> Response revised by judge — issues were found
                </summary>
                <div className="mt-1.5 space-y-1 text-[11px] text-text-muted">
                    <p className="font-medium text-status-warning">Issues:</p>
                    <ul className="list-disc ml-4">{judge.issues.map((i, k) => <li key={k}>{i}</li>)}</ul>
                    {judge.suggestions.length > 0 && (
                        <>
                            <p className="font-medium mt-2">Suggestions:</p>
                            <ul className="list-disc ml-4">{judge.suggestions.map((s, k) => <li key={k}>{s}</li>)}</ul>
                        </>
                    )}
                </div>
            </details>
        );
    }
    if (!judge.passed) {
        return (
            <details className="mt-2 pt-2 border-t border-surface-5">
                <summary className="flex items-center gap-1 text-[11px] text-status-error cursor-pointer">
                    <AlertTriangle size={11} /> Judge flagged issues — review carefully
                </summary>
                <div className="mt-1.5 space-y-1 text-[11px] text-text-muted">
                    <ul className="list-disc ml-4">{judge.issues.map((i, k) => <li key={k}>{i}</li>)}</ul>
                    {judge.suggestions.length > 0 && (
                        <>
                            <p className="font-medium mt-2">Suggestions:</p>
                            <ul className="list-disc ml-4">{judge.suggestions.map((s, k) => <li key={k}>{s}</li>)}</ul>
                        </>
                    )}
                </div>
            </details>
        );
    }
    return null;
}

function ConsistencyBadge({ consistency }: { consistency: ConsistencyResult }) {
    const n = consistency.n_samples ?? 0;
    const rate = consistency.agreement_rate ?? 0;
    const agreed = n > 0 ? Math.round(rate * n) : 0;
    const label = `${agreed}/${n}`;
    const color = rate >= 0.8 ? 'text-accent-green' : rate >= 0.6 ? 'text-status-warning' : 'text-accent-red';
    return (
        <span
            className={cn('text-[11px] font-medium', color)}
            title={`Agreement: ${(rate * 100).toFixed(0)}% across ${n} samples${consistency.disagreements?.length ? `. Disagreements: ${consistency.disagreements.join(', ')}` : ''}`}
        >
            {label}
        </span>
    );
}

function CodeBlock({ code, language, showRun }: { code: string; language: string; showRun: boolean }) {
    const [copied, setCopied] = useState(false);
    const [output, setOutput] = useState<{ stdout: string; stderr: string } | null>(null);
    const [running, setRunning] = useState(false);
    const isTouchDevice = 'ontouchstart' in window;

    const handleCopy = () => {
        navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleRun = async () => {
        setRunning(true);
        try {
            const result = await api.executeCode(code);
            setOutput(result);
        } catch (err) {
            setOutput({ stdout: '', stderr: String(err) });
        } finally {
            setRunning(false);
        }
    };

    return (
        <div className="relative group/code my-2">
            <div className={cn(
                'absolute top-2 right-2 flex gap-1 transition-opacity z-10',
                isTouchDevice ? 'opacity-100' : 'opacity-0 group-hover/code:opacity-100',
            )}>
                <span className={cn('bg-surface-4 rounded text-text-muted', isTouchDevice ? 'px-2 py-1 text-xs' : 'px-1.5 py-0.5 text-[10px]')}>{language}</span>
                <button onClick={handleCopy} className={cn('bg-surface-4 rounded text-text-secondary hover:text-text-primary', isTouchDevice ? 'px-2 py-1 text-xs' : 'px-1.5 py-0.5 text-[10px]')}>
                    {copied ? <Check size={12} /> : 'Copy'}
                </button>
                {showRun && (
                    <button onClick={handleRun} disabled={running} className={cn('bg-accent-green/20 text-accent-green rounded hover:bg-accent-green/30 disabled:opacity-50', isTouchDevice ? 'px-2 py-1 text-xs' : 'px-1.5 py-0.5 text-[10px]')}>
                        {running ? '...' : 'Run ▶'}
                    </button>
                )}
            </div>
            <SyntaxHighlighter
                style={hljsStyle}
                language={language}
                PreTag="div"
                customStyle={{ margin: 0, borderRadius: '8px', fontSize: '13px', background: '#1E1A16' }}
            >
                {code}
            </SyntaxHighlighter>
            {output && (
                <div className="mt-1 bg-surface-0 border border-surface-4 rounded p-2 text-xs font-mono">
                    {output.stdout && <pre className="text-accent-green whitespace-pre-wrap">{output.stdout}</pre>}
                    {output.stderr && <pre className="text-accent-red whitespace-pre-wrap">{output.stderr}</pre>}
                </div>
            )}
        </div>
    );
}
