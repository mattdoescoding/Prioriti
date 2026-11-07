export type Priority = 1 | 2 | 3
export type TaskStatus = 'todo' | 'completed'
export interface TaskInput {
  title: string
  description: string
  deadline: string
  not_before: string | null
  priority: Priority
  category: string
  estimated_minutes: number
  status: TaskStatus
  group_id: string | null
  repeat_days: number[]
  sessions_per_day: number
}
export interface Task extends TaskInput { id: string; owner_id: string; source_id?: string | null }
export interface TaskGroupInput { title: string; color: string; daily_limit: number; preferred_start: string; preferred_end: string }
export interface TaskGroup extends TaskGroupInput { id: string; owner_id: string }
export interface CalendarEvent { id: string; owner_id: string; title: string; start: string; end: string; class_id?: string | null; source_id?: string | null; description?: string }
export interface ScheduledTask { id: string; task_id: string; title: string; start: string; end: string; scheduled_minutes: number; locked: boolean; status: 'planned' | 'completed'; session_key?: string; duration_source: 'user_estimate' }
export interface UnscheduledTask { task_id: string; title: string; code: string; reason: string }
export interface ScheduleResult { week_start: string; effective_start: string; scheduled: ScheduledTask[]; unscheduled: UnscheduledTask[]; events: CalendarEvent[] }
export interface LearningStatus { samples: number; trained_at: string | null; method: string }
export interface Placement { start: string; end: string }
export interface ClassInput { title: string; weekdays: number[]; start_time: string; end_time: string; start_date: string; end_date: string; skip_dates: string[] }
export interface ClassSeries extends ClassInput { id: string; owner_id: string }
export interface AvailabilityWindow { weekday: number; start_time: string; end_time: string }
export interface Availability { windows: AvailabilityWindow[] }
export interface CanvasRequest { content: string; start_date: string; end_date: string; estimated_minutes: number; selected_ids?: string[] }
export interface CanvasItem { source_id: string; title: string; kind: 'task' | 'event'; start: string | null; end: string | null; deadline: string | null; duplicate: boolean }
export interface CanvasPreview { items: CanvasItem[]; warnings: string[] }
export interface CanvasImportResult { imported: { tasks: number; events: number }; skipped: number; warnings: string[] }
