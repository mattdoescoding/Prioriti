import { useEffect, useRef, useState } from 'react'
import { DateTime } from 'luxon'
import { AlignLeft, CalendarDays, Check, CircleCheck, Clock3, Folder, LockKeyhole, Repeat2, Trash2, X } from 'lucide-react'
import type { Placement, Priority, ScheduledTask, Task, TaskGroup, TaskInput, TaskStatus } from './types'
import { inputDateTime, localDateTime, localToUtc, today, WEEKDAYS } from './time'

interface Props {
  task: Task | null
  groups: TaskGroup[]
  block?: ScheduledTask
  initialPlacement?: Placement
  initialGroup?: string | null
  disabled: boolean
  onSave: (value: TaskInput, id?: string, placement?: Placement, blockId?: string) => Promise<boolean>
  onDelete: (id: string) => Promise<boolean>
  onStatus: (id: string, status: TaskStatus) => Promise<boolean>
  onComplete: (block: ScheduledTask, minutes?: number) => Promise<boolean>
  onClose: () => void
}
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function TaskPanel({ task, groups, block, initialPlacement, initialGroup, disabled, onSave, onDelete, onStatus, onComplete, onClose }: Props) {
  const [draft, setDraft] = useState({
    title: task?.title ?? '', description: task?.description ?? '', category: task?.category ?? 'General',
    group_id: task ? task.group_id ?? '' : initialGroup ?? '', priority: task?.priority ?? 2,
    estimated_minutes: task?.estimated_minutes ?? 45, sessions_per_day: task?.sessions_per_day ?? 1,
    repeat_days: task?.repeat_days ?? [] as number[],
    deadline: inputDateTime(task?.deadline) || `${DateTime.fromISO(today()).plus({ days: 7 }).toISODate()}T18:00:00`,
    not_before: inputDateTime(task?.not_before),
  })
  const [repeating, setRepeating] = useState(Boolean(task?.repeat_days?.length))
  const [fixed, setFixed] = useState(Boolean(initialPlacement || (block?.status !== 'completed' && block?.locked)))
  const [start, setStart] = useState(inputDateTime(initialPlacement?.start ?? block?.start) || `${today()}T09:00:00`)
  const [actual, setActual] = useState('')
  const [error, setError] = useState('')
  const panel = useRef<HTMLElement>(null)
  const group = groups.find((item) => item.id === draft.group_id)
  const field = <K extends keyof typeof draft>(name: K, value: typeof draft[K]) => setDraft((current) => ({ ...current, [name]: value }))

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    panel.current?.querySelector<HTMLTextAreaElement>('[name=title]')?.focus()
    return () => previous?.focus()
  }, [])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    try {
      const placement = fixed ? { start: localToUtc(start), end: localDateTime(localToUtc(start)).plus({ minutes: Math.ceil(draft.estimated_minutes / 15) * 15 }).toUTC().toISO()! } : undefined
      const saved = await onSave({ ...draft, group_id: draft.group_id || null, priority: draft.priority as Priority,
        repeat_days: repeating ? draft.repeat_days : [], deadline: localToUtc(draft.deadline),
        not_before: draft.not_before ? localToUtc(draft.not_before) : null, status: task?.status ?? 'todo',
      }, task?.id, placement, block?.id)
      if (saved) onClose()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Check your task details.') }
  }

  return <div className="drawer-layer">
    <button className="drawer-scrim" aria-label="Close task editor" onClick={onClose} disabled={disabled} />
    <aside ref={panel} className="task-drawer" role="dialog" aria-modal="true" aria-label={task ? 'Edit task' : 'New task'} onKeyDown={(event) => {
      if (event.key === 'Escape' && !disabled) onClose()
      if (event.key === 'Tab') {
        const elements = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)') ?? [])
        const first = elements[0], last = elements.at(-1)
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }}>
      <div className="drawer-heading"><span className="eyebrow">{task ? 'TASK DETAILS' : 'MAKE TIME FOR IT'}</span><button className="icon-button" type="button" aria-label="Close editor" onClick={onClose} disabled={disabled}><X size={20} /></button></div>
      <form onSubmit={(event) => { void submit(event) }}>
        <fieldset disabled={disabled} className="drawer-fields">
          <label className="title-label"><span className="sr-only">Title</span><textarea className="task-title-input" name="title" aria-label="Title" rows={Math.min(4, Math.max(1, Math.ceil(draft.title.length / 28)))} placeholder="Add a task title" required maxLength={200} value={draft.title} onChange={(event) => field('title', event.target.value)} /></label>
          <div className="task-subtitle"><span className="color-dot" style={{ background: group?.color ?? '#3568e8' }} />{group?.title ?? 'Personal task'}{task?.source_id && <span className="tag">Canvas</span>}</div>
          <div className="editor-section"><div className="section-icon"><AlignLeft size={18} /></div><label>Description<textarea aria-label="Description" placeholder="Notes, links, or a little more context…" rows={4} maxLength={5000} value={draft.description} onChange={(event) => field('description', event.target.value)} /></label></div>
          <div className="editor-section"><div className="section-icon"><Folder size={18} /></div><div className="field-pair">
            <label>Group<select aria-label="Group" value={draft.group_id} onChange={(event) => field('group_id', event.target.value)}><option value="">No group</option>{groups.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
            <label>Category<input value={draft.category} required maxLength={80} onChange={(event) => field('category', event.target.value)} /></label>
          </div></div>
          <div className="editor-section"><div className="section-icon"><Clock3 size={18} /></div><div className="field-pair">
            <label>Estimated minutes<input type="number" min="1" max="1440" required value={draft.estimated_minutes} onChange={(event) => field('estimated_minutes', Number(event.target.value))} /></label>
            <label>Priority<select aria-label="Priority" value={draft.priority} onChange={(event) => field('priority', Number(event.target.value) as Priority)}><option value="1">Low</option><option value="2">Normal</option><option value="3">High</option></select></label>
          </div></div>
          <div className="editor-section"><div className="section-icon"><CalendarDays size={18} /></div><div className="stack-fields">
            <span className="field-heading">Finish by</span><div className="field-pair"><label><span className="sr-only">Deadline date</span><input type="date" aria-label="Deadline date" required value={draft.deadline.slice(0, 10)} onChange={(event) => field('deadline', `${event.target.value}T${draft.deadline.slice(11) || '18:00:00'}`)} /></label><label><span className="sr-only">Deadline time</span><input type="time" aria-label="Deadline time" required value={draft.deadline.slice(11, 16)} onChange={(event) => field('deadline', `${draft.deadline.slice(0, 10)}T${event.target.value}:00`)} /></label></div>
            <span className="field-heading">Available from <small>optional</small></span><div className="field-pair"><input type="date" aria-label="Available from date" value={draft.not_before.slice(0, 10)} onChange={(event) => field('not_before', event.target.value ? `${event.target.value}T${draft.not_before.slice(11) || '09:00:00'}` : '')} /><input type="time" aria-label="Available from time" value={draft.not_before.slice(11, 16)} onChange={(event) => field('not_before', `${draft.not_before.slice(0, 10) || today()}T${event.target.value}:00`)} /></div>
          </div></div>
          <div className="editor-section"><div className="section-icon"><Repeat2 size={18} /></div><div className="stack-fields"><label className="toggle-label"><input type="checkbox" checked={repeating} onChange={(event) => { setRepeating(event.target.checked); if (!draft.repeat_days.length) field('repeat_days', [DateTime.fromISO(today()).weekday - 1]) }} />Repeat weekly</label>
            {repeating && <><div className="weekday-buttons">{WEEKDAYS.map((day, index) => <button type="button" key={day} aria-label={DAY_NAMES[index]} aria-pressed={draft.repeat_days.includes(index)} onClick={() => field('repeat_days', draft.repeat_days.includes(index) ? draft.repeat_days.filter((item) => item !== index) : [...draft.repeat_days, index].sort())}>{day.slice(0, 1)}</button>)}</div><label>Sessions per day<input type="number" min="1" max="12" required value={draft.sessions_per_day} onChange={(event) => field('sessions_per_day', Number(event.target.value))} /></label><p className="field-help">Each session uses the estimate above. Your group’s daily limit still applies.</p></>}
          </div></div>
          <div className="editor-section"><div className="section-icon"><LockKeyhole size={18} /></div><div className="stack-fields"><label className="toggle-label"><input type="checkbox" disabled={block?.status === 'completed'} checked={fixed} onChange={(event) => setFixed(event.target.checked)} />Place at a specific time</label>{block?.status === 'completed' && <p className="field-help">Reopen this session before moving it.</p>}{fixed && <><input aria-label="Scheduled start" type="datetime-local" required value={start.slice(0, 16)} onChange={(event) => setStart(`${event.target.value}:00`)} /><p className="field-help">This session stays in place when you auto-plan. Adjustments help Prioriti learn your preferences.</p></>}</div></div>
          {error && <p role="alert" className="error">{error}</p>}
          <div className="drawer-footer"><button className="primary" type="submit"><Check size={17} />{task ? 'Save changes' : 'Create task'}</button>{task && <button type="button" className="icon-button danger" aria-label="Delete task" onClick={() => { if (window.confirm(`Delete “${task.title}”?`)) void onDelete(task.id).then((saved) => { if (saved) onClose() }) }}><Trash2 size={18} /></button>}</div>
          {task && <div className="completion-section">{block && <label>Actual minutes (optional)<input type="number" min="1" value={actual} onChange={(event) => setActual(event.target.value)} /></label>}<button type="button" className="secondary full-width" onClick={() => { void (block ? onComplete(block, actual ? Number(actual) : undefined) : onStatus(task.id, task.status === 'todo' ? 'completed' : 'todo')).then((saved) => { if (saved) onClose() }) }}><CircleCheck size={17} />{(block?.status === 'completed' || (!block && task.status === 'completed')) ? 'Reopen task' : block ? 'Complete this session' : 'Mark complete'}</button></div>}
        </fieldset>
      </form>
    </aside>
  </div>
}
