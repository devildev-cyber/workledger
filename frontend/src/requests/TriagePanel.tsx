import { useState, type SubmitEventHandler } from 'react'
import { useNavigate } from 'react-router'

import { api } from '../api/client.ts'
import type { StaffRequest, StaffRequestSummary, WorkOrder } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { useApiData } from '../api/useApiData.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'
import { workOrdersPath } from '../organizations/organizations.ts'
import { WorkOrderForm } from '../workorders/WorkOrderForm.tsx'

type TriagePanelProps = {
  organizationId: string
  request: StaffRequest
  onChanged: () => void
}

type Choice = 'convert' | 'duplicate' | 'decline' | null

export function TriagePanel({ organizationId, request, onChanged }: TriagePanelProps) {
  const [choice, setChoice] = useState<Choice>(null)
  const base = `/organizations/${organizationId}/requests/${request.id}`

  return (
    <section aria-labelledby="triage-heading" className="space-y-3">
      <h2 id="triage-heading" className="text-xl font-semibold">
        Triage
      </h2>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          aria-pressed={choice === 'convert'}
          onClick={() => setChoice('convert')}
          className="rounded bg-slate-900 px-4 py-2 font-medium text-white"
        >
          Create work order
        </button>
        <button
          type="button"
          aria-pressed={choice === 'duplicate'}
          onClick={() => setChoice('duplicate')}
          className="rounded border border-slate-300 px-4 py-2"
        >
          Mark as duplicate
        </button>
        <button
          type="button"
          aria-pressed={choice === 'decline'}
          onClick={() => setChoice('decline')}
          className="rounded border border-slate-300 px-4 py-2"
        >
          Decline
        </button>
      </div>

      {choice === 'convert' && (
        <ConvertForm
          organizationId={organizationId}
          request={request}
          url={`${base}/convert`}
          onCancel={() => setChoice(null)}
        />
      )}
      {choice === 'duplicate' && (
        <DuplicateForm
          organizationId={organizationId}
          request={request}
          url={`${base}/duplicate`}
          onSaved={onChanged}
        />
      )}
      {choice === 'decline' && <DeclineForm url={`${base}/decline`} onSaved={onChanged} />}
    </section>
  )
}

function ConvertForm({
  organizationId,
  request,
  url,
  onCancel,
}: {
  organizationId: string
  request: StaffRequest
  url: string
  onCancel: () => void
}) {
  const navigate = useNavigate()

  return (
    <WorkOrderForm
      label="Create work order"
      submitLabel="Create work order"
      initial={{
        title: request.title,
        scope: request.description,
        category: request.category,
        priority: request.urgency,
        due_date: null,
      }}
      onCancel={onCancel}
      onSubmit={async (values) => {
        const created = await api<WorkOrder>(url, { method: 'POST', body: values })
        await navigate(`${workOrdersPath(organizationId)}/${created.id}`)
      }}
    />
  )
}

function DuplicateForm({
  organizationId,
  request,
  url,
  onSaved,
}: {
  organizationId: string
  request: StaffRequest
  url: string
  onSaved: () => void
}) {
  const [originalId, setOriginalId] = useState('')
  const { busy, error, run, fail } = useAction()
  const { data: nearby, error: loadError } = useApiData<StaffRequestSummary[]>(
    `/organizations/${organizationId}/requests?property_id=${request.property_id}`,
  )

  // Another report at the same property that is still open is a candidate for the original.
  const candidates = (nearby ?? []).filter(
    (item) =>
      item.id !== request.id && !['closed', 'cancelled', 'declined'].includes(item.status),
  )

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (originalId === '') {
      fail('Choose the original request.')
      return
    }
    const saved = await run(() =>
      api(url, { method: 'POST', body: { duplicate_of_id: originalId } }),
    )
    if (saved) onSaved()
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Mark as duplicate"
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error ?? loadError} />
      <SelectField
        id="duplicate-of"
        label="Original request"
        placeholder="Choose the first report"
        value={originalId}
        options={candidates.map((item) => ({
          value: item.id,
          label: `${item.reference} · ${item.title}`,
        }))}
        onChange={setOriginalId}
      />
      <p className="text-sm text-slate-600">
        The resident keeps following their own request and is told it was linked to an earlier
        report. They are not told who made it.
      </p>
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        Mark as duplicate
      </button>
    </form>
  )
}

function DeclineForm({ url, onSaved }: { url: string; onSaved: () => void }) {
  const [reason, setReason] = useState('')
  const { busy, error, run, fail } = useAction()

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (reason.trim().length < 3) {
      fail('Tell the resident why the request is being declined.')
      return
    }
    const saved = await run(() => api(url, { method: 'POST', body: { reason } }))
    if (saved) onSaved()
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Decline request"
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      <TextAreaField
        id="decline-reason"
        label="Reason for the resident"
        maxLength={1000}
        rows={3}
        value={reason}
        onChange={setReason}
      />
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        Decline request
      </button>
    </form>
  )
}
