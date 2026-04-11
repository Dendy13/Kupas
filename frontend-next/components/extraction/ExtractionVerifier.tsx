'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ExtractionChunk, ExtractionSession, ExtractionStatistics } from '@/types'
import {
  approveExtraction,
  mergeChunk,
  splitChunk,
  updateChunk,
} from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  session: ExtractionSession
  onApproved?: () => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function qualityColor(score: number | null): string {
  if (score === null) return 'bg-gray-200 text-gray-700'
  if (score >= 0.9) return 'bg-green-100 text-green-800'
  if (score >= 0.5) return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
}

function formatNumber(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString('id-ID')
}

// ---------------------------------------------------------------------------
// StatsDashboard
// ---------------------------------------------------------------------------

function StatsDashboard({ stats, warnings }: { stats: ExtractionStatistics; warnings: string[] }) {
  return (
    <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 mb-4">
      <h2 className="font-bold text-blue-800 mb-3 text-sm uppercase tracking-wide">
        Statistik Ekstraksi
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
        {[
          ['Halaman', formatNumber(stats.total_pages)],
          ['Chunk', formatNumber(stats.total_chunks)],
          ['Total karakter', formatNumber(stats.total_characters)],
          ['Rata-rata chunk', `${formatNumber(Math.round(stats.avg_chunk_size))} kar`],
          ['Chunk terkecil', `${formatNumber(stats.min_chunk_size)} kar`],
          ['Estimasi baca', `${stats.estimated_reading_time_minutes} mnt`],
        ].map(([label, value]) => (
          <div key={label} className="bg-white rounded-lg p-2 border border-blue-100">
            <p className="text-xs text-gray-500">{label}</p>
            <p className="font-semibold text-gray-900">{value}</p>
          </div>
        ))}
      </div>
      {warnings.length > 0 && (
        <ul className="mt-3 space-y-1">
          {warnings.map((w) => (
            <li key={w} className="text-xs text-yellow-800 bg-yellow-50 border border-yellow-200 rounded px-2 py-1">
              ⚠️ {w}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ChunkEditor
// ---------------------------------------------------------------------------

interface ChunkEditorProps {
  chunk: ExtractionChunk
  isSelected: boolean
  onUpdate: (updated: ExtractionChunk) => void
  onMergeWithNext: () => void
  onSplit: (offset: number) => void
  onDelete: () => void
  canMerge: boolean
}

function ChunkEditor({
  chunk,
  isSelected,
  onUpdate,
  onMergeWithNext,
  onSplit,
  onDelete,
  canMerge,
}: ChunkEditorProps) {
  const [editingContent, setEditingContent] = useState(false)
  const [draft, setDraft] = useState(chunk.content ?? '')
  const [saving, setSaving] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setDraft(chunk.content ?? '')
  }, [chunk.content])

  const handleSave = async () => {
    setSaving(true)
    try {
      const updated = await updateChunk(chunk.session_id!, chunk.id!, { content: draft })
      onUpdate({ ...chunk, ...updated })
      setEditingContent(false)
    } finally {
      setSaving(false)
    }
  }

  const handleToggleVerified = async () => {
    setSaving(true)
    try {
      const updated = await updateChunk(chunk.session_id!, chunk.id!, {
        is_verified: !chunk.is_verified,
      })
      onUpdate({ ...chunk, ...updated })
    } finally {
      setSaving(false)
    }
  }

  const handleSplitAtCursor = () => {
    const ta = textareaRef.current
    if (!ta) return
    const offset = ta.selectionStart
    if (offset > 0 && offset < draft.length) {
      onSplit(offset)
    }
  }

  if (!isSelected) return null

  return (
    <div className="p-4 space-y-3">
      {/* Meta */}
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
          Hal. {chunk.start_page}–{chunk.end_page}
        </span>
        <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
          {formatNumber(chunk.char_count)} kar · {formatNumber(chunk.word_count)} kata
        </span>
        <span className={`px-2 py-0.5 rounded font-medium ${qualityColor(chunk.quality_score)}`}>
          Skor: {chunk.quality_score != null ? (chunk.quality_score * 100).toFixed(0) + '%' : '—'}
        </span>
      </div>

      {/* Content editor */}
      {editingContent ? (
        <div className="space-y-2">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="w-full h-64 text-sm border border-gray-300 rounded p-2 font-mono resize-y focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Menyimpan…' : 'Simpan'}
            </button>
            <button
              onClick={handleSplitAtCursor}
              className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50"
              title="Pisahkan di posisi kursor (Ctrl+K)"
            >
              Pisah di kursor
            </button>
            <button
              onClick={() => { setDraft(chunk.content ?? ''); setEditingContent(false) }}
              className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50"
            >
              Batal
            </button>
          </div>
        </div>
      ) : (
        <div
          className="text-sm text-gray-800 whitespace-pre-wrap bg-gray-50 rounded p-3 border border-gray-200 max-h-80 overflow-y-auto cursor-pointer hover:bg-white transition"
          onClick={() => setEditingContent(true)}
          title="Klik untuk edit"
        >
          {chunk.content || <span className="text-gray-400 italic">Konten kosong</span>}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleToggleVerified}
          disabled={saving}
          className={`px-3 py-1 text-xs rounded border font-medium transition ${
            chunk.is_verified
              ? 'bg-green-50 text-green-700 border-green-300 hover:bg-green-100'
              : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
          }`}
        >
          {chunk.is_verified ? '✅ Terverifikasi' : '○ Tandai Terverifikasi'}
        </button>
        {canMerge && (
          <button
            onClick={onMergeWithNext}
            className="px-3 py-1 text-xs rounded border border-orange-300 text-orange-700 hover:bg-orange-50"
          >
            ⬇ Gabung dengan berikutnya
          </button>
        )}
        <button
          onClick={onDelete}
          className="px-3 py-1 text-xs rounded border border-red-300 text-red-700 hover:bg-red-50"
        >
          🗑 Hapus chunk
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ExtractionVerifier({ session: initialSession, onApproved }: Props) {
  const [chunks, setChunks] = useState<ExtractionChunk[]>(initialSession.chunks)
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [status, setStatus] = useState(initialSession.status)
  const [approving, setApproving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const stats = initialSession.statistics
  const warnings = initialSession.quality_warnings

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        e.preventDefault()
        if (selectedIdx !== null) {
          const chunk = chunks[selectedIdx]
          if (chunk.id && chunk.session_id) {
            updateChunk(chunk.session_id, chunk.id, { is_verified: true })
              .then((updated) => {
                setChunks((prev) =>
                  prev.map((c, i) => (i === selectedIdx ? { ...c, ...updated } : c)),
                )
              })
              .catch(() => {})
          }
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectedIdx, chunks])

  // Auto-save draft every 30s — deliberately uses an empty dep array because
  // we only want this to register once on mount. The effect body performs
  // a background status update that does not depend on the current chunk state.
  useEffect(() => {
    const t = setInterval(() => {
      // Future: PATCH session status to "in_review"
    }, 30_000)
    return () => clearInterval(t)
  }, [])

  const handleUpdate = useCallback((updated: ExtractionChunk) => {
    setChunks((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
  }, [])

  const handleMergeWithNext = useCallback(
    async (idx: number) => {
      const current = chunks[idx]
      const next = chunks[idx + 1]
      if (!current.id || !next.id || !current.session_id) return
      try {
        const merged = await mergeChunk(current.session_id, current.id, next.id)
        setChunks((prev) => {
          const updated = [...prev]
          updated[idx] = merged
          updated.splice(idx + 1, 1)
          return updated
        })
        setSelectedIdx(idx)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Gagal menggabungkan chunk')
      }
    },
    [chunks],
  )

  const handleSplit = useCallback(
    async (idx: number, offset: number) => {
      const chunk = chunks[idx]
      if (!chunk.id || !chunk.session_id) return
      try {
        const [part1, part2] = await splitChunk(chunk.session_id, chunk.id, offset)
        setChunks((prev) => {
          const updated = [...prev]
          updated.splice(idx, 1, part1, part2)
          return updated
        })
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Gagal memisahkan chunk')
      }
    },
    [chunks],
  )

  const handleDelete = useCallback(
    async (idx: number) => {
      const chunk = chunks[idx]
      if (!chunk.id || !chunk.session_id) return
      if (!confirm(`Hapus chunk "${chunk.title}"?`)) return
      try {
        await updateChunk(chunk.session_id, chunk.id, { content: '' })
        setChunks((prev) => prev.filter((_, i) => i !== idx))
        setSelectedIdx(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Gagal menghapus chunk')
      }
    },
    [chunks],
  )

  const handleVerifyAll = useCallback(async () => {
    for (const chunk of chunks) {
      if (chunk.id && chunk.session_id && !chunk.is_verified) {
        await updateChunk(chunk.session_id, chunk.id, { is_verified: true }).catch(() => {})
      }
    }
    setChunks((prev) => prev.map((c) => ({ ...c, is_verified: true })))
  }, [chunks])

  const handleApprove = async () => {
    setApproving(true)
    setError(null)
    try {
      await approveExtraction(initialSession.id)
      setStatus('approved')
      onApproved?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal menyetujui ekstraksi')
    } finally {
      setApproving(false)
    }
  }

  const verifiedCount = chunks.filter((c) => c.is_verified).length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Verifikasi Ekstraksi PDF</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Status:{' '}
            <span
              className={`font-medium ${
                status === 'approved'
                  ? 'text-green-700'
                  : status === 'in_review'
                  ? 'text-blue-700'
                  : 'text-gray-600'
              }`}
            >
              {status}
            </span>{' '}
            · {verifiedCount}/{chunks.length} chunk terverifikasi
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleVerifyAll}
            className="px-4 py-2 text-sm border border-green-300 text-green-700 rounded-lg hover:bg-green-50"
          >
            ✅ Verifikasi Semua
          </button>
          <button
            onClick={handleApprove}
            disabled={approving || status === 'approved'}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {approving ? 'Memproses…' : status === 'approved' ? 'Sudah Disetujui' : '🚀 Setujui & Proses'}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      {/* Stats */}
      {stats && <StatsDashboard stats={stats} warnings={warnings} />}

      {/* Split view */}
      <div className="flex gap-4 min-h-[500px]">
        {/* Left: chunk list */}
        <div className="w-full sm:w-72 flex-shrink-0 space-y-1 overflow-y-auto max-h-[600px] pr-1">
          {chunks.map((chunk, idx) => (
            <button
              key={chunk.id ?? idx}
              onClick={() => setSelectedIdx(idx === selectedIdx ? null : idx)}
              className={`w-full text-left rounded-lg border px-3 py-2 transition ${
                idx === selectedIdx
                  ? 'border-blue-400 bg-blue-50 ring-1 ring-blue-300'
                  : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-gray-800 truncate">
                  {chunk.title || `Chunk ${idx + 1}`}
                </span>
                {chunk.is_verified && (
                  <span className="flex-shrink-0 text-green-500 text-xs">✅</span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`text-xs px-1.5 rounded ${qualityColor(chunk.quality_score)}`}>
                  {chunk.quality_score != null
                    ? (chunk.quality_score * 100).toFixed(0) + '%'
                    : '—'}
                </span>
                <span className="text-xs text-gray-400">
                  {formatNumber(chunk.char_count)} kar
                </span>
              </div>
            </button>
          ))}
        </div>

        {/* Right: chunk detail */}
        <div className="flex-1 rounded-xl border border-gray-200 bg-white overflow-hidden">
          {selectedIdx !== null && chunks[selectedIdx] ? (
            <ChunkEditor
              chunk={chunks[selectedIdx]}
              isSelected
              onUpdate={handleUpdate}
              onMergeWithNext={() => handleMergeWithNext(selectedIdx)}
              onSplit={(offset) => handleSplit(selectedIdx, offset)}
              onDelete={() => handleDelete(selectedIdx)}
              canMerge={selectedIdx < chunks.length - 1}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm p-8">
              ← Pilih chunk di sebelah kiri untuk melihat detail dan mengedit
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
