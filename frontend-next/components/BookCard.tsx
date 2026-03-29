import Image from 'next/image'
import Link from 'next/link'
import type { Book } from '@/types'

interface BookCardProps {
  book: Book
}

export default function BookCard({ book }: BookCardProps) {
  return (
    <Link
      href={`/books/${encodeURIComponent(book.slug)}`}
      className="bg-white rounded-xl shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-200 overflow-hidden flex flex-col group"
      aria-label={book.title ?? book.slug}
    >
      {/* Cover */}
      <div className="relative w-full aspect-[3/4] bg-gradient-to-br from-blue-100 to-blue-200 flex items-center justify-center text-5xl shrink-0">
        {book.cover_url ? (
          <Image
            src={book.cover_url}
            alt={book.title ?? book.slug}
            fill
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 200px"
            className="object-cover"
          />
        ) : (
          <span>📚</span>
        )}
      </div>

      {/* Info */}
      <div className="p-3.5 flex flex-col gap-1 flex-1">
        <h2 className="text-sm font-semibold leading-snug line-clamp-2 text-slate-800">
          {book.title ?? book.slug}
        </h2>
        {book.author && (
          <p className="text-xs text-slate-500 truncate">{book.author}</p>
        )}
        {book.grade && (
          <span className="inline-block self-start px-2 py-0.5 rounded bg-blue-100 text-blue-700 text-[0.7rem] font-semibold mt-0.5">
            {book.grade}
          </span>
        )}
        {book.subject && (
          <p className="text-xs text-slate-500">{book.subject}</p>
        )}
        <div className="mt-auto pt-2">
          <span className="block w-full text-center py-1.5 bg-blue-600 group-hover:bg-blue-700 text-white text-xs font-semibold rounded-lg transition-colors">
            ✨ Kupas
          </span>
        </div>
      </div>
    </Link>
  )
}
