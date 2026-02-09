/**
 * LLMLab Utility Functions
 * @description Helper functions for formatting and common operations
 */

/**
 * Format a number as USD currency
 */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

/**
 * Format a number with compact notation (e.g., 1.2K, 1.5M)
 */
export function formatCompact(num: number): string {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    compactDisplay: 'short',
  }).format(num);
}

/**
 * Format a date string to readable format
 */
export function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  }).format(date);
}

/**
 * Format a date string to full readable format
 */
export function formatDateFull(dateStr: string): string {
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

/**
 * Calculate percentage
 */
export function percentage(value: number, total: number): number {
  if (total === 0) return 0;
  return (value / total) * 100;
}

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, length: number): string {
  if (text.length <= length) return text;
  return text.slice(0, length) + '...';
}

/**
 * Generate a color for a model name (consistent hashing)
 */
export function getModelColor(model: string): string {
  const colors = [
    '#3B82F6', // blue
    '#10B981', // emerald
    '#8B5CF6', // violet
    '#F59E0B', // amber
    '#EF4444', // red
    '#06B6D4', // cyan
    '#EC4899', // pink
    '#6366F1', // indigo
  ];
  
  // Simple hash based on model name
  let hash = 0;
  for (let i = 0; i < model.length; i++) {
    hash = model.charCodeAt(i) + ((hash << 5) - hash);
  }
  
  return colors[Math.abs(hash) % colors.length];
}

/**
 * Classname merger utility
 */
export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

/**
 * Get color class based on budget progress percentage
 */
export function getProgressColor(percentage: number): string {
  if (percentage >= 100) return 'bg-red-500';
  if (percentage >= 80) return 'bg-yellow-500';
  return 'bg-green-500';
}

/**
 * Get initials from a name (max 2 characters)
 */
export function getInitials(name: string): string {
  if (!name) return '?';
  return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
}

/**
 * Copy text to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
