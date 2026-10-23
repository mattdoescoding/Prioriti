import { useState } from 'react'
import type { FormEvent } from 'react'
import type { ClassInput, ClassSeries } from './types'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

interface Props {
  classes: ClassSeries[]
  disabled: boolean
  onSave: (value: ClassInput, id?: string) => Promise<boolean>
  onDelete: (id: string) => Promise<boolean>
}

export default function ClassesPage({
  classes,
  disabled,
  onSave,
  onDelete,
}: Props) {
  const [editing, setEditing] = useState<ClassSeries | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const form = event.currentTarget
    const data = new FormData(form)
    const value = (name: string) => String(data.get(name) ?? '').trim()

    const saved = await onSave({
      title: value('title'),
      weekdays: data.getAll('weekday').map(Number),
      start_time: value('start_time'),
      end_time: value('end_time'),
      start_date: value('start_date'),
      end_date: value('end_date'),
      skip_dates: value('skip_dates')
        .split(',')
        .map((day) => day.trim())
        .filter(Boolean),
    }, editing?.id)

    if (saved) {
      form.reset()
      setEditing(null)
    }
  }

  async function remove(item: ClassSeries) {
    if (!window.confirm(
      `Delete all recurring meetings for "${item.title}"?`,
    )) return

    if (await onDelete(item.id)) {
      if (editing?.id === item.id) setEditing(null)
    }
  }

  return (
    <div className="columns">
      <section className="panel">
        <h2>
          {editing ? 'Edit recurring class' : 'Add a recurring class'}
        </h2>

        <p>
          Repeat on selected weekdays during the term. All times use New York time.
        </p>

        <form
          key={editing?.id ?? 'new'}
          onSubmit={(event) => { void submit(event) }}
        >
          <fieldset disabled={disabled}>
            <label>
              Class name
              <input
                name="title"
                required
                maxLength={200}
                defaultValue={editing?.title ?? ''}
              />
            </label>

            <fieldset className="weekday-field">
              <legend>Meeting days — choose at least one</legend>
              <div className="weekday-options">
                {DAYS.map((day, index) => (
                  <label key={day}>
                    <input
                      type="checkbox"
                      name="weekday"
                      value={index}
                      defaultChecked={
                        editing?.weekdays.includes(index) ?? false
                      }
                    />
                    {day}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="columns">
              <label>
                Start time
                <input
                  type="time"
                  name="start_time"
                  required
                  defaultValue={editing?.start_time ?? ''}
                />
              </label>

              <label>
                End time
                <input
                  type="time"
                  name="end_time"
                  required
                  defaultValue={editing?.end_time ?? ''}
                />
              </label>

              <label>
                First date
                <input
                  type="date"
                  name="start_date"
                  required
                  defaultValue={editing?.start_date ?? ''}
                />
              </label>

              <label>
                Last date, inclusive
                <input
                  type="date"
                  name="end_date"
                  required
                  defaultValue={editing?.end_date ?? ''}
                />
              </label>
            </div>

            <label>
              Skip dates, separated by commas
              <input
                name="skip_dates"
                placeholder="2026-11-25, 2026-11-27"
                defaultValue={editing?.skip_dates.join(', ') ?? ''}
              />
            </label>

            <p className="hint">
              Use YYYY-MM-DD. Meetings must start and end on the same day. The term may span up to 365 days.
              Editing changes the entire series. Add a skipped date to cancel one meeting.
            </p>

            <button type="submit">
              {editing ? 'Save class changes' : 'Save recurring class'}
            </button>

            {editing && (
              <button
                type="button"
                className="secondary"
                onClick={() => setEditing(null)}
              >
                Cancel editing
              </button>
            )}
          </fieldset>
        </form>
      </section>

      <section className="panel">
        <h2>Saved classes</h2>

        {classes.length === 0 ? (
          <p>No recurring classes yet.</p>
        ) : (
          <ul className="records">
            {classes.map((item) => (
              <li key={item.id}>
                <strong>{item.title}</strong>

                <p>
                  {item.weekdays.map((day) => DAYS[day]).join(', ')}
                  {' · '}
                  {item.start_time}–{item.end_time}
                </p>

                <p>{item.start_date} through {item.end_date}</p>

                {item.skip_dates.length > 0 && (
                  <p>Skipped: {item.skip_dates.join(', ')}</p>
                )}

                <div className="calendar-actions">
                  <button
                    type="button"
                    className="secondary"
                    disabled={disabled}
                    onClick={() => setEditing(item)}
                  >
                    Edit series
                  </button>

                  <button
                    type="button"
                    className="danger"
                    disabled={disabled}
                    onClick={() => { void remove(item) }}
                  >
                    Delete series
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}