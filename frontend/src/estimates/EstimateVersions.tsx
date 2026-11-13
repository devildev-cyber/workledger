import type { ApprovalVersion } from '../api/types.ts'
import { formatDate } from '../format.ts'
import { formatMoney } from '../money.ts'
import { EstimateStatusBadge } from './EstimateStatusBadge.tsx'

/** Every estimate there has been, newest first, with the decision on each. */
export function EstimateVersions({ versions }: { versions: ApprovalVersion[] }) {
  return (
    <ol aria-label="Estimates" className="space-y-3">
      {versions.map((item) => (
        <li key={item.id} className="space-y-1 rounded border border-slate-200 bg-white p-3">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">
              Estimate {item.version}: {formatMoney(item.amount_cents, item.currency)}
            </span>
            <EstimateStatusBadge status={item.status} />
            {!item.current && (
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                Replaced
              </span>
            )}
          </p>
          <p className="whitespace-pre-wrap text-sm text-slate-800">{item.description}</p>
          <p className="text-xs text-slate-500">
            {item.provider_name ? `${item.provider_name} · ` : ''}
            Recorded by {item.submitted_by_name} · {formatDate(item.submitted_at)}
          </p>
          {item.decided_at && (
            <p className="text-sm text-slate-800">
              {item.status === 'approved' ? 'Approved' : 'Rejected'} by{' '}
              {item.decided_by_name ?? 'the property owner'} on {formatDate(item.decided_at)}
              {item.decision_reason ? `: ${item.decision_reason}` : ''}
            </p>
          )}
        </li>
      ))}
    </ol>
  )
}
