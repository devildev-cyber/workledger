import type { WorkOrderStatus } from '../api/types.ts'
import { WORK_ORDER_STATUS_LABELS } from './labels.ts'

const TONES: Record<WorkOrderStatus, string> = {
  open: 'bg-slate-100 text-slate-800',
  assigned: 'bg-blue-100 text-blue-900',
  in_progress: 'bg-blue-100 text-blue-900',
  on_hold: 'bg-amber-100 text-amber-900',
  awaiting_approval: 'bg-amber-100 text-amber-900',
  ready_for_review: 'bg-purple-100 text-purple-900',
  completed: 'bg-green-100 text-green-900',
  closed: 'bg-green-100 text-green-900',
  cancelled: 'bg-slate-100 text-slate-600',
}

export function WorkOrderStatusBadge({ status }: { status: WorkOrderStatus }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${TONES[status]}`}>
      {WORK_ORDER_STATUS_LABELS[status]}
    </span>
  )
}
