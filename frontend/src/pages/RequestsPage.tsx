import { useState, type SubmitEventHandler } from 'react'
import { Link, useParams } from 'react-router'

import type { Property, RequestStatus, StaffRequestSummary, Urgency } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { TextField } from '../components/TextField.tsx'
import { formatDate } from '../format.ts'
import {
  canSeeDirectory,
  findMembership,
  requestsPath,
  workOrdersPath,
} from '../organizations/organizations.ts'
import {
  CATEGORY_LABELS,
  STATUS_LABELS,
  STATUS_ORDER,
  URGENCY_ORDER,
  URGENCY_SHORT,
} from '../requests/labels.ts'
import { AGE_CHOICES, groupRequests, type GroupBy } from '../requests/queue.ts'
import { StatusBadge } from '../requests/StatusBadge.tsx'
import { NotFoundPage } from './NotFoundPage.tsx'

export function RequestsPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return <RequestsList organizationId={membership.organization_id} />
}

type Filters = {
  view: 'triage' | 'all'
  status: RequestStatus | ''
  urgency: Urgency | ''
  propertyId: string
  search: string
  olderThan: string
}

const STARTING_FILTERS: Filters = {
  view: 'triage',
  status: '',
  urgency: '',
  propertyId: '',
  search: '',
  olderThan: '',
}

function queryFor(filters: Filters): string {
  const params = new URLSearchParams()
  if (filters.view === 'triage') params.set('needs_triage', 'true')
  if (filters.view === 'all' && filters.status) params.set('status', filters.status)
  if (filters.urgency) params.set('urgency', filters.urgency)
  if (filters.propertyId) params.set('property_id', filters.propertyId)
  if (filters.search.trim()) params.set('q', filters.search.trim())
  if (filters.olderThan) params.set('older_than_days', filters.olderThan)
  const text = params.toString()
  return text ? `?${text}` : ''
}

function RequestsList({ organizationId }: { organizationId: string }) {
  const [filters, setFilters] = useState<Filters>(STARTING_FILTERS)
  const [searchText, setSearchText] = useState('')
  const [groupBy, setGroupBy] = useState<GroupBy>('urgency')
  const base = `/organizations/${organizationId}/requests`
  const { data: requests, error, loading } = useApiData<StaffRequestSummary[]>(
    `${base}${queryFor(filters)}`,
  )
  const { data: properties } = useApiData<Property[]>(`/organizations/${organizationId}/properties`)

  const change = (changes: Partial<Filters>) => setFilters((current) => ({ ...current, ...changes }))

  const handleSearch: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault()
    change({ search: searchText })
  }

  const narrowed =
    filters.status !== '' ||
    filters.urgency !== '' ||
    filters.propertyId !== '' ||
    filters.search !== '' ||
    filters.olderThan !== ''
  const groups = requests ? groupRequests(requests, groupBy) : []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-semibold">Requests</h1>
        <Link to={workOrdersPath(organizationId)} className="text-sm underline">
          Work orders
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SelectField
          id="request-view"
          label="Show"
          value={filters.view}
          options={[
            { value: 'triage', label: 'Needs triage' },
            { value: 'all', label: 'All requests' },
          ]}
          onChange={(value) => change({ view: value as Filters['view'] })}
        />
        {filters.view === 'all' && (
          <SelectField
            id="status-filter"
            label="Status"
            placeholder="Any status"
            value={filters.status}
            options={STATUS_ORDER.map((value) => ({ value, label: STATUS_LABELS[value] }))}
            onChange={(value) => change({ status: value as RequestStatus | '' })}
          />
        )}
        <SelectField
          id="urgency-filter"
          label="Urgency"
          placeholder="Any urgency"
          value={filters.urgency}
          options={URGENCY_ORDER.map((value) => ({ value, label: URGENCY_SHORT[value] }))}
          onChange={(value) => change({ urgency: value as Urgency | '' })}
        />
        <SelectField
          id="property-filter"
          label="Property"
          placeholder="All properties"
          value={filters.propertyId}
          options={(properties ?? []).map((item) => ({ value: item.id, label: item.name }))}
          onChange={(value) => change({ propertyId: value })}
        />
        <SelectField
          id="age-filter"
          label="Age"
          placeholder="Any age"
          value={filters.olderThan}
          options={AGE_CHOICES}
          onChange={(value) => change({ olderThan: value })}
        />
        <SelectField
          id="group-by"
          label="Group by"
          value={groupBy}
          options={[
            { value: 'urgency', label: 'Urgency' },
            { value: 'property', label: 'Property' },
            { value: 'age', label: 'Age' },
            { value: 'none', label: 'No grouping' },
          ]}
          onChange={(value) => setGroupBy(value as GroupBy)}
        />
        <form onSubmit={handleSearch} role="search" className="flex items-end gap-2 sm:col-span-2">
          <div className="flex-1">
            <TextField
              id="request-search"
              label="Search"
              placeholder="Title, resident or REQ-0001"
              value={searchText}
              onChange={setSearchText}
            />
          </div>
          <button type="submit" className="rounded border border-slate-300 px-4 py-2">
            Search
          </button>
        </form>
      </div>

      {loading && (
        <p role="status" className="text-slate-600">
          Loading requests…
        </p>
      )}
      <FormError message={error} />

      {requests && requests.length === 0 && (
        <p className="text-slate-600">
          {narrowed
            ? 'No requests match these filters.'
            : filters.view === 'triage'
              ? 'Nothing is waiting for triage.'
              : 'No requests have been reported yet.'}
        </p>
      )}

      {groups.map((group) => (
        <section key={group.key} aria-label={group.title} className="space-y-2">
          {groupBy !== 'none' && (
            <h2 className="text-lg font-semibold">
              {group.title} <span className="text-sm text-slate-500">({group.requests.length})</span>
            </h2>
          )}
          <RequestTable organizationId={organizationId} requests={group.requests} />
        </section>
      ))}
    </div>
  )
}

function RequestTable({
  organizationId,
  requests,
}: {
  organizationId: string
  requests: StaffRequestSummary[]
}) {
  return (
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
            <th className="px-3 py-2">Work order</th>
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
              <td className="px-3 py-2">
                {request.work_order ? (
                  <Link
                    to={`${workOrdersPath(organizationId)}/${request.work_order.id}`}
                    className="underline"
                  >
                    {request.work_order.reference}
                  </Link>
                ) : (
                  '—'
                )}
              </td>
              <td className="px-3 py-2">{formatDate(request.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
