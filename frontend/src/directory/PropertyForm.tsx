import { useState, type SubmitEventHandler } from 'react'

import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'
import { centsToInput, parseMoneyToCents } from '../money.ts'
import { EMPTY_PROPERTY, type PropertyValues } from './property-values.ts'

type PropertyFormProps = {
  label: string
  initial?: PropertyValues
  submitLabel: string
  onSubmit: (values: PropertyValues) => Promise<unknown>
  onCancel?: () => void
}

export function PropertyForm({
  label,
  initial = EMPTY_PROPERTY,
  submitLabel,
  onSubmit,
  onCancel,
}: PropertyFormProps) {
  const [name, setName] = useState(initial.name)
  const [street, setStreet] = useState(initial.street)
  const [city, setCity] = useState(initial.city)
  const [region, setRegion] = useState(initial.region)
  const [postalCode, setPostalCode] = useState(initial.postal_code)
  const [currency, setCurrency] = useState(initial.currency)
  const [threshold, setThreshold] = useState(centsToInput(initial.approval_threshold_cents))
  const { busy, error, run, fail } = useAction()

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()

    let cents: number | null = null
    if (threshold.trim() !== '') {
      cents = parseMoneyToCents(threshold)
      if (cents === null) {
        fail('Enter the approval threshold as an amount, such as 500 or 500.00.')
        return
      }
    }

    const saved = await run(() =>
      onSubmit({
        name,
        street,
        city,
        region,
        postal_code: postalCode,
        currency,
        approval_threshold_cents: cents,
      }),
    )
    if (saved && initial === EMPTY_PROPERTY) {
      setName('')
      setStreet('')
      setCity('')
      setRegion('')
      setPostalCode('')
      setThreshold('')
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={label}
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      <TextField id={`${label}-name`} label="Name" required maxLength={200} value={name} onChange={setName} />
      <TextField id={`${label}-street`} label="Street" value={street} onChange={setStreet} />
      <div className="grid gap-3 sm:grid-cols-3">
        <TextField id={`${label}-city`} label="City" value={city} onChange={setCity} />
        <TextField id={`${label}-region`} label="State or region" value={region} onChange={setRegion} />
        <TextField
          id={`${label}-postal`}
          label="Postal code"
          value={postalCode}
          onChange={setPostalCode}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          id={`${label}-currency`}
          label="Currency"
          maxLength={3}
          value={currency}
          onChange={setCurrency}
        />
        <TextField
          id={`${label}-threshold`}
          label="Approval threshold"
          inputMode="decimal"
          placeholder="Optional"
          value={threshold}
          onChange={setThreshold}
        />
      </div>
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
