import { Link, useParams } from 'react-router'

import type { RequestSummary } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { formatDate } from '../format.ts'
import { findMembership, isResident, myRequestsPath } from '../organizations/organizations.ts'
import { CATEGORY_LABELS } from '../requests/labels.ts'
import { StatusBadge } from '../requests/StatusBadge.tsx'
import { NotFoundPage } from './NotFoundPage.tsx'

export function MyRequestsPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !isResident(membership.roles)) {
    return <NotFoundPage />
  }

  return <MyRequestsList organizationId={membership.organization_id} />
}

function MyRequestsList({ organizationId }: { organizationId: string }) {
  const base = myRequestsPath(organizationId)
  const { data: requests, error, loading } = useApiData<RequestSummary[]>(
    `/organizations/${organizationId}/my-requests`,
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">My requests</h1>
        <Link
          to={`${base}/new`}
          className="rounded bg-slate-900 px-4 py-2 font-medium text-white"
        >
          Report a problem
        </Link>
      </div>

      {loading && (
        <p role="status" className="text-slate-600">
          Loading your requests…
        </p>
      )}
      <FormError message={error} />

      {requests && requests.length === 0 && (
        <p className="text-slate-600">
          You have not reported anything yet. When something needs fixing, choose Report a problem.
        </p>
      )}

      {requests && requests.length > 0 && (
        <ul className="space-y-3">
          {requests.map((request) => (
            <li key={request.id} className="space-y-1 rounded border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center gap-3">
                <Link to={`${base}/${request.id}`} className="text-lg font-medium underline">
                  {request.title}
                </Link>
                <StatusBadge status={request.status} />
              </div>
              <p className="text-sm text-slate-600">
                {request.reference} · {CATEGORY_LABELS[request.category]} ·{' '}
                {request.building_name ? `${request.building_name} · ` : ''}
                {request.unit_label}, {request.property_name}
              </p>
              <p className="text-xs text-slate-500">Reported {formatDate(request.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
