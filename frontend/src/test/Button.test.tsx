import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { Button } from '../components/ui/Button';

describe('Button', () => {
    it('renders its label', () => {
        render(<Button>Save changes</Button>);
        expect(screen.getByRole('button', { name: 'Save changes' })).toBeTruthy();
    });

    it('calls onClick when pressed', async () => {
        const onClick = vi.fn();
        render(<Button onClick={onClick}>Run</Button>);
        await userEvent.click(screen.getByRole('button', { name: 'Run' }));
        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('ignores clicks while disabled', async () => {
        const onClick = vi.fn();
        render(<Button disabled onClick={onClick}>Run</Button>);
        await userEvent.click(screen.getByRole('button', { name: 'Run' }));
        expect(onClick).not.toHaveBeenCalled();
    });

    it('defaults to type=button so it never submits a parent form by accident', () => {
        render(<Button>Cancel</Button>);
        expect(screen.getByRole('button', { name: 'Cancel' }).getAttribute('type')).toBe('button');
    });
});
