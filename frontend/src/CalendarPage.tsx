import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { DateTime } from 'luxon'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/react/timegrid'
import themePlugin from '@fullcalendar/react/themes/monarch'
import '@fullcalendar/react/skeleton.css'
import '@fullcalendar/react/themes/monarch/theme.css'
import '@fullcalendar/react/themes/monarch/palettes/blue.css'
import { api } from './api'
import type { Commitment, ScheduleResult } from './types'
import { formatDateTime, todayInNewYork } from './time'

const PLUGINS = [themePlugin, timeGridPlugin]

const VIEWS = {
  sevenDays: {
    type: 'timeGrid',
    duration: { days: 7 },
    dateAlignment: 'day',
  },
}

const COLORS = {
  Class: '#5942a6',
  Commitment: '#285b91',
  Task: '#126675',
}

interface Props {
  weekStart: string
  schedule: ScheduleResult | null
  disabled: boolean
  onWeekChange: (value: string) => void
  onGenerate: (event: FormEvent<HTMLFormElement>) => void
}

export default function CalendarPage({
  weekStart,
  schedule,
  disabled,
  onWeekChange,
  onGenerate,
}: Props) {
  const [fixed, setFixed] = useState<Commitment[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [view, setView] = useState('week')

  const result = schedule?.week_start === weekStart ? schedule : null
  const first = DateTime.fromISO(weekStart, {
    zone: 'America/New_York',
  })

  useEffect(() => {
    let active = true

    api.getCalendar(weekStart)
      .then((items) => {
        if (active) setFixed(items)
      })
      .catch((error: unknown) => {
        if (active) {
          setLoadError(
            error instanceof Error
              ? error.message
              : 'Calendar failed to load.',
          )
        }
      })

    return () => { active = false }
  }, [weekStart])

  const blocks = useMemo(() => [
    ...(fixed ?? []).map((item) => ({
      id: `fixed-${item.id}`,
      title: item.title,
      start: item.start,
      end: item.end,
      kind: item.class_id ? 'Class' as const : 'Commitment' as const,
    })),
    ...(result?.scheduled ?? []).map((item) => ({
      id: `task-${item.task_id}`,
      title: item.title,
      start: item.start,
      end: item.end,
      kind: 'Task' as const,
    })),
  ].sort(
    (a, b) => Date.parse(a.start) - Date.parse(b.start),
  ), [fixed, result])

  const events = useMemo(() => blocks.map((block) => ({
    id: block.id,
    title: `${block.kind}: ${block.title}`,
    start: block.start,
    end: block.end,
    backgroundColor: COLORS[block.kind],
    borderColor: COLORS[block.kind],
    textColor: '#ffffff',
  })), [blocks])

  const selectEvent = useCallback(
    (info: { event: { id: string } }) => {
      setSelectedId(info.event.id)
    },
    [],
  )

  const selected = blocks.find((block) => block.id === selectedId)

  const conflicts = (fixed ?? []).some((a, index, items) =>
    items.slice(index + 1).some((b) =>
      Date.parse(a.start) < Date.parse(b.end)
      && Date.parse(a.end) > Date.parse(b.start),
    ),
  )

  function moveWeek(days: number) {
    const next = first.plus({ days }).toISODate()
    if (next) onWeekChange(next)
  }

  return (
    <section className="panel calendar-panel">
      <div className="page-header">
        <div>
          <h2>Your week</h2>
          <p>
            {first.toFormat('LLL d, yyyy')}
            {' – '}
            {first.plus({ days: 6 }).toFormat('LLL d, yyyy')}
          </p>
        </div>

        <div className="calendar-actions">
          <a href="#tasks">Add a task or commitment</a>
          <a href="#classes">Manage classes</a>
        </div>
      </div>

      <form onSubmit={onGenerate}>
        <fieldset className="calendar-toolbar" disabled={disabled}>
          <button
            type="button"
            className="secondary"
            onClick={() => moveWeek(-7)}
          >
            Previous week
          </button>

          <button
            type="button"
            className="secondary"
            onClick={() => onWeekChange(todayInNewYork())}
          >
            Today
          </button>

          <button
            type="button"
            className="secondary"
            onClick={() => moveWeek(7)}
          >
            Next week
          </button>

          <label>
            First day
            <input
              type="date"
              required
              min="1900-01-01"
              max="9999-12-24"
              value={weekStart}
              onChange={(event) => onWeekChange(event.target.value)}
            />
          </label>

          <label>
            View
            <select
              value={view}
              onChange={(event) => setView(event.target.value)}
            >
              <option value="week">Week grid</option>
              <option value="agenda">Agenda list</option>
            </select>
          </label>

          <button type="submit" disabled={fixed === null}>
            Generate schedule
          </button>
        </fieldset>
      </form>

      <p className="hint">
        New York time · Classes are purple, commitments blue, and planned work teal.
      </p>

      {fixed === null && !loadError && (
        <p role="status">Loading fixed events…</p>
      )}

      {loadError && (
        <p role="alert" className="error">
          {loadError} Use “Reload saved records” to retry.
        </p>
      )}

      {conflicts && (
        <p className="notice">
          Some fixed events overlap. Review their times as the events reserve both blocks.
        </p>
      )}

      {!result && (
        <p className="notice">
          Generate this week to place your saved tasks around fixed events.
        </p>
      )}

      {selected && (
        <div className="event-details" aria-live="polite">
          <strong>{selected.kind}: {selected.title}</strong>
          <p>
            {formatDateTime(selected.start)}
            {' → '}
            {formatDateTime(selected.end)}
          </p>
          <button
            type="button"
            className="secondary"
            onClick={() => setSelectedId('')}
          >
            Close details
          </button>
        </div>
      )}

      {fixed !== null && (
        view === 'week' ? (
          <div
            className="calendar-scroll"
            tabIndex={0}
            role="region"
            aria-label="Seven-day calendar"
          >
            <div className="calendar-grid">
              <FullCalendar
                plugins={PLUGINS}
                views={VIEWS}
                initialView="sevenDays"
                initialDate={weekStart}
                timeZone="America/New_York"
                headerToolbar={false}
                allDaySlot={false}
                slotMinTime="00:00:00"
                slotMaxTime="24:00:00"
                scrollTime="08:00:00"
                slotDuration="00:30:00"
                height={650}
                nowIndicator={true}
                editable={false}
                events={events}
                eventClick={selectEvent}
              />
            </div>
          </div>
        ) : (
          <ul className="records">
            {blocks.map((block) => (
              <li key={block.id}>
                <span className="badge">{block.kind}</span>
                <strong>{block.title}</strong>
                <p>
                  {formatDateTime(block.start)}
                  {' → '}
                  {formatDateTime(block.end)}
                </p>
              </li>
            ))}
          </ul>
        )
      )}

      {fixed !== null && blocks.length === 0 && (
        <p>No events in this window.</p>
      )}

      {result && (
        <>
          <p className="hint">
            {result.scheduled.length} tasks placed.
            {' '}Planning starts {formatDateTime(result.effective_start)}.
            {' '}Task placements are a preview; generate again after
            refreshing or changing saved records.
          </p>

          <h3>Tasks that could not fit</h3>

          {result.unscheduled.length === 0 ? (
            <p>All eligible tasks fit.</p>
          ) : (
            <ul className="records">
              {result.unscheduled.map((item) => (
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
  )
}