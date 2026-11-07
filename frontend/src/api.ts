import type {
  Availability,
  CanvasImportResult,
  CanvasPreview,
  CanvasRequest,
  ClassInput,
  ClassSeries,
  CalendarEvent,
  LearningStatus,
  Placement,
  ScheduledTask,
  TaskGroup,
  TaskGroupInput,
  ScheduleResult,
  Task,
  TaskInput,
  TaskStatus,
} from './types'

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function errorMessage(data: unknown, fallback: string): string {
  if (!isRecord(data)) return fallback
  if (typeof data.detail === 'string') return data.detail

  if (Array.isArray(data.detail)) {
    const messages = data.detail.flatMap((issue: unknown) => {
      if (!isRecord(issue) || typeof issue.msg !== 'string') return []

      const field = Array.isArray(issue.loc)
        ? issue.loc.filter((part) => part !== 'body').join('.')
        : ''

      return [field ? `${field}: ${issue.msg}` : issue.msg]
    })

    if (messages.length > 0) return messages.join('; ')
  }

  return fallback
}

async function request<T>(
  path: string,
  body?: unknown,
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' = body === undefined ? 'GET' : 'POST',
): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10_000)
  let response: Response
  let text: string

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
    text = await response.text()
  } catch {
    const problem = controller.signal.aborted
      ? 'The API request timed out.'
      : 'The API request could not finish.'

    throw new Error(
      `${problem} Check that FastAPI is running. ` +
      'If you were saving, reload the saved list before retrying.',
    )
  } finally {
    clearTimeout(timeout)
  }

  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error(`The API returned an unreadable response (${response.status}).`)
  }

  if (!response.ok) {
    throw new Error(errorMessage(data, `Request failed (${response.status}).`))
  }

  if (data === null) {
    throw new Error('The API returned an empty response.')
  }

  return data as T
}

export const api = {
  getTasks: () => request<Task[]>('/tasks'),
  
  getClasses: () => request<ClassSeries[]>('/classes'),

  getCalendar: (weekStart: string) =>
    request<CalendarEvent[]>(
      `/calendar?week_start=${encodeURIComponent(weekStart)}`,
    ),

  saveTask: (task: TaskInput, id?: string) =>
    request<Task>(id ? `/tasks/${encodeURIComponent(id)}` : '/tasks', task, id ? 'PUT' : 'POST'),

  setTaskStatus: (id: string, status: TaskStatus) =>
    request<Task>(`/tasks/${encodeURIComponent(id)}`, { status }, 'PATCH'),

  deleteTask: (id: string) =>
    request<{ deleted: boolean }>(`/tasks/${encodeURIComponent(id)}`, undefined, 'DELETE'),

  deleteAllTasks: () => request<{ deleted_tasks: number; deleted_sessions: number }>('/tasks', undefined, 'DELETE'),

  getGroups: () => request<TaskGroup[]>('/groups'),
  saveGroup: (value: TaskGroupInput, id?: string) => request<TaskGroup>(id ? `/groups/${id}` : '/groups', value, id ? 'PUT' : 'POST'),
  deleteGroup: (id: string) => request<{ deleted: boolean }>(`/groups/${id}`, undefined, 'DELETE'),
  getSchedule: (week: string) => request<ScheduleResult>(`/schedule?week_start=${week}`),
  createBlock: (task_id: string, value: Placement, session_key?: string) => request<ScheduledTask>('/schedule/blocks', { task_id, ...value, ...(session_key ? { session_key } : {}) }),
  moveBlock: (id: string, value: Placement) => request<ScheduledTask>(`/schedule/blocks/${encodeURIComponent(id)}`, value, 'PUT'),
  unlockBlock: (id: string) => request<ScheduledTask>(`/schedule/blocks/${encodeURIComponent(id)}`, { status: 'planned', locked: false }, 'PATCH'),
  completeBlock: (id: string, status: 'planned' | 'completed', actual_minutes?: number) => request<ScheduledTask>(`/schedule/blocks/${encodeURIComponent(id)}`, { status, ...(actual_minutes ? { actual_minutes } : {}) }, 'PATCH'),
  acceptSchedule: (week_start: string) => request<{ accepted: number }>('/schedule/accept', { week_start }),
  getLearning: () => request<LearningStatus>('/learning/status'),
  trainLearning: () => request<LearningStatus>('/learning/train', {}),
  clearLearning: () => request<LearningStatus>('/learning', undefined, 'DELETE'),
  saveEvent: (id: string, value: { title: string; start: string; end: string }) => request<CalendarEvent>(`/events/${encodeURIComponent(id)}`, value, 'PUT'),
  deleteEvent: (id: string) => request<{ deleted: boolean }>(`/events/${encodeURIComponent(id)}`, undefined, 'DELETE'),

  getAvailability: () => request<Availability>('/availability'),

  saveAvailability: (value: Availability) => request<Availability>('/availability', value, 'PUT'),

  previewCanvas: (value: CanvasRequest) => request<CanvasPreview>('/canvas/preview', value),

  importCanvas: (value: CanvasRequest) => request<CanvasImportResult>('/canvas/import', value),

  generateSchedule: (weekStart: string) =>
    request<ScheduleResult>('/schedule/generate', { week_start: weekStart }),

  saveClass: (value: ClassInput, id?: string) =>
    id
      ? request<ClassSeries>(
          `/classes/${encodeURIComponent(id)}`, value, 'PUT',
        )
      : request<ClassSeries>('/classes', value),

  deleteClass: (id: string) =>
    request<{ deleted: boolean }>(
      `/classes/${encodeURIComponent(id)}`, undefined, 'DELETE',
    ),
}
