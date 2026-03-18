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
            trust: true,
        });
        return <span dangerouslySetInnerHTML={{ __html: html }} />;
    } catch {
        return <code className="text-accent-red">{expression}</code>;
    }
}
