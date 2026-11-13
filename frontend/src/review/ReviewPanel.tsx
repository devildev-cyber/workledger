import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { WorkOrder } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'
import { TextField } from '../components/TextField.tsx'
import { formatDate } from '../format.ts'
import { parseMoneyToCents } from '../money.ts'

type ReviewPanelProps = {
  url: string
  workOrder: WorkOrder
  onChanged: () => void
}

/** What the contractor said when they finished, for the manager to check the work against. */
function finishingNote(workOrder: WorkOrder) {
  return [...workOrder.history]
    .reverse()
    .find((entry) => entry.kind === 'status_changed' && entry.status === 'ready_for_review')
}

export function ReviewPanel({ url, workOrder, onChanged }: ReviewPanelProps) {
  const [sendingBack, setSendingBack] = useState(false)
  const [resolution, setResolution] = useState('')
  const [cost, setCost] = useState('')
  const [currency, setCurrency] = useState(workOrder.property_currency)
  const [reason, setReason] = useState('')
  const { busy, error, run, fail, clear } = useAction()
  const finished = finishingNote(workOrder)
  const files = workOrder.attachments.length

  const handleVerify: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (resolution.trim().length < 3) {
      fail('Describe what was done.')
      return
    }
    let cents: number | null = null
    if (cost.trim() !== '') {
      cents = parseMoneyToCents(cost)
      if (cents === null) {
        fail('Enter the cost as an amount, such as 185.50.')
        return
      }
      if (!/^[A-Za-z]{3}$/.test(currency.trim())) {
        fail('Enter the currency as a three-letter code, such as USD.')
        return
      }
    }
    const saved = await run(() =>
      api(`${url}/verify`, {
        method: 'POST',
        body: {
          resolution,
          final_cost_cents: cents,
          currency: cents === null ? null : currency.trim().toUpperCase(),
        },
      }),
    )
    if (saved) onChanged()
  }

  const handleSendBack: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (reason.trim().length < 3) {
      fail('Say what still needs doing.')
      return
    }
    const saved = await run(() => api(`${url}/send-back`, { method: 'POST', body: { reason } }))
    if (saved) onChanged()
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1 rounded border border-amber-300 bg-amber-50 p-4 text-sm">
        <p className="font-medium">
          {workOrder.assignee_name ?? 'The contractor'} marked this work ready for review.
        </p>
        {finished?.body && <p className="whitespace-pre-wrap">{finished.body}</p>}
        {finished && (
          <p className="text-slate-600">
            {finished.author_name ?? 'System'} · {formatDate(finished.created_at)}
          </p>
        )}
        <p className="text-slate-700">
          {files === 0
            ? 'No photos or documents are attached.'
            : `${files} ${files === 1 ? 'photo or document is' : 'photos or documents are'} attached under Files.`}
        </p>
      </div>

      {sendingBack ? (
        <form
          onSubmit={handleSendBack}
          aria-label="Send back"
          className="space-y-3 rounded border border-slate-200 bg-white p-4"
        >
          <FormError message={error} />
          <TextAreaField
            id="review-reason"
            label="What still needs doing?"
            maxLength={1000}
            rows={3}
            value={reason}
            onChange={setReason}
          />
          <p className="text-sm text-slate-600">The contractor will read this.</p>
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={busy}
              className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
            >
              Send back
            </button>
            <button
              type="button"
              onClick={() => {
                clear()
                setSendingBack(false)
              }}
              className="rounded border border-slate-300 px-4 py-2"
            >
              Back to review
            </button>
          </div>
        </form>
      ) : (
        <form
          onSubmit={handleVerify}
          aria-label="Verify the work"
          className="space-y-3 rounded border border-slate-200 bg-white p-4"
        >
          <FormError message={error} />
          <TextAreaField
            id="review-resolution"
            label="What was done"
            maxLength={2000}
            rows={3}
            value={resolution}
            onChange={setResolution}
          />
          <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
            <TextField
              id="review-cost"
              label="Final cost (optional)"
              inputMode="decimal"
              placeholder="185.50"
              value={cost}
              onChange={setCost}
            />
            <TextField
              id="review-currency"
              label="Currency"
              maxLength={3}
              value={currency}
              onChange={setCurrency}
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={busy}
              className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
            >
              Verify and complete
            </button>
            <button
              type="button"
              onClick={() => {
                clear()
                setSendingBack(true)
              }}
              className="rounded border border-slate-300 px-4 py-2"
            >
              Send back instead
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
