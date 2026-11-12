import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { Property, Unit } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'
import { todayInput } from '../format.ts'

type MoveInFormProps = {
  organizationId: string
  residentId: string
  residentName: string
  properties: Property[]
  onDone: () => void
  onCancel: () => void
}

export function MoveInForm({
  organizationId,
  residentId,
  residentName,
  properties,
  onDone,
  onCancel,
}: MoveInFormProps) {
  const [propertyId, setPropertyId] = useState('')
  const [unitId, setUnitId] = useState('')
  const [moveIn, setMoveIn] = useState(todayInput())
  const { busy, error, run } = useAction()

  // Units are fetched only once a property is chosen.
  const units = useApiData<Unit[]>(
    propertyId ? `/organizations/${organizationId}/properties/${propertyId}/units` : null,
  )

  const buildingNames = new Map(
    (properties.find((property) => property.id === propertyId)?.buildings ?? []).map((building) => [
      building.id,
      building.name,
    ]),
  )

  const choose = (value: string) => {
    setPropertyId(value)
    setUnitId('')
  }

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const moved = await run(() =>
      api(`/organizations/${organizationId}/tenancies`, {
        method: 'POST',
        body: { unit_id: unitId, resident_id: residentId, move_in_date: moveIn },
      }),
    )
    if (moved) onDone()
  }

  const selectClass = 'w-full rounded border border-slate-300 bg-white px-3 py-2'

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={`Move in ${residentName}`}
      className="space-y-3 rounded border border-slate-200 bg-slate-50 p-4"
    >
      <FormError message={error ?? units.error} />
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <label htmlFor={`move-property-${residentId}`} className="block text-sm font-medium text-slate-700">
            Property
          </label>
          <select
            id={`move-property-${residentId}`}
            required
            value={propertyId}
            onChange={(event) => choose(event.target.value)}
            className={selectClass}
          >
            <option value="">Choose a property</option>
            {properties.map((property) => (
              <option key={property.id} value={property.id}>
                {property.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor={`move-unit-${residentId}`} className="block text-sm font-medium text-slate-700">
            Unit
          </label>
          <select
            id={`move-unit-${residentId}`}
            required
            disabled={!propertyId}
            value={unitId}
            onChange={(event) => setUnitId(event.target.value)}
            className={selectClass}
          >
            <option value="">Choose a unit</option>
            {(units.data ?? []).map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.building_id ? `${buildingNames.get(unit.building_id) ?? ''} · ` : ''}
                {unit.label}
              </option>
            ))}
          </select>
        </div>
        <TextField
          id={`move-date-${residentId}`}
          label="Move-in date"
          type="date"
          required
          value={moveIn}
          onChange={setMoveIn}
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          Move in
        </button>
        <button type="button" onClick={onCancel} className="rounded border border-slate-300 px-4 py-2">
          Cancel
        </button>
      </div>
    </form>
  )
}
