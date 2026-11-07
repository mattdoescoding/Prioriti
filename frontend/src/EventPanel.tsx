import { useEffect, useRef, useState } from 'react'
import { CalendarDays, Check, Trash2, X } from 'lucide-react'
import type { CalendarEvent } from './types'
import { formatDateTime, inputDateTime, localToUtc } from './time'
export default function EventPanel({ event, disabled, onSave, onDelete, onClose }: { event: CalendarEvent; disabled: boolean; onSave: (id: string, value: { title: string; start: string; end: string }) => Promise<boolean>; onDelete: (id: string) => Promise<boolean>; onClose: () => void }) {
  const [error, setError] = useState('')
  const panel = useRef<HTMLElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const target = panel.current?.querySelector<HTMLElement>('input') ?? panel.current?.querySelector<HTMLElement>('button')
    target?.focus()
    return () => previous?.focus()
  }, [onClose])
  return <div className="drawer-layer"><button className="drawer-scrim" aria-label="Close event" disabled={disabled} onClick={onClose} /><aside ref={panel} onKeyDown={(event) => {
    if (event.key === 'Escape' && !disabled) { event.preventDefault(); onClose() }
    if (event.key === 'Tab') {
      const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), a[href]') ?? [])
      const first = items[0], last = items.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
  }} className="task-drawer" role="dialog" aria-modal="true" aria-label="Calendar event"><div className="drawer-heading"><span className="eyebrow">{event.class_id ? 'CLASS MEETING' : 'CALENDAR EVENT'}</span><button className="icon-button" aria-label="Close event details" disabled={disabled} onClick={onClose}><X size={20} /></button></div>{event.class_id ? <div className="drawer-fields"><CalendarDays size={25} /><h1>{event.title}</h1><p>{formatDateTime(event.start)}<br />{formatDateTime(event.end)}</p><a className="primary button-link" href="#classes" onClick={onClose}>Manage class series</a></div> : <form onSubmit={(e) => { e.preventDefault(); const data = new FormData(e.currentTarget); try { const value = { title: String(data.get('title')).trim(), start: localToUtc(String(data.get('start'))), end: localToUtc(String(data.get('end'))) }; void onSave(event.id, value).then((saved) => { if (saved) onClose() }) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Check the entered times.') } }}><fieldset className="drawer-fields" disabled={disabled}><label>Title<input name="title" defaultValue={event.title} required maxLength={200} /></label><label>Start<input name="start" type="datetime-local" defaultValue={inputDateTime(event.start)} required /></label><label>End<input name="end" type="datetime-local" defaultValue={inputDateTime(event.end)} required /></label>{error && <p role="alert" className="error">{error}</p>}<div className="drawer-footer"><button className="primary" type="submit"><Check size={16} />Save event</button><button className="icon-button danger" type="button" aria-label="Delete event" onClick={() => { if (window.confirm(`Delete “${event.title}”?`)) void onDelete(event.id).then((saved) => { if (saved) onClose() }) }}><Trash2 size={18} /></button></div></fieldset></form>}</aside></div>
}
