import type { EntryKind, WorkOrderStatus } from '../api/types.ts'

export const WORK_ORDER_STATUS_LABELS: Record<WorkOrderStatus, string> = {
  open: 'Open',
  assigned: 'Assigned',
  in_progress: 'In progress',
  on_hold: 'On hold',
  awaiting_approval: 'Awaiting approval',
  ready_for_review: 'Ready for review',
  completed: 'Completed',
  closed: 'Closed',
  cancelled: 'Cancelled',
}

export const WORK_ORDER_STATUS_ORDER = Object.keys(WORK_ORDER_STATUS_LABELS) as WorkOrderStatus[]

export const ENTRY_HEADLINES: Record<Exclude<EntryKind, 'status_changed'>, string> = {
  created: 'Work order created',
  edited: 'Details changed',
  note: 'Note',
  request_linked: 'Request linked',
  assigned: 'Contractor assigned',
  unassigned: 'Contractor removed',
  assignment_accepted: 'Job accepted',
  assignment_declined: 'Job declined',
  progress: 'Progress update',
  clarification: 'Question for the property team',
  verified: 'Work verified',
  sent_back: 'Sent back to the contractor',
}

export const FIELD_LABELS: Record<string, string> = {
  title: 'Title',
  scope: 'Scope',
  category: 'Kind of work',
  priority: 'Priority',
  due_date: 'Due date',
}
