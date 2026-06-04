import { lazy, Suspense } from 'react';
import { useMediaQuery } from '../hooks/useMediaQuery';
import LoadingScreen from '../components/LoadingScreen';

// Desktop drives an Electron <webview>; phones get the remote (laptop-hosted,
// screenshot-based) browser. Kept as separate lazily-mounted components so each
// owns its own hooks — switching across the breakpoint just unmounts/mounts.
const BrowserAtlas = lazy(() => import('./BrowserAtlas'));
const AtlasMobile = lazy(() => import('./AtlasMobile'));

export default function Atlas() {
    const isMobile = useMediaQuery('(max-width: 768px)');
    return (
        <Suspense fallback={<LoadingScreen fill label="Loading…" />}>
            {isMobile ? <AtlasMobile /> : <BrowserAtlas />}
        </Suspense>
    );
}
