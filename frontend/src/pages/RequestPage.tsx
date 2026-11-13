import { Link, useParams } from 'react-router'

import type { StaffRequest } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import {
  canSeeDirectory,
  findMembership,
  requestsPath,
  workOrdersPath,
} from '../organizations/organizations.ts'
import { AttachmentList } from '../requests/AttachmentList.tsx'
import { CATEGORY_LABELS, URGENCY_LABELS } from '../requests/labels.ts'
import { StaffUpdateForm } from '../requests/StaffUpdateForm.tsx'
import { StatusBadge } from '../requests/StatusBadge.tsx'
import { Timeline } from '../requests/Timeline.tsx'
import { TriagePanel } from '../requests/TriagePanel.tsx'
import { UploadForm } from '../requests/UploadForm.tsx'
import { NotFoundPage } from './NotFoundPage.tsx'

export function RequestPage() {
  const user = useCurrentUser()
  const { organizationId, requestId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !requestId || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return <StaffRequestDetail organizationId={membership.organization_id} requestId={requestId} />
}

function StaffRequestDetail({
  organizationId,
  requestId,
}: {
  organizationId: string
  requestId: string
}) {
  const url = `/organizations/${organizationId}/requests/${requestId}`
  const { data: request, error, loading, reload } = useApiData<StaffRequest>(url)

  if (loading) {
    return (
      <p role="status" className="text-slate-600">
        Loading request…
      </p>
    )
  }
  if (error || !request) {
    return <NotFoundPage />
  }

  const { resident } = request

  return (
    <div className="space-y-8">
      <div>
        <Link to={requestsPath(organizationId)} className="text-sm text-slate-600 underline">
          All requests
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{request.title}</h1>
          <StatusBadge status={request.status} />
        </div>
        <p className="text-sm text-slate-600">
          {request.reference}
          {request.submitted_on_behalf ? ' · entered by staff' : ''}
        </p>
        {request.work_order && (
          <p className="text-sm">
            Work order:{' '}
            <Link
              to={`${workOrdersPath(organizationId)}/${request.work_order.id}`}
              className="underline"
            >
              {request.work_order.reference}
            </Link>
          </p>
        )}
        {request.duplicate_of && (
          <p className="text-sm">
            Duplicate of{' '}
            <Link
              to={`${requestsPath(organizationId)}/${request.duplicate_of.id}`}
              className="underline"
            >
              {request.duplicate_of.reference}
            </Link>
          </p>
        )}
      </div>

      {request.needs_triage && (
        <TriagePanel organizationId={organizationId} request={request} onChanged={reload} />
      )}

      <section aria-labelledby="details-heading" className="space-y-3">
        <h2 id="details-heading" className="text-xl font-semibold">
          Details
        </h2>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-slate-600">Home</dt>
          <dd>
            {request.building_name ? `${request.building_name} · ` : ''}
            {request.unit_label}, {request.property_name}
          </dd>
          <dt className="text-slate-600">Kind of problem</dt>
          <dd>{CATEGORY_LABELS[request.category]}</dd>
          <dt className="text-slate-600">Urgency</dt>
          <dd>{URGENCY_LABELS[request.urgency]}</dd>
          <dt className="text-slate-600">Where in the home</dt>
          <dd>{request.location ?? 'Not given'}</dd>
          <dt className="text-slate-600">Access notes</dt>
          <dd>{request.access_notes ?? 'None'}</dd>
        </dl>
        <p className="whitespace-pre-wrap">{request.description}</p>
      </section>

      <section aria-labelledby="resident-heading" className="space-y-3">
        <h2 id="resident-heading" className="text-xl font-semibold">
          Resident
        </h2>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-slate-600">Name</dt>
          <dd>{resident.full_name}</dd>
          <dt className="text-slate-600">Email</dt>
          <dd>{resident.email ?? 'Not set'}</dd>
          <dt className="text-slate-600">Phone</dt>
          <dd>{resident.phone ?? 'Not set'}</dd>
          <dt className="text-slate-600">Entry instructions</dt>
          <dd>{resident.access_instructions ?? 'Not set'}</dd>
        </dl>
      </section>

      <section aria-labelledby="files-heading" className="space-y-3">
        <h2 id="files-heading" className="text-xl font-semibold">
          Photos and documents
        </h2>
        <AttachmentList attachments={request.attachments} baseUrl={`${url}/attachments`} />
        <UploadForm url={`${url}/attachments`} canShare onUploaded={reload} />
      </section>

      <section aria-labelledby="timeline-heading" className="space-y-3">
        <h2 id="timeline-heading" className="text-xl font-semibold">
          Timeline
        </h2>
        <Timeline
          items={request.timeline.map((entry) => ({
            id: entry.id,
            kind: entry.kind,
            body: entry.body,
            status: entry.status,
            created_at: entry.created_at,
            who: entry.author_name ?? 'System',
            internal: entry.visibility === 'internal',
          }))}
        />
        <StaffUpdateForm
          url={`${url}/updates`}
          currentStatus={request.status}
          statusFollowsWorkOrder={request.work_order !== null || request.duplicate_of !== null}
          onSaved={reload}
        />
      </section>
    </div>
  )
}
