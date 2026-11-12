import { useState, type SubmitEventHandler } from 'react'

import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'

export type ResidentValues = {
  full_name: string
  email: string
  phone: string
  access_instructions: string
}

type ResidentFormProps = {
  label: string
  initial?: ResidentValues
  submitLabel: string
  onSubmit: (values: ResidentValues) => Promise<unknown>
  onCancel?: () => void
}

const BLANK: ResidentValues = { full_name: '', email: '', phone: '', access_instructions: '' }

export function ResidentForm({ label, initial = BLANK, submitLabel, onSubmit, onCancel }: ResidentFormProps) {
  const [values, setValues] = useState(initial)
  const { busy, error, run } = useAction()

  const set = (field: keyof ResidentValues) => (value: string) =>
    setValues((current) => ({ ...current, [field]: value }))

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const saved = await run(() => onSubmit(values))
    if (saved && initial === BLANK) {
      setValues(BLANK)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={label}
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      <TextField
        id={`${label}-name`}
        label="Full name"
        required
        maxLength={200}
        value={values.full_name}
        onChange={set('full_name')}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          id={`${label}-email`}
          label="Email"
          type="email"
          value={values.email}
          onChange={set('email')}
        />
        <TextField id={`${label}-phone`} label="Phone" value={values.phone} onChange={set('phone')} />
      </div>
      <TextField
        id={`${label}-access`}
        label="Access instructions"
        value={values.access_instructions}
        onChange={set('access_instructions')}
      />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="rounded border border-slate-300 px-4 py-2">
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
