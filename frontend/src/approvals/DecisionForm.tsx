import { useState } from 'react'

import { api } from '../api/client.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'

type DecisionFormProps = {
  url: string
  onDecided: () => void
}

export function DecisionForm({ url, onDecided }: DecisionFormProps) {
  const [reason, setReason] = useState('')
  const { busy, error, run, fail } = useAction()

  const decide = async (decision: 'approve' | 'reject') => {
    if (decision === 'reject' && reason.trim().length < 3) {
      fail('Say why you are rejecting this estimate.')
      return
    }
    const saved = await run(() =>
      api(`${url}/decision`, {
        method: 'POST',
        body: { decision, reason: reason.trim() === '' ? null : reason },
      }),
    )
    if (saved) onDecided()
  }

  return (
    <form
      aria-label="Your decision"
      onSubmit={(event) => event.preventDefault()}
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      <TextAreaField
        id="decision-reason"
        label="Reason (needed to reject)"
        maxLength={1000}
        rows={3}
        value={reason}
        onChange={setReason}
      />
      <p className="text-sm text-slate-600">
        Your decision is recorded with your name and the time, and the property team can read your
        reason.
      </p>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => decide('approve')}
          className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => decide('reject')}
          className="rounded border border-slate-300 px-4 py-2 disabled:opacity-60"
        >
          Reject
        </button>
      </div>
    </form>
  )
}
