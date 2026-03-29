const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://api.kupas.dendyfajark.page'

export async function getBooks() {
  const res = await fetch(`${API_URL}/books`, { next: { revalidate: 60 } })
  if (!res.ok) throw new Error(`Gagal mengambil daftar buku (${res.status})`)
  return res.json()
}

export async function getBook(slug: string) {
  const res = await fetch(`${API_URL}/books/${slug}`, { next: { revalidate: 60 } })
  if (!res.ok) throw new Error(`Gagal mengambil detail buku (${res.status})`)
  return res.json()
}

export async function generateContent(slug: string) {
  const res = await fetch(`${API_URL}/books/${slug}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) throw new Error(`Gagal generate konten AI (${res.status})`)
  return res.json()
}
