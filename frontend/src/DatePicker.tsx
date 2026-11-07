import { useEffect, useRef, useState } from 'react'
import { DateTime } from 'luxon'
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { today, weekOf } from './time'

export function MiniCalendar({ value, onChange, compact = false }: { value: string; onChange: (value: string) => void; compact?: boolean }) {
  const [month, setMonth] = useState(() => DateTime.fromISO(value).startOf('month'))
  const start = month.startOf('week')
  const selected = DateTime.fromISO(value)
  const move = (amount: number) => setMonth((current) => current.plus({ months: amount }))
  return <div className={`mini-calendar ${compact ? 'compact' : ''}`}>
    <div className="mini-heading"><strong>{month.toFormat('MMMM yyyy')}</strong><div className="inline-actions">
      <button className="icon-button" type="button" aria-label="Previous month" onClick={() => move(-1)}><ChevronLeft size={16} /></button>
      <button className="icon-button" type="button" aria-label="Next month" onClick={() => move(1)}><ChevronRight size={16} /></button>
    </div></div>
    <div className="mini-grid">
      {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, i) => <span className="mini-weekday" key={i}>{day}</span>)}
      {Array.from({ length: 42 }, (_, i) => start.plus({ days: i })).map((day) => {
        const date = day.toISODate()!
        const inWeek = weekOf(date) === weekOf(value)
        return <button type="button" key={date} aria-label={day.toFormat('MMMM d, yyyy')} aria-pressed={date === value} className={[day.month !== month.month && 'muted', inWeek && 'in-week', date === value && 'selected', date === today() && 'is-today'].filter(Boolean).join(' ')} onClick={() => onChange(date)}>{day.day}</button>
      })}
    </div>
    {!compact && selected.toISODate() !== today() && <button type="button" className="text-button mini-today" onClick={() => { setMonth(DateTime.fromISO(today()).startOf('month')); onChange(today()) }}>Jump to today</button>}
  </div>
}

export default function DatePicker({ value, onChange }: { value: string; onChange: (date: string) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false) }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', escape) }
  }, [open])
  return <div className="date-picker" ref={ref}>
    <button type="button" className="month-button" aria-label="Choose calendar date" aria-expanded={open} onClick={() => setOpen(!open)}>{DateTime.fromISO(value).toFormat('MMMM yyyy')}<ChevronDown size={17} /></button>
    {open && <div className="date-popover" role="dialog" aria-label="Choose a date"><MiniCalendar value={value} onChange={(date) => { onChange(date); setOpen(false) }} /></div>}
  </div>
}
