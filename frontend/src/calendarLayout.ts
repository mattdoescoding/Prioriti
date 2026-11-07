import { DateTime } from 'luxon'
import type { CalendarEvent, ScheduledTask, Task } from './types'
import { localDateTime } from './time'

export interface CalendarBlock { id: string; title: string; start: string; end: string; color: string; task?: Task; slot?: ScheduledTask; event?: CalendarEvent }

export function layoutDay(blocks: CalendarBlock[], day: string) {
  const prepared = blocks.filter((block) => localDateTime(block.start).toISODate()! <= day && localDateTime(block.end).toISODate()! >= day && DateTime.fromISO(block.end).toMillis() > DateTime.fromISO(day, { zone: 'America/New_York' }).toMillis()).map((block) => {
    const start = localDateTime(block.start), end = localDateTime(block.end)
    const from = start.toISODate() === day ? start.hour * 60 + start.minute : 0
    let to = end.toISODate() === day ? end.hour * 60 + end.minute : 1440
    if (to <= from && end.toMillis() > start.toMillis()) to = Math.min(1440, from + end.diff(start, 'minutes').minutes)
    return { ...block, from, to, lane: 0, lanes: 1 }
  }).filter((block) => block.to > block.from).sort((a, b) => a.from - b.from || b.to - a.to)
  let cluster: typeof prepared = [], until = 0
  const finish = () => {
    const ends: number[] = []
    for (const block of cluster) {
      let lane = ends.findIndex((end) => end <= block.from)
      if (lane < 0) lane = ends.length
      ends[lane] = block.to; block.lane = lane
    }
    for (const block of cluster) block.lanes = ends.length
    cluster = []
  }
  for (const block of prepared) {
    if (block.from >= until) finish()
    cluster.push(block); until = Math.max(until, block.to)
  }
  finish()
  return prepared
}

