import { notFound } from 'next/navigation'
import { ExtractionVerifier } from '@/components/extraction/ExtractionVerifier'
import type { ExtractionPreviewData } from '@/types/extraction'

interface Props {
  params: Promise<{ id: string }>
}

export default async function VerifyExtractionPage({ params }: Props) {
  const { id } = await params

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ''

  let data: ExtractionPreviewData

  try {
    const response = await fetch(
      `${apiUrl}/api/books/${id}/preview-extraction`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // No body needed – book_id comes from the URL path
        cache: 'no-store',
      }
    )

    if (response.status === 404) {
      notFound()
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({}))
      throw new Error(err?.detail ?? `HTTP ${response.status}`)
    }

    data = await response.json()
  } catch (err) {
    return (
      <main className="max-w-4xl mx-auto px-6 py-12">
        <p className="text-red-500">
          Gagal memuat preview ekstraksi: {String(err)}
        </p>
      </main>
    )
  }

  return <ExtractionVerifier initialData={data} bookId={id} />
}
