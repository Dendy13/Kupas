import type { Book } from '@/types'
import BookCard from './BookCard'

interface BookGridProps {
  books: Book[]
  loading?: boolean
}

function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl shadow-sm overflow-hidden animate-pulse">
      <div className="w-full aspect-[3/4] bg-slate-200" />
      <div className="p-3.5 flex flex-col gap-2">
        <div className="h-3.5 bg-slate-200 rounded w-5/6" />
        <div className="h-3 bg-slate-200 rounded w-3/4" />
        <div className="h-3 bg-slate-200 rounded w-1/3 mt-1" />
        <div className="h-7 bg-slate-200 rounded mt-3" />
      </div>
    </div>
  )
}

export default function BookGrid({ books, loading = false }: BookGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5">
        {Array.from({ length: 10 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    )
  }

  if (books.length === 0) {
    return (
      <p className="text-center text-slate-500 py-12">
        Tidak ada buku yang cocok dengan filter ini.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5">
      {books.map((book) => (
        <BookCard key={book.id} book={book} />
      ))}
    </div>
  )
}
