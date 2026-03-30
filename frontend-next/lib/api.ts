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
