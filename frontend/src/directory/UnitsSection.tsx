import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { Building, Unit } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'

type UnitsSectionProps = {
  url: string
  units: Unit[] | null
  buildings: Building[]
  isAdministrator: boolean
  onChanged: () => void
}

export function UnitsSection({ url, units, buildings, isAdministrator, onChanged }: UnitsSectionProps) {
  const [label, setLabel] = useState('')
  const [buildingId, setBuildingId] = useState('')
  const { busy, error, run } = useAction()

  const buildingNames = new Map(buildings.map((building) => [building.id, building.name]))

  const handleAdd: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const added = await run(() =>
      api(`${url}/units`, {
        method: 'POST',
        body: { label, building_id: buildingId === '' ? null : buildingId },
      }),
    )
    if (added) {
      setLabel('')
      onChanged()
    }
  }

  return (
    <section aria-labelledby="units-heading" className="space-y-3">
      <h2 id="units-heading" className="text-xl font-semibold">
        Units
      </h2>

      {units && units.length === 0 && <p className="text-slate-600">No units yet.</p>}
      {units && units.length > 0 && (
        <ul className="divide-y divide-slate-200 rounded border border-slate-200 bg-white">
          {units.map((unit) => (
            <li key={unit.id} className="flex flex-wrap items-baseline gap-x-4 px-4 py-2">
              <span className="font-medium">
                {unit.building_id ? `${buildingNames.get(unit.building_id) ?? ''} · ` : ''}
                {unit.label}
              </span>
              <span className="text-sm text-slate-600">
                {unit.current_residents.length === 0
                  ? 'Vacant'
                  : unit.current_residents.map((resident) => resident.full_name).join(', ')}
              </span>
            </li>
          ))}
        </ul>
      )}

      {isAdministrator && (
        <form onSubmit={handleAdd} aria-label="Add unit" className="flex flex-wrap items-end gap-2">
          <TextField id="unit-label" label="Unit" required maxLength={100} value={label} onChange={setLabel} />
          {buildings.length > 0 && (
            <div className="space-y-1">
              <label htmlFor="unit-building" className="block text-sm font-medium text-slate-700">
                Building
              </label>
              <select
                id="unit-building"
                value={buildingId}
                onChange={(event) => setBuildingId(event.target.value)}
                className="rounded border border-slate-300 bg-white px-3 py-2"
              >
                <option value="">No building</option>
                {buildings.map((building) => (
                  <option key={building.id} value={building.id}>
                    {building.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            Add unit
          </button>
          <FormError message={error} />
        </form>
      )}
    </section>
  )
}
