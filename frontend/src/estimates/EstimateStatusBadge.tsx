import type { EstimateStatus } from '../api/types.ts'
import { ESTIMATE_STATUS_LABELS } from './labels.ts'

const TONES: Record<EstimateStatus, string> = {
  pending: 'bg-amber-100 text-amber-900',
  approved: 'bg-green-100 text-green-900',
  rejected: 'bg-red-100 text-red-900',
  not_required: 'bg-slate-100 text-slate-700',
}

export function EstimateStatusBadge({ status }: { status: EstimateStatus }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${TONES[status]}`}>
      {ESTIMATE_STATUS_LABELS[status]}
    </span>
  )
}
