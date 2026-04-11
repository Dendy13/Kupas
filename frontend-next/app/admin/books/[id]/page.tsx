import Link from 'next/link'
import { ChunkVerifier } from '@/components/extraction/ChunkVerifier'
import type { ExtractionChunk, ExtractionSession } from '@/types/extraction'

interface Props {
  params: Promise<{ id: string }>
}

interface BookDetail {
  id: number
  slug: string
  title: string | null
  author: string | null
  subject: string | null
  grade: string | null
}

export default async function AdminBookDetailPage({ params }: Props) {
  const { id } = await params
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ''

  // -------------------------------------------------------------------------
  // Fetch book info
  // -------------------------------------------------------------------------
  let book: BookDetail | null = null
  try {
    const res = await fetch(`${apiUrl}/books`, { cache: 'no-store' })
    if (res.ok) {
      const books: BookDetail[] = await res.json()
      book = books.find((b) => String(b.id) === id) ?? null
    }
  } catch {
    // non-fatal — we'll still show the extraction data
  }

  // -------------------------------------------------------------------------
  // Fetch latest extraction session (chunks) for this book
  // -------------------------------------------------------------------------
  let extractionSession: ExtractionSession | null = null
  try {
    const res = await fetch(`${apiUrl}/api/admin/books/${id}/extraction`, {
      cache: 'no-store',
    })
    if (res.ok) {
      extractionSession = await res.json()
    } else if (res.status !== 404) {
      // 404 means no session yet — that's fine
      const err = await res.json().catch(() => ({}))
      console.error('Failed to fetch extraction session:', err)
    }
  } catch (err) {
    console.error('Failed to fetch extraction session:', err)
  }

  const chunks: ExtractionChunk[] = extractionSession?.chunks ?? []

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                               */}
      {/* ------------------------------------------------------------------ */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="mb-1 text-xs text-slate-400">
            <Link href="/admin" className="hover:underline">
              Admin
            </Link>{' '}
            / Buku #{id}
          </p>
          <h1 className="text-xl font-bold text-slate-800">
            {book?.title ?? `Buku #${id}`}
          </h1>
          {book && (
            <p className="mt-0.5 text-sm text-slate-500">
              {[book.author, book.subject, book.grade].filter(Boolean).join(' · ')}
            </p>
          )}
        </div>
        <Link
          href={`/admin/books/${id}/verify-extraction`}
          className="shrink-0 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100"
        >
          Ekstrak Ulang
        </Link>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Chunk list — read-only overview                                      */}
      {/* ------------------------------------------------------------------ */}
      <section>
        <h2 className="mb-3 text-base font-semibold text-slate-700">
          Daftar Chunk{chunks.length > 0 && ` (${chunks.length})`}
        </h2>

        {chunks.length === 0 ? (
          <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
            Belum ada chunk tersimpan untuk buku ini.
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2">#</th>
                  <th className="px-4 py-2">Judul</th>
                  <th className="px-4 py-2 text-right">Halaman</th>
                  <th className="px-4 py-2 text-right">Karakter</th>
                  <th className="px-4 py-2 text-center">Terverifikasi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {chunks.map((chunk, idx) => (
                  <tr key={chunk.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2 text-slate-400">{idx + 1}</td>
                    <td className="max-w-xs truncate px-4 py-2 font-medium text-slate-700">
                      {chunk.title}
                    </td>
                    <td className="px-4 py-2 text-right text-slate-500">
                      {chunk.start_page}–{chunk.end_page}
                    </td>
                    <td className="px-4 py-2 text-right text-slate-500">
                      {(chunk.char_count ?? chunk.content.length).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {chunk.is_verified ? (
                        <span className="text-green-600">✓</span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Inline verification UI                                               */}
      {/* ------------------------------------------------------------------ */}
      <ChunkVerifier bookId={id} initialSession={extractionSession} />
    </main>
  )
}
