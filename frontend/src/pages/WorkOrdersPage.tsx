import { useState, type SubmitEventHandler } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { api } from '../api/client.ts'
import type { Property, Urgency, WorkOrder, WorkOrderStatus, WorkOrderSummary } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { TextField } from '../components/TextField.tsx'
import { formatDay } from '../format.ts'
import { canSeeDirectory, findMembership, workOrdersPath } from '../organizations/organizations.ts'
import { CATEGORY_LABELS, URGENCY_ORDER, URGENCY_SHORT } from '../requests/labels.ts'
import { AGE_CHOICES } from '../requests/queue.ts'
import { WORK_ORDER_STATUS_LABELS, WORK_ORDER_STATUS_ORDER } from '../workorders/labels.ts'
import { WorkOrderForm } from '../workorders/WorkOrderForm.tsx'
import { WorkOrderStatusBadge } from '../workorders/WorkOrderStatusBadge.tsx'
import { NotFoundPage } from './NotFoundPage.tsx'

export function WorkOrdersPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return <WorkOrderList organizationId={membership.organization_id} />
}

type Filters = {
  view: 'open' | 'all'
  status: WorkOrderStatus | ''
  priority: Urgency | ''
  propertyId: string
  search: string
  olderThan: string
}

const NO_FILTERS: Filters = {
  view: 'open',
  status: '',
  priority: '',
  propertyId: '',
  search: '',
  olderThan: '',
}

function queryFor(filters: Filters): string {
  const params = new URLSearchParams()
  if (filters.view === 'open' && filters.status === '') params.set('open_only', 'true')
  if (filters.status) params.set('status', filters.status)
  if (filters.priority) params.set('priority', filters.priority)
  if (filters.propertyId) params.set('property_id', filters.propertyId)
  if (filters.search.trim()) params.set('q', filters.search.trim())
  if (filters.olderThan) params.set('older_than_days', filters.olderThan)
  const text = params.toString()
  return text ? `?${text}` : ''
}

function WorkOrderList({ organizationId }: { organizationId: string }) {
  const navigate = useNavigate()
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [searchText, setSearchText] = useState('')
  const [creating, setCreating] = useState(false)
  const base = `/organizations/${organizationId}/work-orders`
  const { data: workOrders, error, loading } = useApiData<WorkOrderSummary[]>(
    `${base}${queryFor(filters)}`,
  )
  const { data: properties } = useApiData<Property[]>(`/organizations/${organizationId}/properties`)

  const change = (changes: Partial<Filters>) => setFilters((current) => ({ ...current, ...changes }))

  const handleSearch: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault()
    change({ search: searchText })
  }

  const filtered = filters.search !== '' || filters.status !== '' || filters.priority !== ''
    || filters.propertyId !== '' || filters.olderThan !== ''

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-semibold">Work orders</h1>
        {!creating && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="rounded bg-slate-900 px-4 py-2 font-medium text-white"
          >
            New work order
          </button>
        )}
      </div>

      {creating && properties && (
        <WorkOrderForm
          label="New work order"
          submitLabel="Create work order"
          initial={{ title: '', scope: '', category: 'other', priority: 'routine', due_date: null }}
          properties={properties}
          onCancel={() => setCreating(false)}
          onSubmit={async (values, propertyId) => {
            const created = await api<WorkOrder>(base, {
              method: 'POST',
              body: { ...values, property_id: propertyId },
            })
            await navigate(`${workOrdersPath(organizationId)}/${created.id}`)
          }}
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SelectField
          id="work-order-view"
          label="Show"
          value={filters.view}
          options={[
            { value: 'open', label: 'Open work orders' },
            { value: 'all', label: 'All work orders' },
          ]}
          onChange={(value) => change({ view: value as Filters['view'] })}
        />
        <SelectField
          id="work-order-status-filter"
          label="Status"
          placeholder="Any status"
          value={filters.status}
          options={WORK_ORDER_STATUS_ORDER.map((value) => ({
            value,
            label: WORK_ORDER_STATUS_LABELS[value],
          }))}
          onChange={(value) => change({ status: value as WorkOrderStatus | '' })}
        />
        <SelectField
          id="work-order-priority-filter"
          label="Priority"
          placeholder="Any priority"
          value={filters.priority}
          options={URGENCY_ORDER.map((value) => ({ value, label: URGENCY_SHORT[value] }))}
          onChange={(value) => change({ priority: value as Urgency | '' })}
        />
        <SelectField
          id="work-order-property-filter"
          label="Property"
          placeholder="All properties"
          value={filters.propertyId}
          options={(properties ?? []).map((item) => ({ value: item.id, label: item.name }))}
          onChange={(value) => change({ propertyId: value })}
        />
        <SelectField
          id="work-order-age-filter"
          label="Age"
          placeholder="Any age"
          value={filters.olderThan}
          options={AGE_CHOICES}
          onChange={(value) => change({ olderThan: value })}
        />
        <form onSubmit={handleSearch} role="search" className="flex items-end gap-2 sm:col-span-2">
          <div className="flex-1">
            <TextField
              id="work-order-search"
              label="Search"
              placeholder="Title, scope or WO-0001"
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
          Loading work orders…
        </p>
      )}
      <FormError message={error} />

      {workOrders && workOrders.length === 0 && (
        <p className="text-slate-600">
          {filtered ? 'No work orders match these filters.' : 'There are no work orders yet.'}
        </p>
      )}

      {workOrders && workOrders.length > 0 && (
        <div className="overflow-x-auto rounded border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-3 py-2">Reference</th>
                <th className="px-3 py-2">Work order</th>
                <th className="px-3 py-2">Property</th>
                <th className="px-3 py-2">Priority</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Due</th>
                <th className="px-3 py-2">Requests</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {workOrders.map((workOrder) => (
                <tr key={workOrder.id}>
                  <td className="px-3 py-2">{workOrder.reference}</td>
                  <td className="px-3 py-2">
                    <Link to={`${workOrdersPath(organizationId)}/${workOrder.id}`} className="underline">
                      {workOrder.title}
                    </Link>
                    <span className="block text-xs text-slate-500">
                      {CATEGORY_LABELS[workOrder.category]}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {workOrder.unit_label ? `${workOrder.unit_label}, ` : ''}
                    {workOrder.property_name}
                  </td>
                  <td className="px-3 py-2">{URGENCY_SHORT[workOrder.priority]}</td>
                  <td className="px-3 py-2">
                    <WorkOrderStatusBadge status={workOrder.status} />
                  </td>
                  <td className="px-3 py-2">
                    {workOrder.due_date ? formatDay(workOrder.due_date) : '—'}
                    {workOrder.overdue && (
                      <span className="ml-2 rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-900">
                        Overdue
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">{workOrder.request_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
