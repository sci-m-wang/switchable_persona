import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Switchable Persona — 标注工具',
  description: 'Browser-first annotation UI for extraction results.'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body>
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
