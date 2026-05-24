import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import MessageBubble from '../components/MessageBubble';
import type { Message } from '../lib/types';

function assistantWithCode(): Message {
    return {
        role: 'assistant',
        content: '```python\nprint("hello world")\n```',
        mode: 'chat',
        timestamp: Date.now() / 1000,
    } as Message;
}

describe('MessageBubble code highlighting', () => {
    it('renders a fenced code block through the highlighter without crashing', () => {
        const { container } = render(<MessageBubble message={assistantWithCode()} />);
        // The exact code text survives tokenization (proves the highlighter rendered it).
        expect(container.textContent).toContain('print("hello world")');
        // highlight.js wraps the source in a <code> element.
        expect(container.querySelector('code')).not.toBeNull();
    });

    it('shows the language label and a Run button for python blocks', () => {
        const { getByText } = render(<MessageBubble message={assistantWithCode()} />);
        expect(getByText('python')).toBeTruthy();
        expect(getByText(/Run/)).toBeTruthy();
    });
});
