import { expect, test, type Page } from '@playwright/test'

async function workspace(page: Page) {
  const task = { id: 'task', owner_id: 'local-development', title: 'Read chapter', description: '', group_id: 'math', repeat_days: [], sessions_per_day: 1, deadline: '2026-11-12T20:00:00Z', not_before: null, priority: 2, category: 'Reading', estimated_minutes: 45, status: 'todo' }
  const state = { tasks: [task, { ...task, id: 'done', title: 'Finished chapter', status: 'completed' }], samples: 6, deletions: [] as string[], fail: false }
  await page.route('http://127.0.0.1:8000/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    if (request.method() === 'DELETE') {
      state.deletions.push(path)
      if (state.fail) { await route.fulfill({ status: 503, json: { detail: 'Reset could not finish. Try again.' } }); return }
      if (path === '/tasks') state.tasks = []
      if (path === '/learning') state.samples = 0
      await route.fulfill({ json: path === '/tasks' ? { deleted_tasks: 2, deleted_sessions: 1 } : { samples: 0, trained_at: null, method: 'Local preferences' } })
      return
    }
    const week = url.searchParams.get('week_start') || '2026-11-02'
    const data = path === '/tasks' ? state.tasks
      : path === '/groups' ? [{ id: 'math', title: 'Math', color: '#3568e8', daily_limit: 3, preferred_start: '09:00', preferred_end: '18:00' }]
      : path === '/availability' ? { windows: Array.from({ length: 7 }, (_, weekday) => ({ weekday, start_time: '00:00', end_time: '24:00' })) }
      : path === '/learning/status' ? { samples: state.samples, trained_at: null, method: 'Local preferences' }
      : path === '/schedule' ? { week_start: week, effective_start: `${week}T14:00:00Z`, events: [], unscheduled: [], scheduled: state.tasks.length ? [{ id: 'block', task_id: task.id, title: task.title, start: `${week}T14:00:00Z`, end: `${week}T14:45:00Z`, scheduled_minutes: 45, locked: false, status: 'planned', session_key: 'once', duration_source: 'user_estimate' }] : [] }
      : []
    await route.fulfill({ json: data })
  })
  await page.goto('/#availability')
  await expect(page.getByRole('button', { name: 'Save availability', exact: true })).toBeEnabled()
  return state
}

for (const button of ['Delete all tasks', 'Clear learned data']) test(`cancelling ${button.toLowerCase()} keeps saved data`, async ({ page }) => {
  const state = await workspace(page)
  page.once('dialog', async dialog => { expect(dialog.message()).toContain('cannot be undone'); await dialog.dismiss() })
  await page.getByRole('button', { name: button, exact: true }).click()
  await page.getByRole('link', { name: 'Tasks', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Open task Read chapter', exact: true })).toBeVisible()
  expect(state.deletions).toEqual([])
  expect(state.samples).toBe(6)
})

test('deleting all tasks clears active tasks, completed tasks, and calendar sessions', async ({ page }) => {
  const state = await workspace(page)
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: 'Delete all tasks', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('All tasks and scheduling progress deleted.')
  expect(state.deletions).toEqual(['/tasks'])
  expect(state.samples).toBe(6)
  await expect(page.getByRole('button', { name: /^Math/ })).toBeVisible()
  await page.getByRole('link', { name: 'Tasks', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Make room for what matters' })).toBeVisible()
  await page.getByRole('button', { name: 'Completed', exact: true }).click()
  await expect(page.getByRole('button', { name: /Open task/ })).toHaveCount(0)
  await page.getByRole('link', { name: 'Calendar', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Edit task Read chapter', exact: true })).toHaveCount(0)
})

test('clearing learned data resets the displayed model while preserving tasks and sessions', async ({ page }) => {
  const state = await workspace(page)
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: 'Clear learned data', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Learned history cleared. Future plans start fresh.')
  await expect(page.locator('.learning-stat strong')).toHaveText('0')
  expect(state.deletions).toEqual(['/learning'])
  expect(state.tasks).toHaveLength(2)
  await page.getByRole('link', { name: 'Calendar', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Edit task Read chapter', exact: true })).toBeVisible()
})

test('a failed reset shows the error and leaves controls available for retry', async ({ page }) => {
  const state = await workspace(page)
  state.fail = true
  page.on('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: 'Clear learned data', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Reset could not finish. Try again.')
  await expect(page.locator('.learning-stat strong')).toHaveText('6')
  await expect(page.getByRole('button', { name: 'Clear learned data', exact: true })).toBeEnabled()
  state.fail = false
  await page.getByRole('button', { name: 'Clear learned data', exact: true }).click()
  await expect(page.locator('.learning-stat strong')).toHaveText('0')
})
