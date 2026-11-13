import { Link, useParams } from 'react-router'

import type { Approval } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { DecisionForm } from '../approvals/DecisionForm.tsx'
import { EstimateStatusBadge } from '../estimates/EstimateStatusBadge.tsx'
import { EstimateVersions } from '../estimates/EstimateVersions.tsx'
import { addressLine, formatDate, formatDay } from '../format.ts'
import { formatMoney } from '../money.ts'
import { approvalsPath, findMembership, isPropertyOwner } from '../organizations/organizations.ts'
import { CATEGORY_LABELS, URGENCY_SHORT } from '../requests/labels.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function ApprovalPage() {
  const user = useCurrentUser()
  const { organizationId, estimateId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !estimateId || !isPropertyOwner(membership.roles)) {
    return <NotFoundPage />
  }

  return <ApprovalDetail organizationId={membership.organization_id} estimateId={estimateId} />
}

function ApprovalDetail({
  organizationId,
  estimateId,
}: {
  organizationId: string
  estimateId: string
}) {
  const url = `${approvalsPath(organizationId)}/${estimateId}`
  const { data: approval, error, loading, reload } = useApiData<Approval>(url)

  if (loading) {
    return (
      <p role="status" className="text-slate-600">
        Loading estimate…
      </p>
    )
  }
  if (error || !approval) {
    return <NotFoundPage />
  }

  const replacement = approval.current ? undefined : approval.versions.find((item) => item.current)
  const address = addressLine(approval)

  return (
    <div className="space-y-8">
      <div>
        <Link to={approvalsPath(organizationId)} className="text-sm text-slate-600 underline">
          All approvals
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{approval.title}</h1>
          <EstimateStatusBadge status={approval.status} />
        </div>
        <p className="text-sm text-slate-600">{approval.reference}</p>
      </div>

      {replacement && (
        <p role="status" className="rounded border border-slate-300 bg-slate-50 p-3 text-sm">
          A newer estimate has replaced this one.{' '}
          <Link to={`${approvalsPath(organizationId)}/${replacement.id}`} className="underline">
            See the current estimate
          </Link>
        </p>
      )}

      <section aria-labelledby="work-heading" className="space-y-3">
        <h2 id="work-heading" className="text-xl font-semibold">
          Work requested
        </h2>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-slate-600">Property</dt>
          <dd>
            {approval.property_name}
            {address ? `, ${address}` : ''}
          </dd>
          {approval.location && (
            <>
              <dt className="text-slate-600">Location</dt>
              <dd>{approval.location}</dd>
            </>
          )}
          <dt className="text-slate-600">Kind of work</dt>
          <dd>{CATEGORY_LABELS[approval.category]}</dd>
          <dt className="text-slate-600">Priority</dt>
          <dd>{URGENCY_SHORT[approval.priority]}</dd>
          <dt className="text-slate-600">Due date</dt>
          <dd>{approval.due_date ? formatDay(approval.due_date) : 'Not set'}</dd>
        </dl>
        <p className="whitespace-pre-wrap">{approval.scope}</p>
      </section>

      <section aria-labelledby="estimate-heading" className="space-y-3">
        <h2 id="estimate-heading" className="text-xl font-semibold">
          Estimate
        </h2>
        <p className="text-2xl font-semibold">
          {formatMoney(approval.amount_cents, approval.currency)}
        </p>
        {approval.threshold_cents !== null && (
          <p className="text-sm text-slate-600">
            The approval threshold was {formatMoney(approval.threshold_cents, approval.currency)}.
          </p>
        )}
        <p className="whitespace-pre-wrap">{approval.description}</p>
        <p className="text-sm text-slate-600">
          {approval.provider_name ? `${approval.provider_name} · ` : ''}
          Recorded by {approval.submitted_by_name} on {formatDate(approval.submitted_at)}
        </p>
        {approval.decided_at && (
          <p className="text-sm">
            {approval.status === 'approved' ? 'Approved' : 'Rejected'} by{' '}
            {approval.decided_by_name ?? 'a property owner'} on {formatDate(approval.decided_at)}
            {approval.decision_reason ? `: ${approval.decision_reason}` : ''}
          </p>
        )}
      </section>

      {approval.decidable && (
        <section aria-labelledby="decision-heading" className="space-y-3">
          <h2 id="decision-heading" className="text-xl font-semibold">
            Your decision
          </h2>
          <DecisionForm url={url} onDecided={reload} />
        </section>
      )}

      <section aria-labelledby="versions-heading" className="space-y-3">
        <h2 id="versions-heading" className="text-xl font-semibold">
          All estimates for this work
        </h2>
        <EstimateVersions versions={approval.versions} />
      </section>
    </div>
  )
}
