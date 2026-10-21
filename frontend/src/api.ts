import type {
  Commitment,
  CommitmentInput,
  ScheduleResult,
  Task,
  TaskInput,
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

async function request<T>(path: string, body?: unknown): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10_000)
  let response: Response
  let text: string

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: body === undefined ? 'GET' : 'POST',
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

  createTask: (task: TaskInput) => request<Task>('/tasks', task),

  getCommitments: () => request<Commitment[]>('/commitments'),

  createCommitment: (commitment: CommitmentInput) =>
    request<Commitment>('/commitments', commitment),

  generateSchedule: (weekStart: string) =>
    request<ScheduleResult>('/schedule/generate', { week_start: weekStart }),
}