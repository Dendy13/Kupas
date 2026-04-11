export interface ExtractionChunk {
  id?: number
  title: string
  content: string
  start_page: number
  end_page: number
  char_count?: number
  word_count?: number
  quality_score?: number
  is_verified: boolean
  order_index?: number
}

export interface ExtractionStatistics {
  total_chunks: number
  total_chars: number
  total_words: number
  avg_chunk_size: number
  min_chunk_size: number
  max_chunk_size: number
  chunks_below_minimum: number
  chunks_above_maximum: number
}

export interface ExtractionPreviewData {
  chunks: ExtractionChunk[]
  statistics: ExtractionStatistics
  warnings: string[]
}

export interface ExtractionSession {
  id: number
  book_id: number
  status: 'draft' | 'in_review' | 'approved' | 'rejected'
  total_pages: number | null
  approved_by: number | null
  chunks: ExtractionChunk[]
}
