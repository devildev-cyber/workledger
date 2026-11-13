import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { WorkOrder } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'
import { TextField } from '../components/TextField.tsx'
import { formatMoney, parseMoneyToCents } from '../money.ts'
import { EstimateVersions } from './EstimateVersions.tsx'

type EstimatePanelProps = {
  url: string
  workOrder: WorkOrder
  onChanged: () => void
}

function thresholdText(workOrder: WorkOrder): string {
  if (workOrder.approval_threshold_cents === null) {
    return 'This property has no approval threshold, so no estimate needs approval.'
  }
  const amount = formatMoney(workOrder.approval_threshold_cents, workOrder.property_currency)
  return `An estimate above ${amount} needs a property owner's approval before work goes ahead.`
}

function waitingText(workOrder: WorkOrder): string {
  if (workOrder.owner_names.length === 0) {
    return 'No property owner is set for this property, so nobody can approve this yet. Ask an administrator to add one.'
  }
  return `Waiting for ${workOrder.owner_names.join(' or ')}.`
}

export function EstimatePanel({ url, workOrder, onChanged }: EstimatePanelProps) {
  const [amount, setAmount] = useState('')
  const [provider, setProvider] = useState('')
  const [description, setDescription] = useState('')
  const { busy, error, run, fail } = useAction()
  const hasCurrent = workOrder.estimates.some((item) => item.current)

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const cents = parseMoneyToCents(amount)
    if (cents === null || cents < 1) {
      fail('Enter the estimate as an amount, such as 850 or 850.00.')
      return
    }
    if (description.trim().length < 3) {
      fail('Describe what the estimate covers.')
      return
    }
    const saved = await run(() =>
      api(`${url}/estimates`, {
        method: 'POST',
        body: {
          amount_cents: cents,
          description,
          provider_name: provider.trim() === '' ? null : provider,
        },
      }),
    )
    if (saved) {
      setAmount('')
      setProvider('')
      setDescription('')
      onChanged()
    }
  }

  return (
    <div className="space-y-4">
      {workOrder.approval_hold && (
        <div
          role="status"
          className="space-y-1 rounded border border-amber-300 bg-amber-50 p-4 text-sm"
        >
          <p className="font-medium">{workOrder.approval_hold}</p>
          {workOrder.estimates.some((item) => item.current && item.status === 'pending') && (
            <p>{waitingText(workOrder)}</p>
          )}
          {workOrder.estimates.some((item) => item.current && item.status === 'rejected') && (
            <p>Record a revised estimate to ask again, or cancel the work order.</p>
          )}
        </div>
      )}

      {workOrder.estimates.length === 0 ? (
        <p className="text-slate-600">No estimate has been recorded.</p>
      ) : (
        <EstimateVersions versions={workOrder.estimates} />
      )}

      {workOrder.can_record_estimate && (
        <form
          onSubmit={handleSubmit}
          aria-label={hasCurrent ? 'Revise the estimate' : 'Record an estimate'}
          className="space-y-3 rounded border border-slate-200 bg-white p-4"
        >
          <FormError message={error} />
          <p className="text-sm text-slate-600">{thresholdText(workOrder)}</p>
          <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
            <TextField
              id="estimate-amount"
              label={`Amount (${workOrder.property_currency})`}
              inputMode="decimal"
              placeholder="850.00"
              value={amount}
              onChange={setAmount}
            />
            <TextField
              id="estimate-provider"
              label="Quoted by (optional)"
              maxLength={200}
              value={provider}
              onChange={setProvider}
            />
          </div>
          <TextAreaField
            id="estimate-description"
            label="What it covers"
            maxLength={2000}
            rows={3}
            value={description}
            onChange={setDescription}
          />
          {hasCurrent && (
            <p className="text-sm text-slate-600">
              A revision replaces the current estimate. The earlier one stays on record.
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            {hasCurrent ? 'Record revised estimate' : 'Record estimate'}
          </button>
        </form>
      )}
    </div>
  )
}
