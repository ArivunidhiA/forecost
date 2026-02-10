/**
 * Utils Tests
 */

import {
  formatCurrency,
  formatCompact,
  formatDate,
  formatDateFull,
  percentage,
  truncate,
  getModelColor,
  cn,
} from '@/lib/utils';

describe('formatCurrency', () => {
  it('formats positive amounts', () => {
    expect(formatCurrency(42.50)).toBe('$42.50');
    expect(formatCurrency(1234.56)).toBe('$1,234.56');
  });

  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0.00');
  });

  it('formats negative amounts', () => {
    expect(formatCurrency(-50)).toBe('-$50.00');
  });

  it('rounds to two decimal places', () => {
    expect(formatCurrency(42.555)).toBe('$42.56');
    expect(formatCurrency(42.554)).toBe('$42.55');
  });
});

describe('formatCompact', () => {
  it('formats thousands', () => {
    expect(formatCompact(1500)).toBe('1.5K');
    expect(formatCompact(1000)).toBe('1K');
  });

  it('formats millions', () => {
    expect(formatCompact(1500000)).toBe('1.5M');
  });

  it('handles small numbers', () => {
    expect(formatCompact(50)).toBe('50');
  });
});

describe('formatDate', () => {
  it('formats date strings', () => {
    expect(formatDate('2024-01-15T12:00:00Z')).toContain('Jan');
  });
});

describe('formatDateFull', () => {
  it('includes year', () => {
    expect(formatDateFull('2024-01-15T12:00:00Z')).toContain('Jan');
    expect(formatDateFull('2024-01-15T12:00:00Z')).toContain('2024');
  });
});

describe('percentage', () => {
  it('calculates percentage', () => {
    expect(percentage(25, 100)).toBe(25);
    expect(percentage(1, 4)).toBe(25);
  });

  it('handles zero total', () => {
    expect(percentage(10, 0)).toBe(0);
  });
});

describe('truncate', () => {
  it('truncates long text', () => {
    expect(truncate('Hello World', 5)).toBe('Hello...');
  });

  it('does not truncate short text', () => {
    expect(truncate('Hi', 5)).toBe('Hi');
  });
});

describe('getModelColor', () => {
  it('returns consistent color for same model', () => {
    const color1 = getModelColor('gpt-4');
    const color2 = getModelColor('gpt-4');
    expect(color1).toBe(color2);
  });

  it('returns valid hex colors', () => {
    const color = getModelColor('gpt-4');
    expect(color).toMatch(/^#[0-9A-F]{6}$/i);
  });
});

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar');
  });

  it('filters falsy values', () => {
    expect(cn('foo', false, null, undefined, 'bar')).toBe('foo bar');
  });
});
