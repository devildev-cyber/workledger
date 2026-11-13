import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { api } from '../api/client.ts'
import type { WorkOrder } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { formatDay } from '../format.ts'
import {
  canSeeDirectory,
  findMembership,
  requestsPath,
  workOrdersPath,
} from '../organizations/organizations.ts'
import { CATEGORY_LABELS, URGENCY_SHORT } from '../requests/labels.ts'
import { StatusBadge } from '../requests/StatusBadge.tsx'
import { History } from '../workorders/History.tsx'
import { NoteForm } from '../workorders/NoteForm.tsx'
import { StatusControl } from '../workorders/StatusControl.tsx'
import { WorkOrderForm } from '../workorders/WorkOrderForm.tsx'
import { WorkOrderStatusBadge } from '../workorders/WorkOrderStatusBadge.tsx'
import { NotFoundPage } from './NotFoundPage.tsx'

export function WorkOrderPage() {
  const user = useCurrentUser()
  const { organizationId, workOrderId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !workOrderId || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return <WorkOrderDetail organizationId={membership.organization_id} workOrderId={workOrderId} />
}

function WorkOrderDetail({
  organizationId,
  workOrderId,
}: {
  organizationId: string
  workOrderId: string
}) {
  const url = `/organizations/${organizationId}/work-orders/${workOrderId}`
  const { data: workOrder, error, loading, reload } = useApiData<WorkOrder>(url)
  const [editing, setEditing] = useState(false)

  if (loading) {
    return (
      <p role="status" className="text-slate-600">
        Loading work order…
      </p>
    )
  }
  if (error || !workOrder) {
    return <NotFoundPage />
  }

  return (
    <div className="space-y-8">
      <div>
        <Link to={workOrdersPath(organizationId)} className="text-sm text-slate-600 underline">
          All work orders
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{workOrder.title}</h1>
          <WorkOrderStatusBadge status={workOrder.status} />
          {workOrder.overdue && (
            <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-900">
              Overdue
            </span>
          )}
        </div>
        <p className="text-sm text-slate-600">{workOrder.reference}</p>
      </div>

      <section aria-labelledby="details-heading" className="space-y-3">
        <div className="flex items-center gap-4">
          <h2 id="details-heading" className="text-xl font-semibold">
            Details
          </h2>
          {!editing && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-sm underline"
            >
              Edit details
            </button>
          )}
        </div>
        {editing ? (
          <WorkOrderForm
            label="Edit work order"
            submitLabel="Save changes"
            initial={{
              title: workOrder.title,
              scope: workOrder.scope,
              category: workOrder.category,
              priority: workOrder.priority,
              due_date: workOrder.due_date,
            }}
            onCancel={() => setEditing(false)}
            onSubmit={async (values) => {
              await api(url, { method: 'PUT', body: values })
              setEditing(false)
              reload()
            }}
          />
        ) : (
          <>
            <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
              <dt className="text-slate-600">Property</dt>
              <dd>
                {workOrder.unit_label
                  ? `${workOrder.building_name ? `${workOrder.building_name} · ` : ''}${workOrder.unit_label}, `
                  : ''}
                {workOrder.property_name}
              </dd>
              <dt className="text-slate-600">Kind of work</dt>
              <dd>{CATEGORY_LABELS[workOrder.category]}</dd>
              <dt className="text-slate-600">Priority</dt>
              <dd>{URGENCY_SHORT[workOrder.priority]}</dd>
              <dt className="text-slate-600">Due date</dt>
              <dd>{workOrder.due_date ? formatDay(workOrder.due_date) : 'Not set'}</dd>
            </dl>
            <p className="whitespace-pre-wrap">{workOrder.scope}</p>
          </>
        )}
      </section>

      <section aria-labelledby="status-heading" className="space-y-3">
        <h2 id="status-heading" className="text-xl font-semibold">
          Status
        </h2>
        <StatusControl
          url={`${url}/status`}
          allowed={workOrder.allowed_statuses}
          onChanged={reload}
        />
      </section>

      <section aria-labelledby="requests-heading" className="space-y-3">
        <h2 id="requests-heading" className="text-xl font-semibold">
          Linked requests
        </h2>
        {workOrder.linked_requests.length === 0 ? (
          <p className="text-slate-600">No resident requests are linked to this work order.</p>
        ) : (
          <ul className="divide-y divide-slate-200 rounded border border-slate-200 bg-white">
            {workOrder.linked_requests.map((request) => (
              <li key={request.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
                <Link to={`${requestsPath(organizationId)}/${request.id}`} className="underline">
                  {request.reference}
                </Link>
                <span>{request.title}</span>
                <span className="text-slate-600">{request.resident_name}</span>
                <StatusBadge status={request.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="history-heading" className="space-y-3">
        <h2 id="history-heading" className="text-xl font-semibold">
          History
        </h2>
        <History entries={workOrder.history} />
        <NoteForm url={`${url}/notes`} onSaved={reload} />
      </section>
    </div>
  )
}
