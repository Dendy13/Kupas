'use client'

interface FilterChipsProps {
  gradeFilter: string
  subjectFilter: string
  onGradeChange: (value: string) => void
  onSubjectChange: (value: string) => void
}

const GRADES = ['SD', 'SMP', 'SMA']
const SUBJECTS = [
  { label: 'Matematika', value: 'Matematika' },
  { label: 'IPA', value: 'IPA' },
  { label: 'IPS', value: 'IPS' },
  { label: 'Bhs. Indonesia', value: 'Bahasa Indonesia' },
  { label: 'Bhs. Inggris', value: 'Bahasa Inggris' },
  { label: 'PPKn', value: 'PPKn' },
]

function Chip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3.5 py-1 rounded-full border text-xs font-medium transition-all ${
        active
          ? 'bg-blue-600 border-blue-600 text-white'
          : 'bg-white border-slate-200 text-slate-500 hover:border-blue-500 hover:text-blue-600'
      }`}
    >
      {label}
    </button>
  )
}

export default function FilterChips({
  gradeFilter,
  subjectFilter,
  onGradeChange,
  onSubjectChange,
}: FilterChipsProps) {
  return (
    <div className="flex flex-wrap gap-2 items-center">
      <span className="text-xs font-semibold text-slate-400 mr-1">Jenjang:</span>
      <Chip label="Semua" active={gradeFilter === ''} onClick={() => onGradeChange('')} />
      {GRADES.map((g) => (
        <Chip
          key={g}
          label={g}
          active={gradeFilter === g}
          onClick={() => onGradeChange(g)}
        />
      ))}

      <div className="w-px h-5 bg-slate-200 mx-1" />

      <span className="text-xs font-semibold text-slate-400 mr-1">Mapel:</span>
      <Chip label="Semua" active={subjectFilter === ''} onClick={() => onSubjectChange('')} />
      {SUBJECTS.map((s) => (
        <Chip
          key={s.value}
          label={s.label}
          active={subjectFilter === s.value}
          onClick={() => onSubjectChange(s.value)}
        />
      ))}
    </div>
  )
}
