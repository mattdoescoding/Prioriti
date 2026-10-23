import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import type { Commitment, ScheduleResult, Task } from './types'
import { formatDateTime, localToUtc, todayInNewYork } from './time'
import './App.css'

type Page = 'calendar' | 'tasks' | 'classes'

function readPage(): Page {
  if (window.location.hash === '#tasks') return 'tasks'
  if (window.location.hash === '#classes') return 'classes'
  return 'calendar'
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

function field(data: FormData, name: string): string {
  const value = String(data.get(name) ?? '').trim()
  if (!value) throw new Error(`Please enter ${name}.`)
  return value
}

export default function App() {
  const [page, setPage] = useState<Page>(readPage)
  const [tasks, setTasks] = useState<Task[]>([])
  const [commitments, setCommitments] = useState<Commitment[]>([])
  const [schedule, setSchedule] = useState<ScheduleResult | null>(null)
  const [weekStart, setWeekStart] = useState(todayInNewYork)
  const [loaded, setLoaded] = useState(false)
  const [pending, setPending] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const inFlight = useRef(true)
  useEffect(() => {
    const syncPage = () => setPage(readPage())
    window.addEventListener('hashchange', syncPage)
    return () => window.removeEventListener('hashchange', syncPage)
  }, [])

  useEffect(() => {
    let active = true

    Promise.all([api.getTasks(), api.getCommitments()])
      .then(([savedTasks, savedCommitments]) => {
        if (!active) return
        setTasks(savedTasks)
        setCommitments(savedCommitments)
        setLoaded(true)
      })
      .catch((reason: unknown) => {
        if (active) setError(errorText(reason))
      })
      .finally(() => {
        if (active) {
          inFlight.current = false
          setPending(false)
        }
      })

    return () => { active = false }
  }, [])

  async function perform(action: () => Promise<void>) {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setError('')
    setMessage('')
    setSchedule(null)

    try {
      await action()
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  function reload() {
    void perform(async () => {
      setLoaded(false)
      const [savedTasks, savedCommitments] = await Promise.all([
        api.getTasks(), api.getCommitments(),
      ])
      setTasks(savedTasks)
      setCommitments(savedCommitments)
      setLoaded(true)
      setMessage('Saved records refreshed. Generate a new schedule when ready.')
    })
  }

  function saveTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget

    void perform(async () => {
      const data = new FormData(form)
      const minutes = Number(field(data, 'minutes'))
      const priority = Number(field(data, 'priority'))
      const status = field(data, 'status')

      if (!Number.isSafeInteger(minutes) || minutes <= 0) {
        throw new Error('Estimated minutes must be a positive whole number.')
      }
      if (priority !== 1 && priority !== 2 && priority !== 3) {
        throw new Error('Choose a valid priority.')
      }
      if (status !== 'todo' && status !== 'completed') {
        throw new Error('Choose a valid status.')
      }

      const saved = await api.createTask({
        title: field(data, 'title'),
        deadline: localToUtc(field(data, 'deadline')),
        priority,
        category: field(data, 'category'),
        estimated_minutes: minutes,
        status,
      })

      setTasks((current) => [...current, saved])
      form.reset()
      setMessage('Task saved. Generate a new schedule to include your changes.')
    })
  }

  function saveCommitment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget

    void perform(async () => {
      const data = new FormData(form)
      const start = localToUtc(field(data, 'start'))
      const end = localToUtc(field(data, 'end'))
      if (Date.parse(end) <= Date.parse(start)) {
        throw new Error('The commitment must end after it starts.')
      }

      const saved = await api.createCommitment({
        title: field(data, 'title'), start, end,
      })
      setCommitments((current) => [...current, saved])
      form.reset()
      setMessage('Commitment saved. Generate a new schedule to include your changes.')
    })
  }

  function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void perform(async () => {
      const result = await api.generateSchedule(weekStart)
      setSchedule(result)
      setMessage(
        `${result.scheduled.length} scheduled; ${result.unscheduled.length} unscheduled.`,
      )
    })
  }

  const agenda = schedule ? [
    ...schedule.commitments.map((item) => ({
      key: `commitment-${item.id}`, kind: 'Commitment',
      title: item.title, start: item.start, end: item.end, detail: 'Fixed time',
    })),
    ...schedule.scheduled.map((item) => ({
      key: `task-${item.task_id}`, kind: 'Task',
      title: item.title, start: item.start, end: item.end,
      detail: `${item.scheduled_minutes} minutes · based on your estimate`,
    })),
  ].sort((a, b) => Date.parse(a.start) - Date.parse(b.start)) : []

  return (
    <main>
      <header className="page-header">
        <div>
          <span className="badge">Local demo</span>
          <h1>Prioriti</h1>
          <p>Save your work, add commitments, and plan the next seven days.</p>
        </div>
        <button type="button" className="secondary" onClick={reload} disabled={pending}>
          Reload saved records
        </button>
      </header>

      <nav className="page-nav" aria-label="Planner sections">
        <a href="#calendar" aria-current={page === 'calendar' ? 'page' : undefined}>
          Calendar
        </a>
        <a href="#tasks" aria-current={page === 'tasks' ? 'page' : undefined}>
          Tasks
        </a>
        <a href="#classes" aria-current={page === 'classes' ? 'page' : undefined}>
          Classes
        </a>
      </nav>

      <p className="notice">
        All dates and times use America/New_York. Tasks use 9AM–9PM availability and round up to 15-minute blocks.
      </p>
      <div role="status" aria-live="polite">
        {pending ? <p className="notice">Working…</p> : message && <p className="success">{message}</p>}
      </div>
      {error && <p role="alert" className="error">{error}</p>}

      <div className="page-content">
        <section className="panel" hidden={page !== 'tasks'}>
          <h2>Add a task</h2>
          <form onSubmit={saveTask}>
            <fieldset disabled={pending || !loaded}>
              <label>Title<input name="title" required maxLength={200} /></label>
              <label>Deadline<input name="deadline" type="datetime-local" required /></label>
              <div className="page-content">
                <label>Estimated minutes
                  <input name="minutes" type="number" min="1" step="1" required />
                </label>
                <label>Priority
                  <select name="priority" defaultValue="2">
                    <option value="1">1 — Low</option>
                    <option value="2">2 — Medium</option>
                    <option value="3">3 — High</option>
                  </select>
                </label>
              </div>
              <label>Category
                <input name="category" placeholder="Assignment, studying…" required maxLength={80} />
              </label>
              <label>Status
                <select name="status" defaultValue="todo">
                  <option value="todo">To do</option>
                  <option value="completed">Completed</option>
                </select>
              </label>
              <button type="submit">Save task</button>
            </fieldset>
          </form>
        </section>

        <section className="panel" hidden={page !== 'tasks'}>
          <h2>Add a commitment</h2>
          <p>Enter a one-off class, meeting, or other fixed block of time.</p>
          <form onSubmit={saveCommitment}>
            <fieldset disabled={pending || !loaded}>
              <label>Title<input name="title" required maxLength={200} /></label>
              <label>Start<input name="start" type="datetime-local" required /></label>
              <label>End<input name="end" type="datetime-local" required /></label>
              <button type="submit">Save commitment</button>
            </fieldset>
          </form>
        </section>
      </div>

      <div className="page-content">
        <section className="panel" hidden={page !== 'tasks'}>
          <h2>Saved tasks</h2>
          {!loaded ? <p>Load saved records to continue.</p> : tasks.length === 0 ? <p>No tasks yet.</p> : (
            <ul className="records">
              {tasks.map((task) => (
                <li key={task.id}>
                  <strong>{task.title}</strong>
                  <p>{task.estimated_minutes} min · Priority {task.priority} · {task.category} · {task.status}</p>
                  <small>Due {formatDateTime(task.deadline)}</small>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel" hidden={page !== 'tasks'}>
          <h2>Saved commitments</h2>
          {!loaded ? <p>Load saved records to continue.</p> : commitments.length === 0 ? <p>No commitments yet.</p> : (
            <ul className="records">
              {commitments.map((item) => (
                <li key={item.id}>
                  <strong>{item.title}</strong>
                  <p>{formatDateTime(item.start)} → {formatDateTime(item.end)}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="panel" hidden={page !== 'tasks'}>
        <h2>Plan seven days</h2>
        <form onSubmit={generate}>
          <fieldset disabled={pending || !loaded}>
            <label>First day
              <input
                type="date" required value={weekStart}
                onChange={(event) => {
                  setWeekStart(event.target.value)
                  setSchedule(null)
                  setMessage('')
                }}
              />
            </label>
            <button type="submit">Generate schedule</button>
          </fieldset>
        </form>
        <p className="hint">
          Completed tasks are excluded. Each task uses one continuous block. The agenda is regenerated from saved records.
        </p>

        {!schedule ? <p>Generate a schedule to see your agenda.</p> : (
          <>
            <h3>Agenda</h3>
            <p>Planning starts {formatDateTime(schedule.effective_start)}.</p>
            {agenda.length === 0 ? <p>No blocks in this window.</p> : (
              <ul className="records">
                {agenda.map((item) => (
                  <li key={item.key}>
                    <span className="badge">{item.kind}</span>
                    <strong>{item.title}</strong>
                    <p>{formatDateTime(item.start)} → {formatDateTime(item.end)}</p>
                    <small>{item.detail}</small>
                  </li>
                ))}
              </ul>
            )}
            <h3>Unscheduled tasks</h3>
            {schedule.unscheduled.length === 0 ? <p>No unscheduled tasks.</p> : (
              <ul className="records">
                {schedule.unscheduled.map((item) => (
                  <li key={item.task_id}>
                    <strong>{item.title}</strong>
                    <p>{item.reason}</p>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>
    </main>
  )
}