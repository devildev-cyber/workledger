import type { WorkOrder } from '../api/types.ts'
import { formatDate } from '../format.ts'
import { formatMoney } from '../money.ts'

export function Outcome({ workOrder }: { workOrder: WorkOrder }) {
  if (workOrder.resolution === null) return null

  return (
    <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
      <dt className="text-slate-600">Resolution</dt>
      <dd className="whitespace-pre-wrap">{workOrder.resolution}</dd>
      <dt className="text-slate-600">Final cost</dt>
      <dd>
        {workOrder.final_cost_cents !== null && workOrder.currency
          ? formatMoney(workOrder.final_cost_cents, workOrder.currency)
          : 'Not recorded'}
      </dd>
      <dt className="text-slate-600">Verified</dt>
      <dd>
        {workOrder.verified_by_name ?? 'System'}
        {workOrder.verified_at ? ` on ${formatDate(workOrder.verified_at)}` : ''}
      </dd>
    </dl>
  )
}
