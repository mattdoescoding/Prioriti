import { useEffect, useRef, useState } from 'react'
import { DateTime } from 'luxon'
import { Check, ChevronLeft, ChevronRight, CircleCheck, Clock3, LockKeyhole, Plus, Repeat2, Sparkles } from 'lucide-react'
import DatePicker from './DatePicker'
import { layoutDay } from './calendarLayout'
import type { CalendarBlock } from './calendarLayout'
import type { CalendarEvent, Placement, ScheduledTask, ScheduleResult, Task, TaskGroup } from './types'
import { localDateTime, slotAt, today } from './time'

interface Props {
  weekStart: string; schedule: ScheduleResult | null; tasks: Task[]; groups: TaskGroup[]; groupId: string | null; disabled: boolean
  onWeekChange: (date: string) => void; onGenerate: () => void; onAccept: () => void
  onTask: (task: Task, block?: ScheduledTask) => void; onEvent: (event: CalendarEvent) => void
  onError: (message: string) => void; onCreate: (placement?: Placement) => void; onMove: (block: ScheduledTask, placement: Placement) => void
}
const HOUR_HEIGHT = 52

export default function CalendarPage({ weekStart, schedule, tasks, groups, groupId, disabled, onWeekChange, onGenerate, onAccept, onTask, onEvent, onCreate, onMove, onError }: Props) {
  const [view, setView] = useState('week')
  const [showUnscheduled, setShowUnscheduled] = useState(false)
  const scroll = useRef<HTMLDivElement>(null)
  const first = DateTime.fromISO(weekStart)
  const days = Array.from({ length: 7 }, (_, index) => first.plus({ days: index }))
  const visibleTasks = tasks.filter((task) => !groupId || task.group_id === groupId)
  const blocks: CalendarBlock[] = [
    ...(schedule?.events ?? []).map((event) => ({ id: `event-${event.id}`, title: event.title, start: event.start, end: event.end, color: '#8b5fc4', event })),
    ...(schedule?.scheduled ?? []).flatMap((slot) => {
      const task = visibleTasks.find((item) => item.id === slot.task_id)
      return task ? [{ id: slot.id, title: task.title, start: slot.start, end: slot.end, color: groups.find((group) => group.id === task.group_id)?.color ?? '#3568e8', task, slot }] : []
    }),
  ].sort((a, b) => Date.parse(a.start) - Date.parse(b.start))
  const now = localDateTime(new Date().toISOString())
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = 7 * HOUR_HEIGHT }, [weekStart, view])
  const select = (block: CalendarBlock) => block.task ? onTask(block.task, block.slot) : block.event && onEvent(block.event)
  const placementAt = (event: React.MouseEvent | React.DragEvent, day: string): Placement => {
    const minutes = Math.min(23 * 60 + 45, Math.max(0, Math.round((event.clientY - event.currentTarget.getBoundingClientRect().top) / HOUR_HEIGHT * 4) * 15))
    return slotAt(day, minutes)
  }
  return <section className="calendar-workspace" aria-label="Weekly planner">
    <div className="calendar-toolbar"><div className="calendar-navigation"><button className="secondary today-button" type="button" onClick={() => onWeekChange(today())}>Today</button><div className="inline-actions"><button className="icon-button" aria-label="Previous week" onClick={() => onWeekChange(first.minus({ days: 7 }).toISODate()!)}><ChevronLeft size={20} /></button><button className="icon-button" aria-label="Next week" onClick={() => onWeekChange(first.plus({ days: 7 }).toISODate()!)}><ChevronRight size={20} /></button></div><DatePicker value={weekStart} onChange={onWeekChange} /><span className="week-badge">Week {first.weekNumber}</span></div><div className="calendar-tools"><div className="segmented"><button aria-pressed={view === 'week'} onClick={() => setView('week')}>Week</button><button aria-pressed={view === 'agenda'} onClick={() => setView('agenda')}>Agenda</button></div>{Boolean(schedule?.scheduled.length) && <button className="secondary keep-plan" disabled={disabled} onClick={onAccept}><Check size={16} />Keep plan</button>}<button className="primary" type="button" disabled={disabled} onClick={onGenerate}><Sparkles size={16} />Auto-plan</button></div></div>
    {view === 'week' ? <div className="calendar-surface"><div className="week-header"><div className="hour-heading"><Clock3 size={15} /></div>{days.map((day) => <div className={`day-heading ${day.toISODate() === today() ? 'current-day' : ''}`} key={day.toISODate()}><span>{day.toFormat('ccc')}</span><strong>{day.day}</strong></div>)}</div>
      <div className="calendar-body" ref={scroll}><div className="time-grid" style={{ height: 24 * HOUR_HEIGHT }}>
        <div className="hour-labels">{Array.from({ length: 24 }, (_, hour) => <span key={hour} style={{ top: hour * HOUR_HEIGHT }}>{hour === 0 ? '' : DateTime.fromObject({ hour }).toFormat('ha').toLowerCase()}</span>)}</div>
        {days.map((day) => {
          const date = day.toISODate()!
          return <div className={`day-column ${date === today() ? 'current-day' : ''}`} key={date} aria-label={day.toFormat('cccc, LLLL d')} onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
            event.preventDefault(); const id = event.dataTransfer.getData('text/plain'); const block = blocks.find((item) => item.id === id)
            if (block?.slot && !disabled) { try { const placement = placementAt(event, date); placement.end = localDateTime(placement.start).plus({ minutes: block.slot.scheduled_minutes }).toUTC().toISO()!; onMove(block.slot, placement) } catch (reason) { onError(reason instanceof Error ? reason.message : 'Choose another time.') } }
          }} onClick={(event) => { if (!disabled && event.target === event.currentTarget) { try { onCreate(placementAt(event, date)) } catch (reason) { onError(reason instanceof Error ? reason.message : 'Choose another time.') } } }}>
            {Array.from({ length: 24 }, (_, hour) => <div className="grid-hour" key={hour} style={{ top: hour * HOUR_HEIGHT, height: HOUR_HEIGHT }} />)}
            {layoutDay(blocks, date).map((block) => <button key={block.id} type="button" className={`calendar-event ${block.event ? 'fixed-event' : ''} ${block.slot?.status === 'completed' ? 'completed-event' : ''}`} aria-label={block.task ? `Edit task ${block.title}` : `View event ${block.title}`} style={{ top: block.from / 60 * HOUR_HEIGHT + 1, height: Math.max(16, (block.to - block.from) / 60 * HOUR_HEIGHT - 3), left: `calc(${block.lane / block.lanes * 100}% + 3px)`, width: `calc(${100 / block.lanes}% - 7px)`, background: `${block.color}16`, color: block.color, borderLeftColor: block.color }} draggable={Boolean(block.slot) && !disabled} onDragStart={(event) => { event.dataTransfer.setData('text/plain', block.id); event.dataTransfer.effectAllowed = 'move' }} onClick={(event) => { event.stopPropagation(); select(block) }}>
              <span className="event-title">{block.slot?.status === 'completed' && <CircleCheck size={12} />}{block.title}</span>{block.to - block.from >= 45 && <span className="event-time">{localDateTime(block.start).toFormat('h:mm')} – {localDateTime(block.end).toFormat('h:mm a')}{block.slot?.locked ? <LockKeyhole size={11} /> : Boolean(block.task?.repeat_days?.length) && <Repeat2 size={11} />}</span>}
            </button>)}
            {date === today() && <div className="now-line" style={{ top: (now.hour + now.minute / 60) * HOUR_HEIGHT }}><span /></div>}
          </div>
        })}
      </div></div>{!blocks.length && !tasks.length && <div className="calendar-empty"><div className="empty-icon"><Sparkles size={24} /></div><h2>A little space to get started</h2><p>Add a task or import your classes.<br />We’ll help you make time for the rest.</p><button className="secondary" onClick={() => onCreate()} disabled={disabled}><Plus size={16} />Add your first task</button></div>}
    </div> : <div className="agenda-view">{days.map((day) => {
      const entries = blocks.filter((block) => localDateTime(block.start).toISODate() === day.toISODate())
      return <section className="agenda-day" key={day.toISODate()}><div className={`agenda-date ${day.toISODate() === today() ? 'current-day' : ''}`}><strong>{day.day}</strong><span>{day.toFormat('ccc')}</span></div><div className="agenda-entries">{entries.length ? entries.map((block) => <button className="agenda-entry" key={block.id} onClick={() => select(block)}><span className="color-dot" style={{ background: block.color }} /><span className="agenda-time">{localDateTime(block.start).toFormat('h:mm a')} – {localDateTime(block.end).toFormat('h:mm a')}</span><strong>{block.title}</strong>{block.slot?.locked && <LockKeyhole size={14} />}</button>) : <p className="free-day">No plans. A little breathing room.</p>}</div></section>
    })}</div>}
    <div className="calendar-footer"><span><span className="color-dot" style={{ background: '#3568e8' }} />{schedule?.scheduled.length ?? 0} sessions planned</span><span><span className="color-dot" style={{ background: '#8b5fc4' }} />{schedule?.events.length ?? 0} class events</span><span className="footer-tip">Click a task to edit · Drag a session to move it</span>{Boolean(schedule?.unscheduled.length) && <button className="text-button unscheduled-toggle" onClick={() => setShowUnscheduled(!showUnscheduled)}>{schedule!.unscheduled.length} need attention</button>}</div>
    {showUnscheduled && Boolean(schedule?.unscheduled.length) && <div className="unscheduled-tray">{schedule!.unscheduled.map((item, index) => <button key={`${item.task_id}-${index}`} onClick={() => { const task = tasks.find((task) => task.id === item.task_id); if (task) onTask(task) }}><strong>{item.title}</strong><span>{item.reason}</span></button>)}</div>}
    <span className="sr-only">Week beginning {first.toFormat('LLLL d, yyyy')}</span>
  </section>
}
