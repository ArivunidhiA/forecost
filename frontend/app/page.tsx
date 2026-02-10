/**
 * Landing Page
 * @description Main landing page with hero, problem/solution, and install instructions
 */

'use client';

import Navigation from '@/components/Navigation';
import Button from '@/components/Button';
import Link from 'next/link';

export default function LandingPage() {
  const githubAuthUrl = `https://github.com/login/oauth/authorize?client_id=${process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID}&redirect_uri=${encodeURIComponent(process.env.NEXT_PUBLIC_GITHUB_REDIRECT_URI || '')}&scope=user:email`;

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950">
      <Navigation showUserMenu={false} />

      {/* Hero Section */}
      <section className="max-w-4xl mx-auto px-4 sm:px-6 pt-20 pb-16 text-center">
        <h1 className="text-5xl sm:text-6xl font-bold text-slate-900 dark:text-white leading-tight tracking-tight">
          Track your LLM costs<br />
          <span className="text-slate-500 dark:text-slate-400">in 2 minutes</span>
        </h1>
        
        <p className="mt-6 text-xl text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
          A simple proxy that sits between you and your LLM providers. 
          Just swap an environment variable and start tracking.
        </p>

        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link href={githubAuthUrl}>
            <Button size="lg" variant="primary">
              <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              Log in with GitHub
            </Button>
          </Link>
          <a href="#how-it-works">
            <Button size="lg" variant="outline">
              See how it works
            </Button>
          </a>
        </div>
      </section>

      {/* Problem Statement */}
      <section className="py-20 bg-slate-50 dark:bg-slate-900/50">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <p className="text-sm font-medium text-red-600 dark:text-red-400 uppercase tracking-wide mb-2">
              The Problem
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 dark:text-white">
              Most devs have NO idea<br />how much they spend on AI
            </h2>
          </div>

          <div className="grid sm:grid-cols-3 gap-6 text-center">
            <div className="p-6">
              <div className="text-4xl mb-4">🤷</div>
              <p className="text-slate-600 dark:text-slate-400">
                Scattered across multiple providers
              </p>
            </div>
            <div className="p-6">
              <div className="text-4xl mb-4">📊</div>
              <p className="text-slate-600 dark:text-slate-400">
                No breakdown by model or project
              </p>
            </div>
            <div className="p-6">
              <div className="text-4xl mb-4">💸</div>
              <p className="text-slate-600 dark:text-slate-400">
                Surprise bills at month end
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Solution */}
      <section id="how-it-works" className="py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <p className="text-sm font-medium text-green-600 dark:text-green-400 uppercase tracking-wide mb-2">
              The Solution
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 dark:text-white">
              Proxy approach &mdash; just swap your env var
            </h2>
            <p className="mt-4 text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
              LLMLab acts as a transparent proxy. Your code stays the same, 
              you just point to our endpoint. We log every request and show you the costs.
            </p>
          </div>

          {/* How it works steps */}
          <div className="grid sm:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="w-12 h-12 bg-slate-900 dark:bg-white rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-white dark:text-slate-900 font-bold">1</span>
              </div>
              <h3 className="font-semibold text-slate-900 dark:text-white mb-2">Install CLI</h3>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                One pip command to get started
              </p>
            </div>
            <div className="text-center">
              <div className="w-12 h-12 bg-slate-900 dark:bg-white rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-white dark:text-slate-900 font-bold">2</span>
              </div>
              <h3 className="font-semibold text-slate-900 dark:text-white mb-2">Swap Base URL</h3>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                Point your OpenAI client to LLMLab
              </p>
            </div>
            <div className="text-center">
              <div className="w-12 h-12 bg-slate-900 dark:bg-white rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-white dark:text-slate-900 font-bold">3</span>
              </div>
              <h3 className="font-semibold text-slate-900 dark:text-white mb-2">Track Costs</h3>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                See real-time costs in dashboard
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Install Instructions */}
      <section className="py-20 bg-slate-900 dark:bg-black">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-white mb-4">
              Get started in seconds
            </h2>
            <p className="text-slate-400">
              Works with any OpenAI-compatible library
            </p>
          </div>

          {/* Code blocks */}
          <div className="space-y-6">
            {/* Install */}
            <div className="bg-slate-800 rounded-xl p-6 overflow-x-auto">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-slate-400 uppercase tracking-wide">Install</span>
                <button 
                  className="text-xs text-slate-400 hover:text-white transition-colors"
                  onClick={() => navigator.clipboard?.writeText('pip install llmlab-cli')}
                >
                  Copy
                </button>
              </div>
              <pre className="text-green-400 font-mono text-sm">
                <code>pip install llmlab-cli</code>
              </pre>
            </div>

            {/* Login */}
            <div className="bg-slate-800 rounded-xl p-6 overflow-x-auto">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-slate-400 uppercase tracking-wide">Authenticate</span>
              </div>
              <pre className="text-green-400 font-mono text-sm">
                <code>llmlab auth login</code>
              </pre>
            </div>

            {/* Usage */}
            <div className="bg-slate-800 rounded-xl p-6 overflow-x-auto">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-slate-400 uppercase tracking-wide">Python</span>
              </div>
              <pre className="text-slate-300 font-mono text-sm leading-relaxed">
<code>{`from openai import OpenAI

client = OpenAI(
    base_url="https://api.llmlab.dev/v1",  # Just change this
    api_key="llmlab_..."  # Your LLMLab key (wraps your real key)
)

# Use normally - costs are tracked automatically
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)`}</code>
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 text-center">
          <h2 className="text-3xl font-bold text-slate-900 dark:text-white mb-4">
            Ready to track your AI costs?
          </h2>
          <p className="text-slate-600 dark:text-slate-400 mb-8">
            Free forever for individual developers. No credit card required.
          </p>
          <Link href={githubAuthUrl}>
            <Button size="lg" variant="primary">
              <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              Get Started Free
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 dark:border-slate-800 py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center text-sm text-slate-500 dark:text-slate-400">
          <p>© 2024 LLMLab. Open source and free forever.</p>
        </div>
      </footer>
    </div>
  );
}
