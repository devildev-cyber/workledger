import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { Property, Resident, Tenancy } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'
import { formatDay, todayInput } from '../format.ts'
import { MoveInForm } from './MoveInForm.tsx'
import { ResidentForm, type ResidentValues } from './ResidentForm.tsx'

type ResidentCardProps = {
  organizationId: string
  resident: Resident
  properties: Property[]
  isAdministrator: boolean
  onChanged: () => void
}

type Mode = 'view' | 'edit' | 'move-in'

export function ResidentCard({
  organizationId,
  resident,
  properties,
  isAdministrator,
  onChanged,
}: ResidentCardProps) {
  const [mode, setMode] = useState<Mode>('view')

  const save = async (values: ResidentValues) => {
    await api(`/organizations/${organizationId}/residents/${resident.id}`, {
      method: 'PUT',
      body: values,
    })
    setMode('view')
    onChanged()
  }

  if (mode === 'edit') {
    return (
      <li>
        <ResidentForm
          label={`Edit ${resident.full_name}`}
          initial={{
            full_name: resident.full_name,
            email: resident.email ?? '',
            phone: resident.phone ?? '',
            access_instructions: resident.access_instructions ?? '',
          }}
          submitLabel="Save changes"
          onSubmit={save}
          onCancel={() => setMode('view')}
        />
      </li>
    )
  }

  return (
    <li className="space-y-3 rounded border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h3 className="text-lg font-medium">{resident.full_name}</h3>
        {resident.has_account && (
          <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-900">Has account</span>
        )}
      </div>

      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-slate-600">Email</dt>
        <dd>{resident.email ?? 'Not set'}</dd>
        <dt className="text-slate-600">Phone</dt>
        <dd>{resident.phone ?? 'Not set'}</dd>
        <dt className="text-slate-600">Access instructions</dt>
        <dd>{resident.access_instructions ?? 'Not set'}</dd>
      </dl>

      {resident.tenancies.length === 0 ? (
        <p className="text-sm text-slate-600">Not placed in any unit.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {resident.tenancies.map((tenancy) => (
            <TenancyRow
              key={tenancy.id}
              organizationId={organizationId}
              tenancy={tenancy}
              isAdministrator={isAdministrator}
              onChanged={onChanged}
            />
          ))}
        </ul>
      )}

      {isAdministrator && mode === 'view' && (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setMode('edit')}
            aria-label={`Edit ${resident.full_name}`}
            className="rounded border border-slate-300 px-3 py-1 text-sm"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={() => setMode('move-in')}
            aria-label={`Move in ${resident.full_name}`}
            className="rounded border border-slate-300 px-3 py-1 text-sm"
          >
            Move in
          </button>
        </div>
      )}

      {mode === 'move-in' && (
        <MoveInForm
          organizationId={organizationId}
          residentId={resident.id}
          residentName={resident.full_name}
          properties={properties}
          onDone={() => {
            setMode('view')
            onChanged()
          }}
          onCancel={() => setMode('view')}
        />
      )}
    </li>
  )
}

function TenancyRow({
  organizationId,
  tenancy,
  isAdministrator,
  onChanged,
}: {
  organizationId: string
  tenancy: Tenancy
  isAdministrator: boolean
  onChanged: () => void
}) {
  const [ending, setEnding] = useState(false)
  const [moveOut, setMoveOut] = useState(todayInput())
  const { busy, error, run } = useAction()

  const place = `${tenancy.building_name ? `${tenancy.building_name} · ` : ''}${tenancy.unit_label}, ${tenancy.property_name}`

  const handleEnd: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const ended = await run(() =>
      api(`/organizations/${organizationId}/tenancies/${tenancy.id}/end`, {
        method: 'POST',
        body: { move_out_date: moveOut },
      }),
    )
    if (ended) {
      setEnding(false)
      onChanged()
    }
  }

  return (
    <li className="space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="font-medium">{place}</span>
        <span className="text-slate-600">
          {formatDay(tenancy.move_in_date)} to{' '}
          {tenancy.move_out_date ? formatDay(tenancy.move_out_date) : 'present'}
        </span>
        {tenancy.is_current && (
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">Current</span>
        )}
        {isAdministrator && tenancy.move_out_date === null && !ending && (
          <button
            type="button"
            onClick={() => setEnding(true)}
            aria-label={`Record move-out from ${place}`}
            className="rounded border border-slate-300 px-2 py-0.5 text-xs"
          >
            Record move-out
          </button>
        )}
      </div>
      {ending && (
        <form
          onSubmit={handleEnd}
          aria-label={`Move out from ${place}`}
          className="flex flex-wrap items-end gap-2"
        >
          <TextField
            id={`move-out-${tenancy.id}`}
            label="Move-out date"
            type="date"
            required
            value={moveOut}
            onChange={setMoveOut}
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            Save move-out
          </button>
          <button
            type="button"
            onClick={() => setEnding(false)}
            className="rounded border border-slate-300 px-4 py-2"
          >
            Cancel
          </button>
        </form>
      )}
      <FormError message={error} />
    </li>
  )
}
