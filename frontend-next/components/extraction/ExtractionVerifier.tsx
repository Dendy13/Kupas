'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ExtractionChunk, ExtractionPreviewData } from '@/types/extraction'

interface Props {
  initialData: ExtractionPreviewData
  bookId: string
}

// Colour-code chunks by size
function chunkSizeClass(chars: number): string {
  if (chars < 500) return 'border-yellow-400 bg-yellow-50'
  if (chars > 15000) return 'border-orange-400 bg-orange-50'
  return 'border-slate-200 bg-white'
}

export function ExtractionVerifier({ initialData, bookId }: Props) {
  const [chunks, setChunks] = useState<ExtractionChunk[]>(
    initialData.chunks.map((c, i) => ({ ...c, id: i }))
  )
  const [selectedId, setSelectedId] = useState<number>(0)
  const [isSaving, setIsSaving] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saved' | 'error'>('idle')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ''

  // -----------------------------------------------------------------------
  // Auto-save with 500 ms debounce
  // -----------------------------------------------------------------------
  const triggerAutoSave = useCallback(
    (updated: ExtractionChunk[]) => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(async () => {
        try {
          await fetch(`${apiUrl}/api/extractions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              book_id: parseInt(bookId),
              chunks: updated,
            }),
          })
          setSaveStatus('saved')
          setTimeout(() => setSaveStatus('idle'), 2000)
        } catch {
          setSaveStatus('error')
        }
      }, 500)
    },
    [apiUrl, bookId]
  )

  // -----------------------------------------------------------------------
  // Keyboard shortcuts
  // -----------------------------------------------------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey
      if (ctrl && e.key === 's') {
        e.preventDefault()
        triggerAutoSave(chunks)
      }
      if (ctrl && e.key === 'm') {
        e.preventDefault()
        handleMergeSmall()
      }
      if (e.key === 'Delete' && document.activeElement?.tagName !== 'TEXTAREA') {
        handleRemove(selectedId)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chunks, selectedId])

  // -----------------------------------------------------------------------
  // Chunk operations
  // -----------------------------------------------------------------------
  const handleContentEdit = (id: number, newContent: string) => {
    const updated = chunks.map((c) =>
      c.id === id
        ? { ...c, content: newContent, char_count: newContent.length, word_count: newContent.split(/\s+/).filter(Boolean).length }
        : c
    )
    setChunks(updated)
    triggerAutoSave(updated)
  }

  const handleTitleEdit = (id: number, newTitle: string) => {
    const updated = chunks.map((c) => (c.id === id ? { ...c, title: newTitle } : c))
    setChunks(updated)
    triggerAutoSave(updated)
  }

  const handleRemove = (id: number) => {
    const updated = chunks.filter((c) => c.id !== id)
    setChunks(updated)
    if (selectedId === id && updated.length > 0) {
      setSelectedId(updated[0].id ?? 0)
    }
    triggerAutoSave(updated)
  }

  /** Merge all chunks below 500 chars into the next sibling */
  const handleMergeSmall = () => {
    const result: ExtractionChunk[] = []
    for (const chunk of chunks) {
      const charCount = chunk.char_count ?? chunk.content.length
      if (result.length > 0 && charCount < 500) {
        const prev = result[result.length - 1]
        const merged = prev.content + '\n\n' + chunk.content
        result[result.length - 1] = {
          ...prev,
          content: merged,
          char_count: merged.length,
          word_count: merged.split(/\s+/).filter(Boolean).length,
          end_page: chunk.end_page,
        }
      } else {
        result.push({ ...chunk })
      }
    }
    setChunks(result)
    triggerAutoSave(result)
  }

  /** Remove exact duplicate content chunks */
  const handleRemoveDuplicates = () => {
    const seen = new Set<string>()
    const result = chunks.filter((c) => {
      const key = c.content.trim()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    setChunks(result)
    triggerAutoSave(result)
  }

  // -----------------------------------------------------------------------
  // Approve & generate
  // -----------------------------------------------------------------------
  const handleApprove = async () => {
    setIsSaving(true)
    try {
      const saveRes = await fetch(`${apiUrl}/api/extractions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_id: parseInt(bookId), chunks }),
      })
      if (!saveRes.ok) throw new Error(`Simpan gagal: HTTP ${saveRes.status}`)
      const session = await saveRes.json()

      const approveRes = await fetch(
        `${apiUrl}/api/extractions/${session.id}/approve`,
        { method: 'POST' }
      )
      if (!approveRes.ok) throw new Error(`Approve gagal: HTTP ${approveRes.status}`)

      setSaveStatus('saved')
      alert('Ekstraksi disetujui! Pipeline generasi AI telah dimulai.')
    } catch (err) {
      setSaveStatus('error')
      alert(`Error: ${String(err)}`)
    } finally {
      setIsSaving(false)
    }
  }

  // -----------------------------------------------------------------------
  // Derived values
  // -----------------------------------------------------------------------
  const stats = initialData.statistics
  const selectedChunk = chunks.find((c) => c.id === selectedId) ?? chunks[0]

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-slate-800">Verifikasi Ekstraksi PDF</h1>
          <p className="text-sm text-slate-500">Buku ID: {bookId}</p>
        </div>
        <div className="flex items-center gap-3">
          {saveStatus === 'saved' && (
            <span className="text-xs text-green-600">✓ Tersimpan</span>
          )}
          {saveStatus === 'error' && (
            <span className="text-xs text-red-600">✗ Gagal menyimpan</span>
          )}
          <button
            onClick={handleMergeSmall}
            className="text-sm px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-100"
          >
            Gabung Chunk Kecil <kbd className="ml-1 text-xs opacity-60">⌘M</kbd>
          </button>
          <button
            onClick={handleRemoveDuplicates}
            className="text-sm px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-100"
          >
            Hapus Duplikat
          </button>
          <button
            onClick={handleApprove}
            disabled={isSaving}
            className="text-sm px-4 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isSaving ? 'Menyimpan…' : 'Setujui & Generate'}
          </button>
        </div>
      </header>

      {/* Warnings */}
      {initialData.warnings.length > 0 && (
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 flex flex-wrap gap-2">
          {initialData.warnings.map((w, i) => (
            <span key={i} className="text-xs text-amber-700 bg-amber-100 px-2 py-1 rounded">
              ⚠ {w}
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-0 h-[calc(100vh-120px)]">
        {/* Left: chunk list */}
        <aside className="border-r border-slate-200 overflow-y-auto bg-white">
          <div className="p-3 border-b border-slate-100 text-xs text-slate-500 font-medium uppercase tracking-wide">
            {chunks.length} Chunk
          </div>
          {chunks.map((chunk, idx) => {
            const charCount = chunk.char_count ?? chunk.content.length
            return (
              <button
                key={chunk.id ?? idx}
                onClick={() => setSelectedId(chunk.id ?? idx)}
                className={`w-full text-left px-4 py-3 border-b border-slate-100 hover:bg-slate-50 transition-colors ${
                  selectedId === (chunk.id ?? idx) ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
                }`}
              >
                <p className="text-sm font-medium text-slate-700 truncate">{chunk.title}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  Hal. {chunk.start_page}–{chunk.end_page} · {charCount.toLocaleString()} karakter
                </p>
                {charCount < 500 && (
                  <span className="inline-block mt-1 text-xs bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded">
                    Terlalu kecil
                  </span>
                )}
                {charCount > 15000 && (
                  <span className="inline-block mt-1 text-xs bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded">
                    Terlalu besar
                  </span>
                )}
              </button>
            )
          })}
        </aside>

        {/* Right: editor */}
        <main className="overflow-y-auto p-6 flex flex-col gap-4">
          {selectedChunk ? (
            <>
              {/* Title edit */}
              <input
                type="text"
                value={selectedChunk.title}
                onChange={(e) => handleTitleEdit(selectedChunk.id ?? 0, e.target.value)}
                className="w-full text-lg font-bold text-slate-800 border border-slate-200 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-300"
              />

              {/* Meta */}
              <div className="flex flex-wrap gap-4 text-sm text-slate-500">
                <span>Halaman {selectedChunk.start_page}–{selectedChunk.end_page}</span>
                <span>{(selectedChunk.char_count ?? selectedChunk.content.length).toLocaleString()} karakter</span>
                <span>{(selectedChunk.word_count ?? selectedChunk.content.split(/\s+/).filter(Boolean).length).toLocaleString()} kata</span>
              </div>

              {/* Content editor */}
              <div
                className={`flex-1 rounded-xl border-2 p-1 ${chunkSizeClass(
                  selectedChunk.char_count ?? selectedChunk.content.length
                )}`}
              >
                <textarea
                  value={selectedChunk.content}
                  onChange={(e) =>
                    handleContentEdit(selectedChunk.id ?? 0, e.target.value)
                  }
                  className="w-full h-[50vh] p-4 text-sm text-slate-700 bg-transparent resize-none focus:outline-none font-mono leading-relaxed"
                />
              </div>

              {/* Actions for this chunk */}
              <div className="flex gap-3">
                <button
                  onClick={() => handleRemove(selectedChunk.id ?? 0)}
                  className="text-sm px-3 py-1.5 rounded-lg border border-red-300 text-red-600 hover:bg-red-50"
                >
                  Hapus Chunk <kbd className="ml-1 text-xs opacity-60">Del</kbd>
                </button>
              </div>
            </>
          ) : (
            <p className="text-slate-400 text-sm">Pilih chunk di sebelah kiri.</p>
          )}

          {/* Statistics dashboard */}
          {stats && (
            <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4 bg-white rounded-xl border border-slate-200 p-4">
              <Stat label="Total Chunk" value={stats.total_chunks} />
              <Stat label="Total Karakter" value={stats.total_chars?.toLocaleString()} />
              <Stat label="Rata-rata Karakter" value={Math.round(stats.avg_chunk_size)?.toLocaleString()} />
              <Stat label="Total Kata" value={stats.total_words?.toLocaleString()} />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number | undefined }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-lg font-bold text-slate-800">{value ?? '—'}</span>
    </div>
  )
}
