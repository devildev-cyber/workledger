import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { RequestStatus } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'
import { STATUS_LABELS, STATUS_ORDER } from './labels.ts'

type StaffUpdateFormProps = {
  url: string
  currentStatus: RequestStatus
  onSaved: () => void
}

export function StaffUpdateForm({ url, currentStatus, onSaved }: StaffUpdateFormProps) {
  const [status, setStatus] = useState('')
  const [body, setBody] = useState('')
  const [visibility, setVisibility] = useState<'internal' | 'resident'>('internal')
  const { busy, error, run, fail } = useAction()

  const finished = currentStatus === 'closed' || currentStatus === 'cancelled'
  const choices = STATUS_ORDER.filter((value) => value !== 'submitted' && value !== currentStatus)

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (status === '' && body.trim() === '') {
      fail('Write a note or choose a new status.')
      return
    }
    const saved = await run(() =>
      api(url, {
        method: 'POST',
        body: { status: status === '' ? null : status, body, visibility },
      }),
    )
    if (saved) {
      setStatus('')
      setBody('')
      onSaved()
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Update request"
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      {!finished && (
        <SelectField
          id="update-status"
          label="Change status"
          placeholder="Keep current status"
          value={status}
          options={choices.map((value) => ({ value, label: STATUS_LABELS[value] }))}
          onChange={setStatus}
        />
      )}
      <TextAreaField
        id="update-body"
        label="Note or message"
        maxLength={2000}
        rows={3}
        value={body}
        onChange={setBody}
      />
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium text-slate-700">Who can read it</legend>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="update-visibility"
            checked={visibility === 'internal'}
            onChange={() => setVisibility('internal')}
          />
          Internal note, staff only
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="update-visibility"
            checked={visibility === 'resident'}
            onChange={() => setVisibility('resident')}
          />
          Message the resident can read
        </label>
      </fieldset>
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        Save update
      </button>
    </form>
  )
}
