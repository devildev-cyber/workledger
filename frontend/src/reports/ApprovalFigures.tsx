import type { ApprovalMetrics } from '../api/types.ts'
import { Figure, Figures } from './Figure.tsx'
import { formatHours, formatTotals } from './reports.ts'

/** What owners decided about estimates above the approval threshold. */
export function ApprovalFigures({ approvals }: { approvals: ApprovalMetrics }) {
  return (
    <div className="space-y-3">
      <Figures>
        <Figure label="Needed approval" value={approvals.needed_approval} />
        <Figure label="Waiting" value={approvals.pending} />
        <Figure label="Approved" value={approvals.approved} />
        <Figure label="Rejected" value={approvals.rejected} />
      </Figures>
      <Figures>
        <Figure label="Waiting amount" value={formatTotals(approvals.pending_amounts)} />
        <Figure label="Approved amount" value={formatTotals(approvals.approved_amounts)} />
        <Figure label="Rejected amount" value={formatTotals(approvals.rejected_amounts)} />
        <Figure
          label="Average decision time"
          value={formatHours(approvals.average_decision_hours)}
        />
      </Figures>
      {approvals.replaced > 0 && (
        <p className="text-sm text-slate-600">
          {approvals.replaced} estimate{approvals.replaced === 1 ? ' was' : 's were'} replaced by a
          newer one before anyone decided.
        </p>
      )}
    </div>
  )
}
