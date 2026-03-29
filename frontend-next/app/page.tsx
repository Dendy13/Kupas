import { getBooks } from '@/lib/api'
import type { Book } from '@/types'
import BookCatalog from '@/components/BookCatalog'

export default async function HomePage() {
  let books: Book[] = []
  let error: string | null = null

  try {
    books = await getBooks()
  } catch (err) {
    error = err instanceof Error ? err.message : 'Gagal memuat daftar buku.'
  }

  if (error) {
    return (
      <>
        <div className="bg-gradient-to-br from-blue-900 via-blue-600 to-sky-400 text-white py-14 px-6 text-center">
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight mb-3">
            Belajar Lebih Cerdas dengan AI 🎓
          </h1>
          <p className="text-base opacity-90 max-w-lg mx-auto">
            Kupas buku-buku resmi Kemdikdasmen secara instan — dapatkan ringkasan dan soal latihan
            otomatis.
          </p>
        </div>
        <main className="max-w-6xl mx-auto px-6 py-12">
          <p className="text-center text-red-500">Gagal memuat buku: {error}</p>
        </main>
      </>
    )
  }

  return <BookCatalog books={books} />
}
