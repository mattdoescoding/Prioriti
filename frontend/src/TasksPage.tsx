import { useState } from 'react'
import { ArrowUpRight, Check, Circle, Clock3, Flag, Plus, Repeat2, Search } from 'lucide-react'
import type { Task, TaskGroup, TaskStatus } from './types'
import { localDateTime, WEEKDAYS } from './time'

interface Props { tasks: Task[]; groups: TaskGroup[]; groupId: string | null; disabled: boolean; onOpen: (task: Task) => void; onCreate: () => void; onStatus: (id: string, status: TaskStatus) => Promise<boolean> }
export default function TasksPage({ tasks, groups, groupId, disabled, onOpen, onCreate, onStatus }: Props) {
  const [filter, setFilter] = useState('open')
  const [search, setSearch] = useState('')
  const visible = tasks.filter((task) => (!groupId || task.group_id === groupId) && (filter === 'all' || (filter === 'done' ? task.status === 'completed' : task.status === 'todo')) && `${task.title} ${task.description} ${task.category}`.toLowerCase().includes(search.toLowerCase()))
  const sections = [...groups.map((group) => ({ id: group.id, title: group.title, color: group.color })), { id: null, title: 'Personal', color: '#3568e8' }].filter((group) => !groupId || group.id === groupId)
  return <div className="workspace-page">
    <div className="page-heading"><div><span className="eyebrow">A LITTLE STRUCTURE. MORE SPACE.</span><h1>Your tasks</h1><p>Everything you’re working toward, all in one place.</p></div><button className="primary" type="button" onClick={onCreate} disabled={disabled}><Plus size={18} />Add task</button></div>
    <div className="list-toolbar"><div className="segmented">{[['open', 'To do'], ['done', 'Completed'], ['all', 'All tasks']].map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div><label className="search-field"><Search size={17} /><input aria-label="Search tasks" placeholder="Find a task…" value={search} onChange={(event) => setSearch(event.target.value)} /></label></div>
    {!visible.length && <div className="empty-state"><div className="empty-icon"><Check size={30} /></div><h2>{tasks.length ? 'A clear view ahead' : 'Make room for what matters'}</h2><p>{tasks.length ? 'No tasks match this view. Try another group or filter.' : 'Add your first task. Prioriti will help you find the right time for it.'}</p>{!tasks.length && <button className="primary" onClick={onCreate} disabled={disabled}><Plus size={17} />Create a task</button>}</div>}
    {sections.map((group) => {
      const items = visible.filter((task) => (task.group_id ?? null) === group.id)
      return items.length > 0 && <section className="task-group-section" key={group.id ?? 'personal'}><div className="group-heading"><span className="color-dot" style={{ background: group.color }} /><h2>{group.title}</h2><span className="count-pill">{items.length}</span></div><div className="task-list">{items.map((task) => <div className={`task-row ${task.status === 'completed' ? 'is-completed' : ''}`} key={task.id}>
        <button className="task-check" type="button" disabled={disabled} aria-label={`${task.status === 'todo' ? 'Complete' : 'Reopen'} ${task.title}`} onClick={() => { void onStatus(task.id, task.status === 'todo' ? 'completed' : 'todo') }}>{task.status === 'completed' ? <Check size={16} /> : <Circle size={19} />}</button>
        <button className="task-row-content" type="button" aria-label={`Open task ${task.title}`} onClick={() => onOpen(task)}><div className="task-row-title"><strong>{task.title}</strong>{task.source_id && <span className="tag">Canvas</span>}{task.priority === 3 && <Flag size={14} className="priority-high" />}</div>{task.description && <p>{task.description}</p>}<div className="task-meta"><span><Clock3 size={13} />{task.estimated_minutes} min</span><span>{task.category}</span>{Boolean(task.repeat_days?.length) && <span><Repeat2 size={13} />{task.sessions_per_day}× daily · {task.repeat_days.map((day) => WEEKDAYS[day]).join(', ')}</span>}</div></button>
        <span className="task-due">{localDateTime(task.deadline).toFormat('LLL d')}</span><ArrowUpRight size={16} className="row-arrow" />
      </div>)}</div></section>
    })}
  </div>
}
