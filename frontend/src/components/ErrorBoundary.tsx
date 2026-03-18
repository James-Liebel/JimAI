import React from 'react';

interface ErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
}

interface ErrorBoundaryProps {
    children: React.ReactNode;
}

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error('[ErrorBoundary] Caught render error:', error, info.componentStack);
    }

    render() {
        if (this.state.hasError) {
            const isDev = import.meta.env.DEV;
            return (
                <div className="h-screen w-screen flex items-center justify-center bg-surface-0 p-6">
                    <div className="max-w-lg w-full rounded-card border border-accent-red/40 bg-surface-1 p-8 text-center">
                        <h1 className="text-xl font-semibold text-accent-red mb-3">Something went wrong</h1>
                        <p className="text-sm text-text-secondary mb-4">
                            An unexpected error occurred. You can try reloading the app.
                        </p>
                        {isDev && this.state.error && (
                            <pre className="mb-5 text-left text-xs text-text-muted bg-surface-0 border border-surface-3 rounded-btn p-3 overflow-auto max-h-48 whitespace-pre-wrap">
                                {this.state.error.message}
                                {'\n'}
                                {this.state.error.stack}
                            </pre>
                        )}
                        <button
                            type="button"
                            onClick={() => window.location.reload()}
                            className="px-4 py-2 rounded-btn border border-accent-red/40 bg-accent-red/10 text-accent-red text-sm hover:bg-accent-red/20 transition-colors"
                        >
                            Reload App
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
