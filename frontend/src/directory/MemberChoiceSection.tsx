import { useState } from 'react'

import { api } from '../api/client.ts'
import type { ManagerChoice } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'

export type MemberChoiceWording = {
  heading: string
  intro: string
  loading: string
  empty: string
  legend: string
  save: string
  saved: string
}

type MemberChoiceSectionProps = {
  url: string
  // Used for the heading's id, so two sections on one page stay distinct.
  name: string
  wording: MemberChoiceWording
}

/** Choosing which members of one kind are attached to a property. */
export function MemberChoiceSection({ url, name, wording }: MemberChoiceSectionProps) {
  const { data: choices, error: loadError, loading, reload } = useApiData<ManagerChoice[]>(url)
  // Only differences from what the server holds are kept here.
  const [changes, setChanges] = useState<Record<string, boolean>>({})
  const { busy, error, run } = useAction()
  const [saved, setSaved] = useState(false)

  const isAssigned = (choice: ManagerChoice) => changes[choice.membership_id] ?? choice.assigned

  const toggle = (choice: ManagerChoice, assigned: boolean) => {
    setSaved(false)
    setChanges((current) => ({ ...current, [choice.membership_id]: assigned }))
  }

  const save = async () => {
    if (!choices) return
    const membershipIds = choices.filter(isAssigned).map((choice) => choice.membership_id)
    const ok = await run(() => api(url, { method: 'PUT', body: { membership_ids: membershipIds } }))
    if (ok) {
      setChanges({})
      setSaved(true)
      reload()
    }
  }

  return (
    <section aria-labelledby={`${name}-heading`} className="space-y-3">
      <h2 id={`${name}-heading`} className="text-xl font-semibold">
        {wording.heading}
      </h2>
      <p className="text-sm text-slate-600">{wording.intro}</p>

      {loading && (
        <p role="status" className="text-slate-600">
          {wording.loading}
        </p>
      )}
      <FormError message={loadError ?? error} />

      {choices && choices.length === 0 && <p className="text-slate-600">{wording.empty}</p>}
      {choices && choices.length > 0 && (
        <fieldset className="space-y-2">
          <legend className="sr-only">{wording.legend}</legend>
          {choices.map((choice) => (
            <label key={choice.membership_id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isAssigned(choice)}
                onChange={(event) => toggle(choice, event.target.checked)}
              />
              {choice.full_name}
              <span className="text-slate-500">{choice.email}</span>
            </label>
          ))}
          <button
            type="button"
            onClick={save}
            disabled={busy}
            className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            {wording.save}
          </button>
          {saved && (
            <p role="status" className="text-sm text-green-800">
              {wording.saved}
            </p>
          )}
        </fieldset>
      )}
    </section>
  )
}
