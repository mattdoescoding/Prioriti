import { useState } from 'react'
import { DateTime } from 'luxon'
import { api } from './api'
import type { CanvasPreview, CanvasRequest } from './types'
import { formatDateTime, today } from './time'

interface Props {
  disabled: boolean
  onImport: (value: CanvasRequest) => Promise<boolean>
}

export default function CanvasImport({ disabled, onImport }: Props) {
  const [value, setValue] = useState<CanvasRequest>({
    content: '', start_date: today(),
    end_date: DateTime.fromISO(today()).plus({ months: 4 }).toISODate()!, estimated_minutes: 60,
  })
  const [preview, setPreview] = useState<CanvasPreview | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function change(changes: Partial<CanvasRequest>) {
    setValue((current) => ({ ...current, ...changes }))
    setPreview(null)
    setError('')
  }

  async function read(file?: File) {
    change({ content: '' })
    if (!file) return
    if (file.size > 2_000_000) { setError('Choose a calendar file smaller than 2 MB.'); return }
    setBusy(true)
    try { change({ content: await file.text() }) }
    catch { setError('This file could not be read. Try selecting it again.') }
    finally { setBusy(false) }
  }

  async function inspect() {
    setBusy(true)
    setError('')
    setPreview(null)
    try {
      const result = await api.previewCanvas(value)
      setPreview(result)
      setSelected(result.items.filter((item) => !item.duplicate).map((item) => item.source_id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The calendar could not be read.')
    } finally { setBusy(false) }
  }

  const available = preview?.items.filter((item) => !item.duplicate) ?? []

  return (
    <section className="panel">
      <h2>Import from Canvas</h2>
      <p>In Canvas, open Calendar → Calendar Feed → Click to view Calendar Feed. Save the downloaded .ics file, then select it below.</p>
      <p className="hint">Timed events become calendar events; assignment deadlines become tasks. Only meetings included in the file can be imported. This is a file import; download a fresh file to add new entries.</p>
      <form onSubmit={(event) => { event.preventDefault(); void inspect() }}>
        <fieldset disabled={disabled || busy}>
          <label>Canvas calendar file
            <input type="file" accept=".ics,.ical,text/calendar" onChange={(event) => { void read(event.target.files?.[0]) }} required />
          </label>
          <div className="columns">
            <label>Import from<input type="date" value={value.start_date} required onChange={(event) => change({ start_date: event.target.value })} /></label>
            <label>Import through<input type="date" value={value.end_date} required onChange={(event) => change({ end_date: event.target.value })} /></label>
          </div>
          <label>Initial estimate for imported assignments (minutes)
            <input type="number" min="1" step="1" required value={value.estimated_minutes} onChange={(event) => change({ estimated_minutes: Number(event.target.value) })} />
          </label>
          <button type="submit" disabled={!value.content}>{busy ? 'Reading calendar…' : 'Preview import'}</button>
        </fieldset>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {preview && (
        <div>
          <h3>Review entries</h3>
          {preview.warnings.map((warning, index) => <p className="notice" key={index}>{warning}</p>)}
          {!preview.items.length ? <p>No usable entries in this date range.</p> : (
            <>
              <p>{available.length} new entries. Existing entries are skipped, preserving your edits.</p>
              <label className="check-label">
                <input type="checkbox" checked={available.length > 0 && selected.length === available.length} disabled={disabled || !available.length} onChange={(event) => setSelected(event.target.checked ? available.map((item) => item.source_id) : [])} />
                Select all new entries
              </label>
              <ul className="records import-preview">
                {preview.items.map((item) => (
                  <li key={item.source_id}>
                    <label className="check-label">
                      <input type="checkbox" disabled={disabled || item.duplicate} checked={selected.includes(item.source_id)} onChange={(event) => setSelected(event.target.checked ? [...selected, item.source_id] : selected.filter((id) => id !== item.source_id))} />
                      {item.title}
                    </label>
                    <p>{item.kind === 'task' ? 'Assignment due' : 'Class event'}: {formatDateTime(item.deadline ?? item.start!)}{item.end && ` → ${formatDateTime(item.end)}`}</p>
                    {item.duplicate && <span className="badge">Already imported</span>}
                  </li>
                ))}
              </ul>
              <button type="button" disabled={disabled || !selected.length} onClick={() => {
                void onImport({ ...value, selected_ids: selected }).then((saved) => { if (saved) setPreview(null) })
              }}>Import {selected.length} selected entries</button>
            </>
          )}
        </div>
      )}
    </section>
  )
}
