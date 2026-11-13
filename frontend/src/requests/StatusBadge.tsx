import type { RequestStatus } from '../api/types.ts'
import { STATUS_LABELS } from './labels.ts'

const TONES: Record<RequestStatus, string> = {
  submitted: 'bg-slate-100 text-slate-800',
  in_review: 'bg-amber-100 text-amber-900',
  in_progress: 'bg-blue-100 text-blue-900',
  resolved: 'bg-green-100 text-green-900',
  closed: 'bg-green-100 text-green-900',
  cancelled: 'bg-slate-100 text-slate-600',
  declined: 'bg-red-100 text-red-900',
}

export function StatusBadge({ status }: { status: RequestStatus }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${TONES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  )
}
