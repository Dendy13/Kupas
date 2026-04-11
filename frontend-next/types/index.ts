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

export interface ExtractionChunk {
  id: number | null
  session_id: number | null
  title: string | null
  content: string | null
  char_count: number | null
  word_count: number | null
  start_page: number | null
  end_page: number | null
  order_index: number
  is_verified: boolean
  quality_score: number | null
}

export interface ExtractionStatistics {
  total_pages: number
  total_chunks: number
  avg_chunk_size: number
  min_chunk_size: number
  max_chunk_size: number
  total_characters: number
  estimated_reading_time_minutes: number
}

export interface ExtractionPreviewResponse {
  chunks: ExtractionChunk[]
  statistics: ExtractionStatistics
  quality_warnings: string[]
}

export interface ExtractionSession {
  id: number
  book_id: number
  status: string
  total_pages: number | null
  total_chunks: number | null
  approved_by: number | null
  approved_at: string | null
  created_at: string
  updated_at: string
  chunks: ExtractionChunk[]
  statistics: ExtractionStatistics | null
  quality_warnings: string[]
}
