// describes data exchanged with FastAPI

export type Priority = 1 | 2 | 3
export type TaskStatus = 'todo' | 'completed'

export interface TaskInput {
  title: string
  deadline: string
  priority: Priority
  category: string
  estimated_minutes: number
  status: TaskStatus
}

export interface Task extends TaskInput {
  id: string
  owner_id: string
}

export interface CommitmentInput {
  title: string
  start: string
  end: string
}

export interface Commitment extends CommitmentInput {
  id: string
  owner_id: string
  class_id?: string | null
}

export interface ScheduledTask {
  task_id: string
  title: string
  start: string
  end: string
  scheduled_minutes: number
  duration_source: 'user_estimate'
}

export interface UnscheduledTask {
  task_id: string
  title: string
  code:
    | 'window_elapsed'
    | 'deadline_passed'
    | 'duration_exceeds_day'
    | 'no_slot'
  reason: string
}

export interface ScheduleResult {
  week_start: string
  timezone: string
  effective_start: string
  scheduled: ScheduledTask[]
  unscheduled: UnscheduledTask[]
  commitments: Commitment[]
}

export interface ClassInput {
  title: string
  weekdays: number[]
  start_time: string
  end_time: string
  start_date: string
  end_date: string
  skip_dates: string[]
}

export interface ClassSeries extends ClassInput {
  id: string
  owner_id: string
}