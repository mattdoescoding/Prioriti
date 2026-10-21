import { DateTime } from 'luxon'

const ZONE = 'America/New_York'

export function todayInNewYork(): string {
  return DateTime.now().setZone(ZONE).toFormat('yyyy-MM-dd')
}

export function localToUtc(value: string): string {
  const format = "yyyy-MM-dd'T'HH:mm"
  const local = DateTime.fromFormat(value, format, { zone: ZONE })

  if (!local.isValid || local.toFormat(format) !== value) {
    throw new Error('Enter a valid New York date and time.')
  }

  if (local.getPossibleOffsets().length > 1) {
    throw new Error(
      'This time occurs twice when daylight saving time ends. Choose an unambiguous time.',
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
    .toFormat('ccc, LLL d, yyyy · h:mm a ZZZZ')
}