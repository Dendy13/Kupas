'use client'

import { useState, useMemo } from 'react'
import type { Book } from '@/types'
import SearchBar from '@/components/SearchBar'
import FilterChips from '@/components/FilterChips'
import BookGrid from '@/components/BookGrid'

interface BookCatalogProps {
  books: Book[]
}

export default function BookCatalog({ books }: BookCatalogProps) {
  const [query, setQuery] = useState('')
  const [gradeFilter, setGradeFilter] = useState('')
  const [subjectFilter, setSubjectFilter] = useState('')

  const filtered = useMemo(() => {
    const q = query.toLowerCase()
    return books.filter((b) => {
      const matchQuery =
        !q ||
        (b.title ?? '').toLowerCase().includes(q) ||
        (b.subject ?? '').toLowerCase().includes(q) ||
        (b.author ?? '').toLowerCase().includes(q)
      const matchGrade = !gradeFilter || (b.grade ?? '').includes(gradeFilter)
      const matchSubject =
        !subjectFilter ||
        (b.subject ?? '').toLowerCase().includes(subjectFilter.toLowerCase())
      return matchQuery && matchGrade && matchSubject
    })
  }, [books, query, gradeFilter, subjectFilter])

  return (
    <>
      {/* Hero */}
      <div className="bg-gradient-to-br from-blue-900 via-blue-600 to-sky-400 text-white py-14 px-6 text-center">
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight mb-3">
          Belajar Lebih Cerdas dengan AI 🎓
        </h1>
        <p className="text-base opacity-90 max-w-lg mx-auto mb-8">
          Kupas buku-buku resmi Kemdikdasmen secara instan — dapatkan ringkasan dan soal latihan
          otomatis.
        </p>
        <SearchBar value={query} onChange={setQuery} />
      </div>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-6 py-8 pb-16">
        <div className="mb-7">
          <FilterChips
            gradeFilter={gradeFilter}
            subjectFilter={subjectFilter}
            onGradeChange={setGradeFilter}
            onSubjectChange={setSubjectFilter}
          />
        </div>
        <BookGrid books={filtered} />
      </main>
    </>
  )
}
