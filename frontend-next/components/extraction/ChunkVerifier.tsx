'use client'

import { useCallback, useState } from 'react'
import type { ExtractionChunk, ExtractionSession } from '@/types/extraction'

interface Props {
  bookId: string
  initialSession: ExtractionSession | null
}

export function ChunkVerifier({ bookId, initialSession }: Props) {
  const [session, setSession] = useState<ExtractionSession | null>(initialSession)
  const normalizeChunks = (raw: ExtractionChunk[]) =>
    raw.map((c) => ({ ...c, char_count: c.char_count ?? c.content.length }))
  const [chunks, setChunks] = useState<ExtractionChunk[]>(normalizeChunks(initialSession?.chunks ?? []))
  const [selectedId, setSelectedId] = useState<number | null>(
    initialSession?.chunks[0]?.id ?? null
  )
  const [saving, setSaving] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ''
  const approved = session?.status === 'approved'

  // -------------------------------------------------------------------------
  // Patch a single chunk on the server
  // -------------------------------------------------------------------------
  const patchChunk = useCallback(
    async (chunk: ExtractionChunk, update: Partial<Pick<ExtractionChunk, 'title' | 'content' | 'is_verified'>>) => {
      if (approved || chunk.id === undefined) return
      try {
        const res = await fetch(`${apiUrl}/api/admin/books/${bookId}/chunks/${chunk.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(update),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body?.detail ?? `HTTP ${res.status}`)
        }
        const updated: ExtractionChunk = await res.json()
        setChunks((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
      } catch (err) {
        setError(`Gagal menyimpan: ${String(err)}`)
      }
    },
    [apiUrl, bookId, approved]
  )

  const handleTitleBlur = (chunk: ExtractionChunk, value: string) => {
    if (value !== chunk.title) patchChunk(chunk, { title: value })
  }

  const handleContentBlur = (chunk: ExtractionChunk, value: string) => {
    if (value !== chunk.content) patchChunk(chunk, { content: value })
  }

  const handleVerifiedToggle = (chunk: ExtractionChunk) => {
    patchChunk(chunk, { is_verified: !chunk.is_verified })
  }

  // -------------------------------------------------------------------------
  // Approve & Lock
  // -------------------------------------------------------------------------
  const handleApprove = async () => {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${apiUrl}/api/admin/books/${bookId}/approve-extraction`, {
        method: 'POST',
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail ?? `HTTP ${res.status}`)
      }
      const updatedSession: ExtractionSession = await res.json()
      setSession(updatedSession)
      setChunks(normalizeChunks(updatedSession.chunks))
      setStatusMsg('Ekstraksi disetujui & dikunci.')
    } catch (err) {
      setError(`Gagal menyetujui: ${String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------
  if (!session) {
    return (
      <div className="mt-8 rounded-xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-500">
        Belum ada sesi ekstraksi untuk buku ini. Jalankan ekstraksi PDF terlebih dahulu melalui{' '}
        <a href={`/admin/books/${bookId}/verify-extraction`} className="text-blue-600 underline">
          halaman verifikasi
        </a>
        .
      </div>
    )
  }

  const selectedChunk = chunks.find((c) => c.id === selectedId) ?? chunks[0] ?? null

  return (
    <section className="mt-8">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-800">Verifikasi Chunk</h2>
          <p className="text-xs text-slate-500">
            Sesi #{session.id} · status:{' '}
            <span
              className={
                approved
                  ? 'font-medium text-green-600'
                  : 'font-medium text-amber-600'
              }
            >
              {session.status}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          {statusMsg && <span className="text-xs text-green-600">✓ {statusMsg}</span>}
          {error && <span className="text-xs text-red-600">✗ {error}</span>}
          {!approved && (
            <button
              onClick={handleApprove}
              disabled={saving}
              className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Menyimpan…' : 'Setujui & Kunci'}
            </button>
          )}
          {approved && (
            <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-700">
              ✓ Disetujui
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-0 overflow-hidden rounded-xl border border-slate-200 lg:grid-cols-[280px_1fr]">
        {/* Chunk list */}
        <aside className="overflow-y-auto border-b border-slate-200 bg-white lg:border-b-0 lg:border-r">
          {chunks.map((chunk, idx) => (
            <button
              key={chunk.id ?? idx}
              onClick={() => setSelectedId(chunk.id ?? null)}
              className={`w-full border-b border-slate-100 px-4 py-3 text-left transition-colors hover:bg-slate-50 ${
                selectedId === chunk.id ? 'border-l-4 border-l-blue-500 bg-blue-50' : ''
              }`}
            >
              <p className="truncate text-sm font-medium text-slate-700">{chunk.title}</p>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
                <span>
                  Hal. {chunk.start_page}–{chunk.end_page}
                </span>
                <span>·</span>
                <span>{(chunk.char_count ?? chunk.content.length).toLocaleString()} kar.</span>
                {chunk.is_verified && (
                  <span className="rounded bg-green-100 px-1 text-green-700">✓</span>
                )}
              </div>
            </button>
          ))}
        </aside>

        {/* Editor pane */}
        <div className="bg-white p-5">
          {selectedChunk ? (
            <div className="flex flex-col gap-3">
              {/* Title */}
              <input
                type="text"
                defaultValue={selectedChunk.title}
                disabled={approved}
                onBlur={(e) => handleTitleBlur(selectedChunk, e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-300 disabled:bg-slate-50 disabled:text-slate-500"
              />

              {/* Meta row */}
              <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500">
                <span>
                  Halaman {selectedChunk.start_page}–{selectedChunk.end_page}
                </span>
                <span>
                  {(selectedChunk.char_count ?? selectedChunk.content.length).toLocaleString()} karakter
                </span>
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={selectedChunk.is_verified}
                    disabled={approved}
                    onChange={() => handleVerifiedToggle(selectedChunk)}
                    className="h-3.5 w-3.5 accent-blue-600"
                  />
                  <span className={selectedChunk.is_verified ? 'text-green-600' : ''}>
                    Terverifikasi
                  </span>
                </label>
              </div>

              {/* Content textarea */}
              <textarea
                key={selectedChunk.id}
                defaultValue={selectedChunk.content}
                disabled={approved}
                onBlur={(e) => handleContentBlur(selectedChunk, e.target.value)}
                rows={18}
                className="w-full resize-none rounded-lg border border-slate-200 p-3 font-mono text-sm leading-relaxed text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-300 disabled:bg-slate-50 disabled:text-slate-500"
              />
            </div>
          ) : (
            <p className="text-sm text-slate-400">Pilih chunk di sebelah kiri.</p>
          )}
        </div>
      </div>
    </section>
  )
}
