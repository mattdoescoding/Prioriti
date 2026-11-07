import { useState } from 'react'
import { FolderPlus, Pencil, Plus, Trash2 } from 'lucide-react'
import type { TaskGroup, TaskGroupInput } from './types'

interface Props { groups: TaskGroup[]; disabled: boolean; onSave: (value: TaskGroupInput, id?: string) => Promise<boolean>; onDelete: (id: string) => Promise<boolean> }
const COLORS = ['#3568e8', '#8959d0', '#d57b25', '#188b72', '#d4587b', '#367f9e', '#67734f', '#526078']
export default function GroupsPage({ groups, disabled, onSave, onDelete }: Props) {
  const [editing, setEditing] = useState<TaskGroup | null>(null)
  const [color, setColor] = useState(COLORS[0])
  return <div className="workspace-page">
    <div className="page-heading"><div><span className="eyebrow">A PLACE FOR EVERY KIND OF WORK</span><h1>Task groups</h1><p>Give related tasks a home, a color, and a little structure.</p></div></div>
    <div className="settings-columns"><section className="settings-card"><div className="card-heading"><FolderPlus size={20} /><h2>{editing ? 'Edit group' : 'Create a group'}</h2></div>
      <form key={editing?.id ?? 'new'} onSubmit={(event) => {
        event.preventDefault(); const form = event.currentTarget; const data = new FormData(form)
        void onSave({ title: String(data.get('title')).trim(), color, daily_limit: Number(data.get('daily_limit')), preferred_start: String(data.get('preferred_start')), preferred_end: String(data.get('preferred_end')) }, editing?.id).then((saved) => { if (saved) { form.reset(); setEditing(null); setColor(COLORS[0]) } })
      }}><fieldset disabled={disabled}>
        <label>Group name<input name="title" placeholder="e.g. Coursework, Reading, Personal" maxLength={80} required defaultValue={editing?.title} /></label>
        <div><span className="field-heading">Group color</span><div className="color-swatches">{COLORS.map((value) => <button key={value} type="button" aria-label={`Choose ${value}`} aria-pressed={color === value} style={{ background: value }} onClick={() => setColor(value)} />)}</div></div>
        <label>Maximum sessions per day<input name="daily_limit" type="number" min="1" max="20" required defaultValue={editing?.daily_limit ?? 3} /></label>
        <p className="field-help">Across every task in this group. Repeating tasks count toward this limit.</p>
        <div className="field-pair"><label>Preferred start<input name="preferred_start" type="time" required defaultValue={editing?.preferred_start ?? '09:00'} /></label><label>Preferred end<input name="preferred_end" type="time" required defaultValue={editing?.preferred_end ?? '18:00'} /></label></div>
        <p className="field-help">A preference, not a restriction. Availability and deadlines always take priority.</p>
        <div className="inline-actions"><button className="primary" type="submit"><Plus size={17} />{editing ? 'Save group' : 'Create group'}</button>{editing && <button className="secondary" type="button" onClick={() => { setEditing(null); setColor(COLORS[0]) }}>Cancel</button>}</div>
      </fieldset></form>
    </section><section className="group-cards">{!groups.length && <div className="settings-card empty-group"><FolderPlus size={28} /><h2>Start with what matters</h2><p>A group for coursework, one for personal projects. Keep it as simple as you like.</p></div>}{groups.map((group) => <article className="settings-card group-card" key={group.id}><div className="group-card-top"><span className="group-mark" style={{ color: group.color, background: `${group.color}12` }}><FolderPlus size={21} /></span><div className="inline-actions"><button className="icon-button" type="button" aria-label={`Edit ${group.title}`} disabled={disabled} onClick={() => { setEditing(group); setColor(group.color) }}><Pencil size={16} /></button><button className="icon-button danger" type="button" aria-label={`Delete ${group.title}`} disabled={disabled} onClick={() => { if (window.confirm(`Delete “${group.title}”? Its tasks will be kept.`)) void onDelete(group.id).then((saved) => { if (saved && editing?.id === group.id) { setEditing(null); setColor(COLORS[0]) } }) }}><Trash2 size={16} /></button></div></div><h2>{group.title}</h2><p>Up to {group.daily_limit} sessions per day</p><small>Prefers {group.preferred_start} – {group.preferred_end}</small></article>)}</section></div>
  </div>
}
