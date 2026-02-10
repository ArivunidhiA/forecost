'use client';

import { ReactNode } from 'react';
import ErrorBoundary from './ErrorBoundary';

/**
 * Client-side error boundary wrapper for use in server component layouts.
 */
export default function ClientErrorBoundary({ children }: { children: ReactNode }) {
  return <ErrorBoundary>{children}</ErrorBoundary>;
}
