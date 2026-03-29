import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Kupas — Platform Edukasi AI Kemdikdasmen',
  description:
    'Kupas buku-buku resmi Kemdikdasmen secara instan — dapatkan ringkasan dan soal latihan otomatis berbasis AI.',
  keywords: ['buku pelajaran', 'Kemdikdasmen', 'ringkasan', 'soal latihan', 'AI', 'edukasi'],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body className="font-sans antialiased">
        <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
          <div className="max-w-6xl mx-auto px-6 h-16 flex items-center gap-6">
            <a href="/" className="text-2xl font-extrabold tracking-tight text-blue-600 shrink-0">
              Ku<span className="text-amber-500">pas</span>
            </a>
            <p className="text-sm text-slate-500 hidden sm:block">
              Ringkasan &amp; soal latihan dari buku Kemdikdasmen berbasis AI
            </p>
          </div>
        </header>
        {children}
        <footer className="text-center py-6 text-sm text-slate-400 border-t border-slate-200">
          &copy; 2024 Kupas &middot; Platform edukasi AI dari buku resmi Kemdikdasmen
        </footer>
      </body>
    </html>
  )
}
