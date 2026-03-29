export interface Book {
  id: number
  slug: string
  title: string | null
  author: string | null
  subject: string | null
  grade: string | null
  cover_url: string | null
}

export interface BookDetail extends Book {
  chapters: Chapter[]
}

export interface Chapter {
  id: number
  chapter_number: number
  title: string | null
  content: string | null
}

export interface GenerateResult {
  slug: string
  summary: string
  questions: string[]
}
