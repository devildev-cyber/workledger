import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { WorkOrderStatus } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { TextField } from '../components/TextField.tsx'
import { WORK_ORDER_STATUS_LABELS } from './labels.ts'

type StatusControlProps = {
  url: string
  allowed: WorkOrderStatus[]
  onChanged: () => void
}

export function StatusControl({ url, allowed, onChanged }: StatusControlProps) {
  const [status, setStatus] = useState('')
  const [note, setNote] = useState('')
  const { busy, error, run, fail } = useAction()

  if (allowed.length === 0) {
    return (
      <p className="text-sm text-slate-600">
        This work order is finished. An administrator can reopen it.
      </p>
    )
  }

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (status === '') {
      fail('Choose the new status.')
      return
    }
    const saved = await run(() =>
      api(url, { method: 'POST', body: { status, note: note.trim() === '' ? null : note } }),
    )
    if (saved) {
      setStatus('')
      setNote('')
      onChanged()
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Change status"
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      <SelectField
        id="work-order-status"
        label="New status"
        placeholder="Choose a status"
        value={status}
        options={allowed.map((value) => ({ value, label: WORK_ORDER_STATUS_LABELS[value] }))}
        onChange={setStatus}
      />
      <TextField
        id="work-order-status-note"
        label="Reason or note (optional)"
        maxLength={1000}
        value={note}
        onChange={setNote}
      />
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        Update status
      </button>
    </form>
  )
}
