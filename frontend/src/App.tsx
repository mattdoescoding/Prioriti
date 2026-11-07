import { useCallback, useEffect, useRef, useState } from 'react'
import { DateTime } from 'luxon'
import { CalendarDays, Check, ChevronRight, Folder, GraduationCap, ListTodo, Menu, Plus, RefreshCw, SlidersHorizontal, Sparkles, X } from 'lucide-react'
import { api } from './api'
import { MiniCalendar } from './DatePicker'
import { localDateTime, today, weekOf } from './time'
import type { Availability, CalendarEvent, CanvasRequest, ClassInput, ClassSeries, LearningStatus, Placement, ScheduledTask, ScheduleResult, Task, TaskGroup, TaskGroupInput, TaskInput, TaskStatus } from './types'
import CalendarPage from './CalendarPage'
import ClassesPage from './ClassesPage'
import TasksPage from './TasksPage'
import AvailabilityPage from './AvailabilityPage'
import CanvasImport from './CanvasImport'
import TaskPanel from './TaskPanel'
import GroupsPage from './GroupsPage'
import EventPanel from './EventPanel'
import './App.css'

type Page = 'calendar' | 'tasks' | 'groups' | 'classes' | 'availability'
const NAV = [{ id: 'calendar', title: 'Calendar', icon: CalendarDays }, { id: 'tasks', title: 'Tasks', icon: ListTodo }, { id: 'classes', title: 'Classes & Canvas', icon: GraduationCap }, { id: 'availability', title: 'Availability', icon: SlidersHorizontal }] as const
const readPage = (): Page => ['tasks', 'groups', 'classes', 'availability'].find((item) => window.location.hash === `#${item}`) as Page ?? 'calendar'
const readRecords = (week: string) => Promise.all([api.getTasks(), api.getGroups(), api.getClasses(), api.getAvailability(), api.getSchedule(week), api.getLearning()])
const errorText = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Try again.'
interface Editor { id: string | null; blockId?: string; block?: ScheduledTask; placement?: Placement }

export default function App() {
  const [page, setPage] = useState<Page>(readPage)
  const [tasks, setTasks] = useState<Task[]>([])
  const [groups, setGroups] = useState<TaskGroup[]>([])
  const [classes, setClasses] = useState<ClassSeries[]>([])
  const [availability, setAvailability] = useState<Availability>({ windows: [] })
  const [schedule, setSchedule] = useState<ScheduleResult | null>(null)
  const [learning, setLearning] = useState<LearningStatus>({ samples: 0, trained_at: null, method: '' })
  const [weekStart, setWeekStart] = useState(() => weekOf(today()))
  const [groupId, setGroupId] = useState<string | null>(null)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [version, setVersion] = useState(0)
  const inFlight = useRef(true)
  const applyRecords = useCallback(([savedTasks, savedGroups, savedClasses, savedAvailability, savedSchedule, savedLearning]: Awaited<ReturnType<typeof readRecords>>) => {
    setTasks(savedTasks); setGroups(savedGroups); setClasses(savedClasses); setAvailability(savedAvailability); setSchedule(savedSchedule); setLearning(savedLearning); setLoaded(true)
  }, [])

  useEffect(() => {
    const navigate = () => { setPage(readPage()); setSidebarOpen(false) }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  useEffect(() => {
    let active = true
    readRecords(weekStart).then((records) => { if (active) applyRecords(records) }).catch((reason: unknown) => { if (active) setError(errorText(reason)) }).finally(() => { if (active) { inFlight.current = false; setPending(false) } })
    return () => { active = false }
  }, [weekStart, applyRecords])
  useEffect(() => {
    if (!message) return
    const timeout = window.setTimeout(() => setMessage(''), 4500)
    return () => window.clearTimeout(timeout)
  }, [message])

  async function perform(action: () => Promise<unknown>, success: string) {
    if (inFlight.current) return false
    inFlight.current = true; setPending(true); setError(''); setMessage('')
    try {
      await action(); applyRecords(await readRecords(weekStart)); setVersion((value) => value + 1); setMessage(success); return true
    } catch (reason) {
      setError(errorText(reason))
      try { applyRecords(await readRecords(weekStart)) } catch { /* Keep the original error visible. */ }
      return false
    } finally { inFlight.current = false; setPending(false) }
  }
  const createTask = (placement?: Placement) => { setEditor({ id: null, placement }); setSidebarOpen(false) }
  const openTask = (task: Task, block?: ScheduledTask) => setEditor({ id: task.id, blockId: block?.id, block })
  const disabled = pending || !loaded
  const editTask = editor?.id ? tasks.find((task) => task.id === editor.id) : null
  const editBlock = editor?.blockId ? schedule?.scheduled.find((block) => block.id === editor.blockId) ?? editor.block : undefined

  async function saveTask(value: TaskInput, id?: string, placement?: Placement, blockId?: string) {
    let saved: Task | undefined
    const original = schedule?.scheduled.find((block) => block.id === blockId) ?? (editor?.blockId === blockId ? editor?.block : undefined)
    const success = await perform(async () => {
      saved = await api.saveTask(value, id)
      if (placement || blockId) {
        const current = await api.getSchedule(weekStart)
        const block = blockId ? current.scheduled.find((item) => item.id === blockId) : current.scheduled.find((item) => item.task_id === saved!.id && item.status === 'planned' && (!value.repeat_days.length || !placement || localDateTime(item.start).toISODate() === localDateTime(placement.start).toISODate()))
        if (placement) {
          if (block) {
            if (Date.parse(block.start) !== Date.parse(placement.start) || Date.parse(block.end) !== Date.parse(placement.end) || !block.locked) await api.moveBlock(block.id, placement)
          } else await api.createBlock(saved.id, placement, original?.session_key)
        } else if (block?.locked && block.status === 'planned') await api.unlockBlock(block.id)
      }
    }, 'Task saved. Your calendar is up to date.')
    if (!success && saved && !id) setEditor({ id: saved.id, placement })
    return success
  }
  const statusTask = (id: string, status: TaskStatus) => perform(() => api.setTaskStatus(id, status), status === 'completed' ? 'Task completed. Nicely done.' : 'Task reopened.')
  const deleteTask = (id: string) => perform(() => api.deleteTask(id), 'Task deleted.')
  const deleteAllTasks = () => perform(async () => { await api.deleteAllTasks(); setEditor(null) }, 'All tasks and scheduling progress deleted.')
  const clearLearning = () => perform(() => api.clearLearning(), 'Learned history cleared. Future plans start fresh.')
  const saveGroup = (value: TaskGroupInput, id?: string) => perform(() => api.saveGroup(value, id), 'Group saved.')
  const deleteGroup = (id: string) => perform(async () => { await api.deleteGroup(id); if (groupId === id) setGroupId(null) }, 'Group removed. Its tasks are still here.')
  const saveClass = (value: ClassInput, id?: string) => perform(() => api.saveClass(value, id), 'Class saved.')
  const deleteClass = (id: string) => perform(() => api.deleteClass(id), 'Class removed.')
  const saveAvailability = (value: Availability) => perform(() => api.saveAvailability(value), 'Availability saved.')
  const importCanvas = (value: CanvasRequest) => perform(async () => { const result = await api.importCanvas(value); setMessage(`Imported ${result.imported.tasks} tasks and ${result.imported.events} events.`) }, 'Your Canvas calendar has been imported.')
  const completeBlock = (block: ScheduledTask, minutes?: number) => {
    if (!schedule?.scheduled.some((item) => item.id === block.id)) { setError('Save this session’s placement before marking it complete.'); return Promise.resolve(false) }
    return perform(() => api.completeBlock(block.id, block.status === 'completed' ? 'planned' : 'completed', minutes), block.status === 'completed' ? 'Session reopened.' : 'Session completed.')
  }
  const changeWeek = (date: string) => {
    const week = weekOf(date)
    if (week === weekStart || pending) return
    inFlight.current = true; setPending(true); setSchedule(null); setWeekStart(week); setMessage('')
  }
  const saveEvent = (id: string, value: { title: string; start: string; end: string }) => perform(() => api.saveEvent(id, value), 'Event updated.')
  const deleteEvent = (id: string) => perform(() => api.deleteEvent(id), 'Event removed.')
  const closeEvent = useCallback(() => setSelectedEvent(null), [])
  const currentLabel = page === 'groups' ? 'Task groups' : NAV.find((item) => item.id === page)?.title ?? 'Calendar'

  return <div className="app-shell">
    {sidebarOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
    <aside className={`app-sidebar ${sidebarOpen ? 'is-open' : ''}`}><a href="#calendar" className="brand" aria-label="Prioriti home"><span className="brand-symbol"><CalendarDays size={22} strokeWidth={2} /></span><span>prioriti<span className="brand-period">.</span></span></a>
      <button className="create-button" type="button" aria-label="New task" disabled={disabled} onClick={() => createTask()}><Plus size={22} /><span>New task</span></button>
      <nav className="primary-nav" aria-label="Planner sections">{NAV.map(({ id, title, icon: Icon }) => <a key={id} href={`#${id}`} aria-label={id === 'classes' ? 'Classes' : title} aria-current={page === id ? 'page' : undefined}><Icon size={18} /><span>{title}</span>{id === 'tasks' && <span className="nav-count">{tasks.filter((task) => task.status === 'todo').length}</span>}</a>)}</nav>
      <MiniCalendar key={weekStart} value={weekStart} onChange={changeWeek} compact />
      <div className="sidebar-group-heading"><span>MY GROUPS</span><a href="#groups" className="icon-button" aria-label="Manage task groups"><Plus size={16} /></a></div>
      <div className="sidebar-groups"><button className={`group-filter ${!groupId ? 'active' : ''}`} onClick={() => setGroupId(null)}><Folder size={16} /><span>All groups</span><span className="group-count">{tasks.length}</span></button>{groups.map((group) => <button className={`group-filter ${groupId === group.id ? 'active' : ''}`} key={group.id} onClick={() => { setGroupId(groupId === group.id ? null : group.id); setSidebarOpen(false) }}><span className="color-dot" style={{ background: group.color }} /><span>{group.title}</span><span className="group-count">{tasks.filter((task) => task.group_id === group.id).length}</span></button>)}{!groups.length && <a className="create-group-link" href="#groups">Create your first group<ChevronRight size={13} /></a>}</div>
      <div className="sidebar-bottom"><button className="learning-link" onClick={() => { window.location.hash = 'availability' }}><Sparkles size={17} /><span>{learning.samples ? `${learning.samples} learned preferences` : 'A little smarter with every plan'}</span></button><div className="workspace-status"><span className={`status-dot ${loaded ? '' : 'offline'}`} /><span>Saved on this computer</span></div></div>
    </aside>
    <main className="app-main"><header className="app-topbar"><div className="topbar-title"><button className="icon-button menu-button" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Menu size={21} /></button><span>Workspace</span><ChevronRight size={13} /><strong>{currentLabel}</strong></div><div className="topbar-actions"><span className="today-label">{DateTime.fromISO(today()).toFormat('cccc, LLLL d')}</span><button className={`icon-button ${pending ? 'spinning' : ''}`} type="button" aria-label="Reload saved records" disabled={pending} onClick={() => { void perform(async () => {}, 'Everything is up to date.') }}><RefreshCw size={17} /></button><span className="workspace-avatar">P</span></div></header>
      {pending && <div className="loading-line" aria-label="Loading saved records" role="status" />}
      <div className={`page-content ${page === 'calendar' ? 'calendar-page' : ''}`}>
        {page === 'calendar' && <CalendarPage weekStart={weekStart} schedule={schedule} tasks={tasks} groups={groups} groupId={groupId} disabled={disabled} onWeekChange={changeWeek} onGenerate={() => { void perform(() => api.generateSchedule(weekStart), 'Your week is planned. Adjust anything to make it yours.') }} onAccept={() => { void perform(() => api.acceptSchedule(weekStart), 'Plan kept. Your scheduling preferences have been updated.') }} onTask={openTask} onEvent={setSelectedEvent} onError={setError} onCreate={createTask} onMove={(block, placement) => { void perform(() => api.moveBlock(block.id, placement), 'Session moved. Preference saved for future plans.') }} />}
        {page === 'tasks' && <TasksPage tasks={tasks} groups={groups} groupId={groupId} disabled={disabled} onOpen={openTask} onCreate={() => createTask()} onStatus={statusTask} />}
        {page === 'groups' && <GroupsPage groups={groups} disabled={disabled} onSave={saveGroup} onDelete={deleteGroup} />}
        {page === 'classes' && <div className="workspace-page classes-page"><div className="page-heading"><div><span className="eyebrow">THE FIXED POINTS IN YOUR WEEK</span><h1>Classes & Canvas</h1><p>Bring your class schedule and assignments together.</p></div></div><CanvasImport disabled={disabled} onImport={importCanvas} /><ClassesPage classes={classes} disabled={disabled} onSave={saveClass} onDelete={deleteClass} /></div>}
        {page === 'availability' && loaded && <AvailabilityPage key={version} availability={availability} learning={learning} disabled={disabled} onSave={saveAvailability} onTrain={() => perform(() => api.trainLearning(), 'Your learned preferences are up to date.')} onDeleteTasks={deleteAllTasks} onClearLearning={clearLearning} />}
      </div>
    </main>
    {message && !error && <div className="toast success-toast" role="status"><Check size={17} />{message}</div>}
    {error && <div className="toast error-toast" role="alert"><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={16} /></button></div>}
    {editor && (!editor.id || editTask) && <TaskPanel key={`${editor.id ?? 'new'}:${editor.blockId ?? ''}`} task={editTask ?? null} groups={groups} block={editBlock} initialPlacement={editor.placement} initialGroup={groupId} disabled={disabled} onSave={saveTask} onDelete={deleteTask} onStatus={statusTask} onComplete={completeBlock} onClose={() => setEditor(null)} />}
    {selectedEvent && <EventPanel key={selectedEvent.id} event={selectedEvent} disabled={disabled} onSave={saveEvent} onDelete={deleteEvent} onClose={closeEvent} />}
  </div>
}
