'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createExtraction, getExtraction, previewExtraction } from '@/lib/api'
import type { ExtractionPreviewResponse, ExtractionSession } from '@/types'
import ExtractionVerifier from '@/components/extraction/ExtractionVerifier'

interface PageProps {
  params: { id: string }
}

type ViewState = 'idle' | 'previewing' | 'preview_done' | 'loading_session' | 'session_loaded' | 'error'

export default function VerifyExtractionPage({ params }: PageProps) {
  const bookId = parseInt(params.id, 10)
  const router = useRouter()

  const [viewState, setViewState] = useState<ViewState>('idle')
  const [preview, setPreview] = useState<ExtractionPreviewResponse | null>(null)
  const [session, setSession] = useState<ExtractionSession | null>(null)
  const [sessionId, setSessionId] = useState<string>('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const loadSession = useCallback(async (sid: number) => {
    setViewState('loading_session')
    setErrorMsg(null)
    try {
      const result: ExtractionSession = await getExtraction(sid)
      setSession(result)
      setViewState('session_loaded')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Gagal memuat sesi ekstraksi.')
      setViewState('error')
    }
  }, [])

  // Allow loading an existing session by ID from query string
  useEffect(() => {
    const qp = new URLSearchParams(window.location.search)
    const sid = qp.get('session')
    if (sid) {
      setSessionId(sid)
      loadSession(parseInt(sid, 10))
    }
  }, [loadSession])

  async function handlePreview() {
    setViewState('previewing')
    setErrorMsg(null)
    try {
      const result = await previewExtraction(bookId)
      setPreview(result)
      setViewState('preview_done')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Terjadi kesalahan saat preview.')
      setViewState('error')
    }
  }

  async function handleCreateSession() {
    setViewState('previewing')
    setErrorMsg(null)
    try {
      const result: ExtractionSession = await createExtraction(bookId)
      setSession(result)
      setViewState('session_loaded')
      // Update URL for bookmarking
      window.history.replaceState(null, '', `?session=${result.id}`)
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Gagal membuat sesi ekstraksi.')
      setViewState('error')
    }
  }

  function handleLoadSession() {
    const sid = parseInt(sessionId, 10)
    if (!isNaN(sid) && sid > 0) {
      loadSession(sid)
    }
  }

  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-500 mb-6">
        <button onClick={() => router.back()} className="hover:underline">
          ← Kembali
        </button>
        <span className="mx-2">/</span>
        <span>Verifikasi Ekstraksi — Buku #{bookId}</span>
      </nav>

      {/* Error banner */}
      {errorMsg && (
        <div className="mb-6 bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-3 text-sm">
          <strong>Error:</strong> {errorMsg}
        </div>
      )}

      {/* Idle: action selection */}
      {(viewState === 'idle' || viewState === 'error') && (
        <div className="space-y-6">
          <h1 className="text-2xl font-bold text-gray-900">Verifikasi Ekstraksi PDF</h1>
          <p className="text-gray-600">
            Ekstrak teks dari PDF buku, review hasilnya, dan setujui untuk mulai
            generate materi pembelajaran AI.
          </p>

          <div className="grid sm:grid-cols-3 gap-4">
            {/* Preview only */}
            <div className="rounded-xl border border-gray-200 p-5 space-y-3">
              <h2 className="font-semibold text-gray-900">🔍 Preview Ekstraksi</h2>
              <p className="text-sm text-gray-500">
                Jalankan ekstraksi dan lihat hasilnya tanpa menyimpan ke database.
              </p>
              <button
                onClick={handlePreview}
                className="w-full py-2 px-4 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition font-medium"
              >
                Preview
              </button>
            </div>

            {/* Create new session */}
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-5 space-y-3">
              <h2 className="font-semibold text-gray-900">⚡ Ekstrak &amp; Simpan</h2>
              <p className="text-sm text-gray-500">
                Jalankan ekstraksi dan simpan sesi baru ke database untuk diedit.
              </p>
              <button
                onClick={handleCreateSession}
                className="w-full py-2 px-4 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition font-medium"
              >
                Mulai Ekstraksi
              </button>
            </div>

            {/* Load existing session */}
            <div className="rounded-xl border border-gray-200 p-5 space-y-3">
              <h2 className="font-semibold text-gray-900">📂 Buka Sesi Tersimpan</h2>
              <p className="text-sm text-gray-500">Masukkan ID sesi ekstraksi yang sudah ada.</p>
              <div className="flex gap-2">
                <input
                  type="number"
                  placeholder="Session ID"
                  value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}
                  className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                <button
                  onClick={handleLoadSession}
                  disabled={!sessionId}
                  className="px-4 py-2 text-sm bg-gray-800 text-white rounded-lg hover:bg-gray-900 disabled:opacity-50"
                >
                  Buka
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Loading states */}
      {(viewState === 'previewing' || viewState === 'loading_session') && (
        <div className="flex flex-col items-center justify-center py-24 space-y-4">
          <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-600">
            {viewState === 'previewing' ? 'Sedang mengekstrak PDF…' : 'Memuat sesi…'}
          </p>
        </div>
      )}

      {/* Preview result (read-only) */}
      {viewState === 'preview_done' && preview && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">Hasil Preview Ekstraksi</h1>
            <div className="flex gap-2">
              <button
                onClick={() => setViewState('idle')}
                className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Ulangi
              </button>
              <button
                onClick={handleCreateSession}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Simpan Sesi untuk Edit
              </button>
            </div>
          </div>

          {/* Warnings */}
          {preview.quality_warnings.length > 0 && (
            <ul className="space-y-1">
              {preview.quality_warnings.map((w) => (
                <li key={w} className="text-sm text-yellow-800 bg-yellow-50 border border-yellow-200 rounded px-3 py-1">
                  ⚠️ {w}
                </li>
              ))}
            </ul>
          )}

          {/* Stats mini */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            {[
              ['Halaman', preview.statistics.total_pages],
              ['Chunk', preview.statistics.total_chunks],
              ['Total karakter', preview.statistics.total_characters.toLocaleString('id-ID')],
              ['Estimasi baca', `${preview.statistics.estimated_reading_time_minutes} mnt`],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-lg border border-gray-200 p-3 bg-gray-50">
                <p className="text-xs text-gray-500">{label}</p>
                <p className="font-semibold text-gray-900">{value}</p>
              </div>
            ))}
          </div>

          {/* Chunk list */}
          <div className="space-y-3">
            {preview.chunks.map((chunk, idx) => (
              <div key={idx} className="rounded-xl border border-gray-200 bg-white overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50">
                  <span className="font-medium text-gray-800 text-sm">
                    {chunk.title || `Chunk ${idx + 1}`}
                  </span>
                  <div className="flex gap-2 text-xs text-gray-500">
                    <span>Hal. {chunk.start_page}–{chunk.end_page}</span>
                    <span>{chunk.char_count?.toLocaleString('id-ID')} kar</span>
                  </div>
                </div>
                <div className="px-4 py-3 text-sm text-gray-700 max-h-40 overflow-y-auto whitespace-pre-wrap">
                  {chunk.content?.slice(0, 600)}
                  {(chunk.content?.length ?? 0) > 600 && (
                    <span className="text-gray-400"> …(dipotong)</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Session editor */}
      {viewState === 'session_loaded' && session && (
        <ExtractionVerifier
          session={session}
          onApproved={() => {
            setTimeout(() => router.back(), 1500)
          }}
        />
      )}
    </main>
  )
}
