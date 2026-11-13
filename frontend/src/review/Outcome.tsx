import type { WorkOrder } from '../api/types.ts'
import { formatDate } from '../format.ts'
import { formatMoney } from '../money.ts'

export function Outcome({ workOrder }: { workOrder: WorkOrder }) {
  if (workOrder.resolution === null) return null

  const check = workOrder.cost_check
  const currency = workOrder.currency ?? workOrder.property_currency

  return (
    <div className="space-y-3">
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
      {check?.over_estimate_cents != null && check.estimate_cents !== null && (
        <p role="note" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">
          The final cost is {formatMoney(check.over_estimate_cents, currency)} more than the
          estimate of {formatMoney(check.estimate_cents, currency)}.
        </p>
      )}
      {check?.above_approval && (
        <p role="note" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">
          The final cost is above the property&apos;s approval threshold, and no approved estimate
          covers it.
        </p>
      )}
    </div>
  )
}
