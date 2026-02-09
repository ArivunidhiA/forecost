/**
 * GitHub OAuth Callback Page
 * @description Handles the OAuth redirect, exchanges code for token, and redirects to dashboard
 */

'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api, setToken, setUser } from '@/lib/api';

export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get('code');
      const errorParam = searchParams.get('error');
      const errorDescription = searchParams.get('error_description');

      // Check for OAuth errors
      if (errorParam) {
        setError(errorDescription || errorParam);
        return;
      }

      // Check for code
      if (!code) {
        setError('No authorization code received');
        return;
      }

      try {
        // Exchange code for token
        const response = await api.githubCallback(code);
        
        // Store token
        setToken(response.token);

        // Construct and store user object from response fields
        setUser({
          id: response.user_id,
          github_id: 0,
          email: response.email,
          username: response.username,
          created_at: new Date().toISOString(),
        });

        // Redirect to dashboard
        router.push('/dashboard');
      } catch (err) {
        console.error('Auth callback error:', err);
        setError(err instanceof Error ? err.message : 'Authentication failed');
      }
    };

    handleCallback();
  }, [searchParams, router]);

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-white dark:bg-slate-950 flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <div className="w-16 h-16 bg-red-100 dark:bg-red-900/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">
            Authentication Failed
          </h1>
          <p className="text-slate-600 dark:text-slate-400 mb-6">
            {error}
          </p>
          <a
            href="/"
            className="inline-flex items-center justify-center px-4 py-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-lg font-medium hover:bg-slate-800 dark:hover:bg-slate-100 transition-colors"
          >
            Back to Home
          </a>
        </div>
      </div>
    );
  }

  // Loading state
  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 flex items-center justify-center">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-slate-300 border-t-slate-900 dark:border-slate-600 dark:border-t-white mb-4" />
        <p className="text-slate-600 dark:text-slate-400">
          Signing you in...
        </p>
      </div>
    </div>
  );
}
