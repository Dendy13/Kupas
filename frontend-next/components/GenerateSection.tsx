'use client'

import { useState } from 'react'
import { generateContent } from '@/lib/api'
import type { GenerateResult } from '@/types'

interface GenerateSectionProps {
  slug: string
}

export default function GenerateSection({ slug }: GenerateSectionProps) {
  const [result, setResult] = useState<GenerateResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleGenerate() {
    setLoading(true)
    setError(null)
    try {
      const data = await generateContent(slug)
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Terjadi kesalahan.')
    } finally {
      setLoading(false)
    }
  }

  if (!result && !loading && !error) {
    return (
      <button
        onClick={handleGenerate}
        className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl transition-colors text-sm flex items-center justify-center gap-2"
      >
        ✨ Kupas dengan AI
      </button>
    )
  }

  if (loading) {
    return (
      <div className="text-center py-10">
        <div className="inline-block w-9 h-9 border-[3px] border-slate-200 border-t-blue-600 rounded-full animate-spin" />
        <p className="mt-3 text-sm text-slate-500">Menganalisis buku dengan AI…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-3">
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-800">
          ⚠️ Gagal memuat konten AI: {error}
        </div>
        <button
          onClick={handleGenerate}
          className="text-sm text-blue-600 hover:underline"
        >
          Coba lagi
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div>
        <h3 className="flex items-center gap-2 text-base font-bold text-slate-800 mb-3">
          <span className="w-1 h-5 bg-blue-600 rounded-full inline-block" />
          Ringkasan
        </h3>
        <div className="bg-sky-50 border border-sky-200 rounded-xl px-4 py-3 text-sm leading-relaxed text-sky-900 whitespace-pre-wrap">
          {result?.summary}
        </div>
      </div>

      {/* Questions */}
      <div>
        <h3 className="flex items-center gap-2 text-base font-bold text-slate-800 mb-3">
          <span className="w-1 h-5 bg-blue-600 rounded-full inline-block" />
          Soal Latihan
        </h3>
        {result?.questions && result.questions.length > 0 ? (
          <ul className="space-y-3">
            {result.questions.map((q, i) => (
              <li
                key={i}
                className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm leading-relaxed text-slate-700"
              >
                <strong>{i + 1}.</strong> {q}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">Tidak ada soal tersedia.</p>
        )}
      </div>

      <button
        onClick={handleGenerate}
        className="text-sm text-blue-600 hover:underline"
      >
        Buat ulang
      </button>
    </div>
  )
}
