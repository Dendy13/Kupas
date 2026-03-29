'use client'

interface SearchBarProps {
  value: string
  onChange: (value: string) => void
}

export default function SearchBar({ value, onChange }: SearchBarProps) {
  return (
    <div className="relative max-w-xl mx-auto">
      <svg
        className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 stroke-slate-400 fill-none pointer-events-none"
        viewBox="0 0 24 24"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Cari judul buku, mata pelajaran…"
        autoComplete="off"
        className="w-full pl-11 pr-4 py-3 rounded-full border-none outline-none text-base shadow-lg text-slate-800 placeholder:text-slate-400 bg-white"
      />
    </div>
  )
}
