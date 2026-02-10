/**
 * Root Layout
 * @description Global layout with dark mode support and Inter font
 */

import type { Metadata, Viewport } from 'next';
import { ReactNode } from 'react';
import ClientErrorBoundary from '@/components/ClientErrorBoundary';
import './globals.css';

export const metadata: Metadata = {
  title: 'LLMLab - Track Your LLM Costs',
  description: 'Track and optimize your LLM costs in 2 minutes. Simple proxy approach - just swap your env var.',
  icons: {
    icon: [
      {
        url: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%23000'/><text x='50%' y='50%' dominant-baseline='central' text-anchor='middle' font-size='14' font-weight='bold' fill='%23fff'>LL</text></svg>",
        type: 'image/svg+xml',
      },
    ],
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Prevent flash of wrong theme */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const theme = localStorage.getItem('theme');
                if (theme === 'dark' || (!theme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                  document.documentElement.classList.add('dark');
                } else {
                  document.documentElement.classList.remove('dark');
                }
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body className="antialiased">
        <ClientErrorBoundary>
          {children}
        </ClientErrorBoundary>
      </body>
    </html>
  );
}
