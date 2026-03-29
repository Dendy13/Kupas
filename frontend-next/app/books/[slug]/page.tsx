import type { Metadata } from 'next'
import Image from 'next/image'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getBook } from '@/lib/api'
import GenerateSection from '@/components/GenerateSection'

interface Props {
  params: { slug: string }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  try {
    const book = await getBook(params.slug)
    return {
      title: `${book.title ?? params.slug} — Kupas`,
      description: `Ringkasan dan soal latihan AI untuk buku "${book.title ?? params.slug}"`,
    }
  } catch {
    return { title: 'Buku — Kupas' }
  }
}

export default async function BookDetailPage({ params }: Props) {
  let book
  try {
    book = await getBook(params.slug)
  } catch (err) {
    const status = err instanceof Error && err.message.includes('404') ? 'not-found' : 'error'
    if (status === 'not-found') notFound()
    return (
      <main className="max-w-3xl mx-auto px-6 py-12">
        <p className="text-red-500">Gagal memuat buku: {String(err)}</p>
      </main>
    )
  }

  return (
    <main className="max-w-3xl mx-auto px-6 py-10 pb-16">
      {/* Back */}
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline mb-8"
      >
        ← Kembali ke katalog
      </Link>

      {/* Book header */}
      <div className="flex gap-6 mb-8">
        <div className="relative w-24 h-32 rounded-xl overflow-hidden bg-gradient-to-br from-blue-100 to-blue-200 flex items-center justify-center text-4xl shrink-0">
          {book.cover_url ? (
            <Image
              src={book.cover_url}
              alt={book.title ?? book.slug}
              fill
              className="object-cover"
            />
          ) : (
            <span>📚</span>
          )}
        </div>
        <div className="flex flex-col gap-1 pt-1">
          <h1 className="text-xl font-bold leading-snug text-slate-800">
            {book.title ?? book.slug}
          </h1>
          {book.author && (
            <p className="text-sm text-slate-500">✍️ {book.author}</p>
          )}
          <p className="text-sm text-slate-500">
            {[book.grade, book.subject].filter(Boolean).join(' · ')}
          </p>
        </div>
      </div>

      {/* Chapters list */}
      {book.chapters && book.chapters.length > 0 && (
        <div className="mb-8">
          <h2 className="text-base font-bold text-slate-700 mb-3">Daftar Bab</h2>
          <ul className="space-y-1.5">
            {book.chapters.map((ch) => (
              <li
                key={ch.id}
                className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-4 py-2"
              >
                <span className="font-medium text-slate-500 mr-2">Bab {ch.chapter_number}.</span>
                {ch.title ?? `Bab ${ch.chapter_number}`}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* AI Generate Section */}
      <div className="border-t border-slate-200 pt-8">
        <GenerateSection slug={book.slug} />
      </div>
    </main>
  )
}
