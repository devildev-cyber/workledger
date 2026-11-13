import { Link, useParams } from 'react-router'

import type { ApprovalSummary } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { EstimateStatusBadge } from '../estimates/EstimateStatusBadge.tsx'
import { formatDate } from '../format.ts'
import { formatMoney } from '../money.ts'
import { approvalsPath, findMembership, isPropertyOwner } from '../organizations/organizations.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function ApprovalsPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !isPropertyOwner(membership.roles)) {
    return <NotFoundPage />
  }

  return <ApprovalList organizationId={membership.organization_id} />
}

function ApprovalList({ organizationId }: { organizationId: string }) {
  const { data, error, loading } = useApiData<ApprovalSummary[]>(approvalsPath(organizationId))

  if (loading) {
    return (
      <p role="status" className="text-slate-600">
        Loading estimates…
      </p>
    )
  }

  const items = data ?? []
  const waiting = items.filter((item) => item.decidable)
  const earlier = items.filter((item) => !item.decidable)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Approvals</h1>
      <FormError message={error} />
      {data && items.length === 0 && (
        <p className="text-slate-600">
          Nothing needs your decision. Estimates above a property&apos;s approval threshold appear
          here.
        </p>
      )}
      <ApprovalGroup
        title="Waiting for your decision"
        items={waiting}
        organizationId={organizationId}
      />
      <ApprovalGroup title="Earlier estimates" items={earlier} organizationId={organizationId} />
    </div>
  )
}

function ApprovalGroup({
  title,
  items,
  organizationId,
}: {
  title: string
  items: ApprovalSummary[]
  organizationId: string
}) {
  if (items.length === 0) return null

  return (
    <section aria-label={title} className="space-y-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              to={`${approvalsPath(organizationId)}/${item.id}`}
              className="block space-y-1 rounded border border-slate-200 bg-white p-4"
            >
              <span className="block text-base font-medium underline">{item.title}</span>
              <span className="block text-sm text-slate-700">
                {item.location ? `${item.location}, ` : ''}
                {item.property_name}
              </span>
              <span className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">{formatMoney(item.amount_cents, item.currency)}</span>
                <EstimateStatusBadge status={item.status} />
                {!item.current && (
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                    Replaced
                  </span>
                )}
                <span className="text-slate-600">{item.reference}</span>
                <span className="text-slate-600">{formatDate(item.submitted_at)}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
