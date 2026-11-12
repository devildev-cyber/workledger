import { useState } from 'react'
import { Link, useParams } from 'react-router'

import type { RequestStatus, StaffRequestSummary } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { formatDate } from '../format.ts'
import { canSeeDirectory, findMembership, requestsPath } from '../organizations/organizations.ts'
import { CATEGORY_LABELS, STATUS_LABELS, STATUS_ORDER } from '../requests/labels.ts'
import { StatusBadge } from '../requests/StatusBadge.tsx'
import { NotFoundPage } from './NotFoundPage.tsx'

const URGENCY_SHORT = { routine: 'Routine', soon: 'Soon', urgent: 'Urgent', emergency: 'Emergency' }

export function RequestsPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return <RequestsList organizationId={membership.organization_id} />
}

function RequestsList({ organizationId }: { organizationId: string }) {
  const [status, setStatus] = useState<RequestStatus | ''>('')
  const base = `/organizations/${organizationId}/requests`
  const { data: requests, error, loading } = useApiData<StaffRequestSummary[]>(
    status ? `${base}?status=${status}` : base,
  )

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Requests</h1>

      <div className="max-w-xs">
        <SelectField
          id="status-filter"
          label="Show"
          placeholder="All statuses"
          value={status}
          options={STATUS_ORDER.map((value) => ({ value, label: STATUS_LABELS[value] }))}
          onChange={(value) => setStatus(value as RequestStatus | '')}
        />
      </div>

      {loading && (
        <p role="status" className="text-slate-600">
          Loading requests…
        </p>
      )}
      <FormError message={error} />

      {requests && requests.length === 0 && (
        <p className="text-slate-600">
          {status ? 'No requests have this status.' : 'No requests have been reported yet.'}
        </p>
      )}

      {requests && requests.length > 0 && (
        <div className="overflow-x-auto rounded border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-3 py-2">Reference</th>
                <th className="px-3 py-2">Summary</th>
                <th className="px-3 py-2">Home</th>
                <th className="px-3 py-2">Resident</th>
                <th className="px-3 py-2">Urgency</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {requests.map((request) => (
                <tr key={request.id}>
                  <td className="px-3 py-2">{request.reference}</td>
                  <td className="px-3 py-2">
                    <Link to={`${requestsPath(organizationId)}/${request.id}`} className="underline">
                      {request.title}
                    </Link>
                    <span className="block text-xs text-slate-500">
                      {CATEGORY_LABELS[request.category]}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {request.building_name ? `${request.building_name} · ` : ''}
                    {request.unit_label}, {request.property_name}
                  </td>
                  <td className="px-3 py-2">{request.resident_name}</td>
                  <td className="px-3 py-2">{URGENCY_SHORT[request.urgency]}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={request.status} />
                  </td>
                  <td className="px-3 py-2">{formatDate(request.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
