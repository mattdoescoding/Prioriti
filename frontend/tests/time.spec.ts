import { expect, test } from '@playwright/test'
import { slotAt } from '../src/time'

test('calendar placement keeps the clicked hour across clock changes', () => {
  expect(slotAt('2026-11-01', 540, 45).start).toBe('2026-11-01T14:00:00.000Z')
  expect(slotAt('2027-03-14', 540, 45).start).toBe('2027-03-14T13:00:00.000Z')
})

test('calendar placement rejects clock times that do not exist or occur twice', () => {
  expect(() => slotAt('2027-03-14', 150, 45)).toThrow()
  expect(() => slotAt('2026-11-01', 90, 45)).toThrow()
})

test('sessions crossing a repeated clock hour stay visible', async () => {
  const { layoutDay } = await import('../src/calendarLayout')
  const entries = layoutDay([{ id: 'clock-change', title: 'Reading', color: '#3568e8', start: '2027-11-07T05:30:00Z', end: '2027-11-07T06:15:00Z' }], '2027-11-07')
  expect(entries).toHaveLength(1)
  expect(entries[0].to).toBeGreaterThan(entries[0].from)
})
