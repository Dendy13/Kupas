const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api-kupas.dendyfajark.page'
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || ''

const headers = {
  'Content-Type': 'application/json',
  'X-API-Key': API_KEY,
}

export async function getBooks() {
  const res = await fetch(`${API_URL}/books`, { next: { revalidate: 60 }, headers })
  if (!res.ok) throw new Error(`Gagal mengambil daftar buku (${res.status})`)
  return res.json()
}

export async function getBook(slug: string) {
  const res = await fetch(`${API_URL}/books/${slug}`, { next: { revalidate: 60 }, headers })
  if (!res.ok) throw new Error(`Gagal mengambil detail buku (${res.status})`)
  return res.json()
}

export async function generateContent(slug: string) {
  const res = await fetch(`${API_URL}/books/${slug}/generate`, {
    method: 'POST',
    headers,
  })
  if (!res.ok) throw new Error(`Gagal generate konten AI (${res.status})`)
  return res.json()
}

// ---------------------------------------------------------------------------
// Extraction API
// ---------------------------------------------------------------------------

export async function previewExtraction(bookId: number) {
  const res = await fetch(`${API_URL}/api/books/${bookId}/preview-extraction`, {
    method: 'POST',
    headers,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Gagal preview ekstraksi (${res.status})`)
  }
  return res.json()
}

export async function createExtraction(bookId: number) {
  const res = await fetch(`${API_URL}/api/books/${bookId}/extractions`, {
    method: 'POST',
    headers,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Gagal membuat sesi ekstraksi (${res.status})`)
  }
  return res.json()
}

export async function getExtraction(sessionId: number) {
  const res = await fetch(`${API_URL}/api/extractions/${sessionId}`, {
    cache: 'no-store',
    headers,
  })
  if (!res.ok) throw new Error(`Gagal mengambil sesi ekstraksi (${res.status})`)
  return res.json()
}

export async function updateChunk(
  sessionId: number,
  chunkId: number,
  data: { title?: string; content?: string; is_verified?: boolean },
) {
  const res = await fetch(
    `${API_URL}/api/extractions/${sessionId}/chunks/${chunkId}`,
    {
      method: 'PATCH',
      headers,
      body: JSON.stringify(data),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Gagal update chunk (${res.status})`)
  }
  return res.json()
}

export async function mergeChunk(
  sessionId: number,
  chunkId: number,
  targetChunkId: number,
) {
  const res = await fetch(
    `${API_URL}/api/extractions/${sessionId}/chunks/${chunkId}/merge`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ target_chunk_id: targetChunkId }),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Gagal merge chunk (${res.status})`)
  }
  return res.json()
}

export async function splitChunk(
  sessionId: number,
  chunkId: number,
  splitAt: number,
) {
  const res = await fetch(
    `${API_URL}/api/extractions/${sessionId}/chunks/${chunkId}/split`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ split_at: splitAt }),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Gagal split chunk (${res.status})`)
  }
  return res.json()
}

export async function approveExtraction(sessionId: number) {
  const res = await fetch(`${API_URL}/api/extractions/${sessionId}/approve`, {
    method: 'POST',
    headers,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Gagal menyetujui ekstraksi (${res.status})`)
  }
  return res.json()
}
