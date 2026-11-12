import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { Building } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'

type BuildingsSectionProps = {
  url: string
  buildings: Building[]
  isAdministrator: boolean
  onChanged: () => void
}

export function BuildingsSection({ url, buildings, isAdministrator, onChanged }: BuildingsSectionProps) {
  const [name, setName] = useState('')
  const { busy, error, run } = useAction()

  const handleAdd: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const added = await run(() => api(`${url}/buildings`, { method: 'POST', body: { name } }))
    if (added) {
      setName('')
      onChanged()
    }
  }

  return (
    <section aria-labelledby="buildings-heading" className="space-y-3">
      <h2 id="buildings-heading" className="text-xl font-semibold">
        Buildings
      </h2>
      {buildings.length === 0 ? (
        <p className="text-slate-600">No separate buildings. Units belong to the property directly.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {buildings.map((building) => (
            <li key={building.id} className="rounded bg-slate-100 px-3 py-1 text-sm">
              {building.name}
            </li>
          ))}
        </ul>
      )}
      {isAdministrator && (
        <form onSubmit={handleAdd} aria-label="Add building" className="flex flex-wrap items-end gap-2">
          <TextField id="building-name" label="Building name" required value={name} onChange={setName} />
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            Add building
          </button>
          <FormError message={error} />
        </form>
      )}
    </section>
  )
}
