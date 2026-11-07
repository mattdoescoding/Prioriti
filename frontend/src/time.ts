import { DateTime } from 'luxon'

const ZONE = 'America/New_York'

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function today(): string {
  return DateTime.now().setZone(ZONE).toFormat('yyyy-MM-dd')
}

export function localToUtc(value: string): string {
  const format = value.length === 19 ? "yyyy-MM-dd'T'HH:mm:ss" : "yyyy-MM-dd'T'HH:mm"
  const local = DateTime.fromFormat(value, format, { zone: ZONE })

  if (!local.isValid || local.toFormat(format) !== value) {
    throw new Error('Enter a valid date and time.')
  }

  if (local.getPossibleOffsets().length > 1) {
    throw new Error(
      'This time occurs twice when clocks change. Choose another time.',
    )
  }

  const utc = local.toUTC().toISO()
  if (!utc) throw new Error('The date could not be converted.')
  return utc
}

export function formatDateTime(value: string): string {
  return DateTime.fromISO(value, { setZone: true })
    .setZone(ZONE)
    .setLocale('en-US')
    .toFormat('ccc, LLL d, yyyy · h:mm a')
}

export function inputDateTime(value?: string | null): string {
  return value ? DateTime.fromISO(value).setZone(ZONE).toFormat("yyyy-MM-dd'T'HH:mm:ss") : ''
}

export const localDateTime = (value: string) => DateTime.fromISO(value, { setZone: true }).setZone(ZONE)
export const weekOf = (value: string) => DateTime.fromISO(value).startOf('week').toISODate()!

export function slotAt(day: string, minutes: number, duration = 45) {
  const hour = String(Math.floor(minutes / 60)).padStart(2, '0')
  const minute = String(minutes % 60).padStart(2, '0')
  const start = localToUtc(`${day}T${hour}:${minute}`)
  return { start, end: DateTime.fromISO(start).plus({ minutes: duration }).toUTC().toISO()! }
}
