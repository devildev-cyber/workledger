import { Link, useLocation, useParams } from 'react-router'

import type { ResidentRequest } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { findMembership, isResident, myRequestsPath } from '../organizations/organizations.ts'
import { AttachmentList } from '../requests/AttachmentList.tsx'
import { CATEGORY_LABELS, URGENCY_LABELS } from '../requests/labels.ts'
import { MessageForm } from '../requests/MessageForm.tsx'
import { StatusBadge } from '../requests/StatusBadge.tsx'
import { Timeline } from '../requests/Timeline.tsx'
import { UploadForm } from '../requests/UploadForm.tsx'
import { WithdrawControl } from '../requests/WithdrawControl.tsx'
import { NotFoundPage } from './NotFoundPage.tsx'

type ConfirmationState = { submitted?: boolean; failedUploads?: string[] } | null

export function MyRequestPage() {
  const user = useCurrentUser()
  const { organizationId, requestId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !requestId || !isResident(membership.roles)) {
    return <NotFoundPage />
  }

  return <RequestDetail organizationId={membership.organization_id} requestId={requestId} />
}

function RequestDetail({
  organizationId,
  requestId,
}: {
  organizationId: string
  requestId: string
}) {
  const location = useLocation()
  const confirmation = location.state as ConfirmationState
  const url = `/organizations/${organizationId}/my-requests/${requestId}`
  const { data: request, error, loading, reload } = useApiData<ResidentRequest>(url)

  if (loading) {
    return (
      <p role="status" className="text-slate-600">
        Loading request…
      </p>
    )
  }
  if (error || !request) {
    // Someone else's request and one that does not exist look the same.
    return <NotFoundPage />
  }

  const failedUploads = confirmation?.failedUploads ?? []

  return (
    <div className="space-y-8">
      <div>
        <Link to={myRequestsPath(organizationId)} className="text-sm text-slate-600 underline">
          My requests
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{request.title}</h1>
          <StatusBadge status={request.status} />
        </div>
        <p className="text-sm text-slate-600">{request.reference}</p>
      </div>

      {confirmation?.submitted && (
        <p role="status" className="rounded bg-green-50 p-3 text-green-900">
          Request {request.reference} received. This page will show updates as the property team
          works on it.
        </p>
      )}
      {failedUploads.length > 0 && (
        <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
          Your request was saved, but these files could not be attached: {failedUploads.join(', ')}.
          You can add them again below.
        </p>
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
          {request.location && (
            <>
              <dt className="text-slate-600">Where in the home</dt>
              <dd>{request.location}</dd>
            </>
          )}
          {request.access_notes && (
            <>
              <dt className="text-slate-600">Access notes</dt>
              <dd>{request.access_notes}</dd>
            </>
          )}
        </dl>
        <p className="whitespace-pre-wrap">{request.description}</p>
      </section>

      <section aria-labelledby="files-heading" className="space-y-3">
        <h2 id="files-heading" className="text-xl font-semibold">
          Photos and documents
        </h2>
        <AttachmentList attachments={request.attachments} baseUrl={`${url}/attachments`} />
        {request.can_message && <UploadForm url={`${url}/attachments`} onUploaded={reload} />}
      </section>

      <section aria-labelledby="progress-heading" className="space-y-3">
        <h2 id="progress-heading" className="text-xl font-semibold">
          Progress
        </h2>
        <Timeline
          items={request.timeline.map((entry) => ({
            id: entry.id,
            kind: entry.kind,
            body: entry.body,
            status: entry.status,
            created_at: entry.created_at,
            who: entry.author,
          }))}
        />
        {request.can_message && <MessageForm url={`${url}/messages`} onSent={reload} />}
      </section>

      {request.can_cancel && <WithdrawControl url={`${url}/cancel`} onWithdrawn={reload} />}
    </div>
  )
}
