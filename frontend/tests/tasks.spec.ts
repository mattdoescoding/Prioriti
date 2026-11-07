import { expect, test } from '@playwright/test'

function fixture() {
  return { id: 'saved-task', owner_id: 'local-development', title: 'Read chapter',
    description: 'Review lecture notes', group_id: null, repeat_days: [], sessions_per_day: 1,
    deadline: '2026-11-12T20:00:00Z', not_before: null, priority: 2,
    category: 'Reading', estimated_minutes: 45, status: 'todo' }
}

test.beforeEach(async ({ page }) => {
  let task = fixture()
  await page.route('http://127.0.0.1:8000/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (path === '/tasks/saved-task') {
      const body = request.postDataJSON()
      if (body.not_before && Date.parse(body.not_before) >= Date.parse(body.deadline)) {
        await route.fulfill({ status: 422, json: { detail: 'Available-from time must be before the deadline.' } })
        return
      }
      task = { ...task, ...body }
      await route.fulfill({ json: task })
      return
    }
    const data = path === '/tasks' ? [task]
      : path === '/availability' ? { windows: Array.from({ length: 7 }, (_, weekday) => ({ weekday, start_time: '00:00', end_time: '24:00' })) }
      : path === '/learning/status' ? { samples: 0, trained_at: null, method: 'Local preferences' }
      : path === '/schedule' ? { week_start: url.searchParams.get('week_start'), effective_start: '2026-11-06T14:00:00Z', scheduled: [], unscheduled: [], events: [] }
      : []
    await route.fulfill({ json: data })
  })
  await page.goto('/#tasks')
  await expect(page.getByRole('button', { name: 'New task', exact: true })).toBeEnabled()
})

test('task click opens the editor with descriptions and repeats', async ({ page }) => {
  await page.getByRole('button', { name: /Open task Read chapter/ }).click()
  const panel = page.getByRole('dialog', { name: 'Edit task', exact: true })
  await expect(panel.getByLabel('Title', { exact: true })).toHaveValue('Read chapter')
  await expect(panel.getByLabel('Description', { exact: true })).toHaveValue('Review lecture notes')
  await panel.getByLabel('Repeat weekly').check()
  await expect(panel.getByLabel('Sessions per day', { exact: true })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Monday', exact: true })).toBeVisible()
})

test('invalid task dates can be corrected without reloading', async ({ page }) => {
  await page.getByRole('button', { name: /Open task Read chapter/ }).click()
  const panel = page.getByRole('dialog', { name: 'Edit task', exact: true })
  await panel.getByLabel('Available from date', { exact: true }).fill('2026-11-13')
  await panel.getByLabel('Available from time', { exact: true }).fill('09:00')
  await panel.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('alert')).toContainText('Available-from time')
  await expect(panel.getByLabel('Available from date', { exact: true })).toBeEnabled()
  await panel.getByLabel('Available from date', { exact: true }).fill('2026-11-09')
  await panel.getByRole('button', { name: 'Save changes' }).click()
  await expect(panel).toHaveCount(0)
})

test('calendar uses an in-app date picker and has no commitment flow', async ({ page }) => {
  await page.getByRole('link', { name: 'Calendar', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Auto-plan', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Choose calendar date', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Choose a date', exact: true })).toBeVisible()
  await expect(page.getByText(/commitment/i)).toHaveCount(0)
})

test('editing an ungrouped task never silently assigns the active group', async ({ page }) => {
  const task = fixture()
  await page.route('http://127.0.0.1:8000/groups', route => route.fulfill({ json: [{ id: 'coursework', owner_id: 'local-development', title: 'Coursework', color: '#3568e8', daily_limit: 3, preferred_start: '09:00', preferred_end: '18:00' }] }))
  await page.route('http://127.0.0.1:8000/schedule?*', route => route.fulfill({ json: { week_start: new URL(route.request().url()).searchParams.get('week_start'), effective_start: task.deadline, events: [], scheduled: [], unscheduled: [{ task_id: task.id, title: task.title, code: 'no_slot', reason: 'No space yet' }] } }))
  await page.goto('/#calendar')
  await page.reload()
  await page.getByRole('button', { name: /^Coursework/ }).click()
  await page.getByRole('button', { name: /need attention/ }).click()
  await page.getByRole('button', { name: /Read chapter No space yet/ }).click()
  await expect(page.getByRole('dialog', { name: 'Edit task' }).getByLabel('Group', { exact: true })).toHaveValue('')
})

test('deleting the edited group returns the form to creation', async ({ page }) => {
  let groups = [{ id: 'coursework', owner_id: 'local-development', title: 'Coursework', color: '#3568e8', daily_limit: 3, preferred_start: '09:00', preferred_end: '18:00' }]
  await page.route('http://127.0.0.1:8000/groups**', async route => {
    if (route.request().method() === 'DELETE') { groups = []; await route.fulfill({ json: { deleted: true } }) }
    else await route.fulfill({ json: groups })
  })
  page.on('dialog', dialog => dialog.accept())
  await page.goto('/#groups')
  await page.reload()
  await page.getByRole('button', { name: 'Edit Coursework', exact: true }).click()
  await page.getByRole('button', { name: 'Delete Coursework', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Create a group', exact: true })).toBeVisible()
})

test('event editor receives keyboard focus and closes with Escape', async ({ page }) => {
  await page.route('http://127.0.0.1:8000/schedule?*', route => {
    const week = new URL(route.request().url()).searchParams.get('week_start')
    return route.fulfill({ json: { week_start: week, effective_start: `${week}T14:00:00Z`, scheduled: [], unscheduled: [], events: [{ id: 'event', owner_id: 'local-development', title: 'Lecture', start: `${week}T14:00:00Z`, end: `${week}T15:00:00Z` }] } })
  })
  await page.goto('/#calendar')
  await page.reload()
  await page.getByRole('button', { name: 'View event Lecture', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Calendar event', exact: true })
  await expect(dialog.getByLabel('Title', { exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
})

for (const retry of [false, true]) test(`editing a pruned repeat occurrence preserves identity${retry ? ' after a rejected placement' : ''}`, async ({ page }) => {
  let task = { ...fixture(), repeat_days: [0], sessions_per_day: 3 }
  let pruned = false
  const createdKeys: string[] = []
  let movedCompleted = false
  await page.route('http://127.0.0.1:8000/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    const week = url.searchParams.get('week_start') || '2026-11-02'
    const first = { id: 'first', task_id: task.id, title: task.title, start: `${week}T14:00:00Z`, end: `${week}T14:45:00Z`, scheduled_minutes: 45, locked: true, status: 'completed', session_key: `${week}:0`, duration_source: 'user_estimate' }
    const second = { ...first, id: 'second', status: 'planned', locked: false, start: `${week}T16:00:00Z`, end: `${week}T16:45:00Z`, session_key: `${week}:2` }
    if (path === '/tasks/saved-task' && request.method() === 'PUT') { task = { ...task, ...request.postDataJSON() }; pruned = true; await route.fulfill({ json: task }); return }
    if (path === '/schedule/blocks/first' && request.method() === 'PUT') { movedCompleted = true; await route.fulfill({ status: 422, json: { detail: 'Reopen this completed session before moving it.' } }); return }
    if (path === '/schedule/blocks' && request.method() === 'POST') { createdKeys.push(request.postDataJSON().session_key ?? ''); if (retry && createdKeys.length === 1) await route.fulfill({ status: 422, json: { detail: 'This time conflicts with a lecture.' } }); else await route.fulfill({ status: 201, json: second }); return }
    const data = path === '/tasks' ? [task] : path === '/groups' || path === '/classes' ? []
      : path === '/availability' ? { windows: [] } : path === '/learning/status' ? { samples: 0, trained_at: null, method: '' }
      : path === '/schedule' ? { week_start: week, effective_start: first.start, events: [], unscheduled: [], scheduled: pruned ? [first] : [first, second] } : []
    await route.fulfill({ json: data })
  })
  await page.goto('/#calendar')
  await page.reload()
  await page.getByRole('button', { name: 'Edit task Read chapter', exact: true }).last().click()
  const panel = page.getByRole('dialog', { name: 'Edit task', exact: true })
  await panel.getByLabel('Place at a specific time').check()
  await panel.getByLabel('Estimated minutes', { exact: true }).fill('60')
  await panel.getByRole('button', { name: 'Save changes', exact: true }).click()
  if (retry) {
    await expect(page.getByRole('alert')).toContainText('conflicts with a lecture')
    await panel.getByLabel('Scheduled start').fill('2026-11-02T12:00')
    await panel.getByRole('button', { name: 'Save changes', exact: true }).click()
  }
  await expect(panel).toHaveCount(0)
  expect(movedCompleted).toBe(false)
  expect(createdKeys).toHaveLength(retry ? 2 : 1)
  expect(createdKeys.every((key) => /:2$/.test(key))).toBe(true)
})
