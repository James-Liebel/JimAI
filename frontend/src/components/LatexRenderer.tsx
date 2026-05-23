import katex from 'katex';
import 'katex/dist/katex.min.css';

interface Props {
    expression: string;
    display?: boolean;
}

export default function LatexRenderer({ expression, display = false }: Props) {
    try {
        const html = katex.renderToString(expression, {
            displayMode: display,
            throwOnError: false,
            // trust:false (KaTeX default) — blocks \href{javascript:…}, \htmlData, and raw
            // HTML injection. Math content can come from model output, so never trust it.
            trust: false,
        });
        return <span dangerouslySetInnerHTML={{ __html: html }} />;
    } catch {
        return <code className="text-accent-red">{expression}</code>;
    }
}
