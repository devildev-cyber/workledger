import { useState } from 'react'

import { api } from '../api/client.ts'
import type { Member, Role } from '../api/types.ts'
import { errorMessage } from '../format.ts'
import { ALL_ROLES, roleLabel } from '../organizations/organizations.ts'
import { RoleCheckboxes } from './RoleCheckboxes.tsx'

type MemberRowProps = {
  member: Member
  organizationId: string
  organizationName: string
  isYou: boolean
  onChanged: (member: Member) => void
}

type Mode = 'viewing' | 'editing' | 'confirming-removal'

export function MemberRow({
  member,
  organizationId,
  organizationName,
  isYou,
  onChanged,
}: MemberRowProps) {
  const [mode, setMode] = useState<Mode>('viewing')
  const [roles, setRoles] = useState<Role[]>(member.roles)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const url = `/organizations/${organizationId}/members/${member.id}`

  const run = async (action: () => Promise<void>) => {
    setError(null)
    setBusy(true)
    try {
      await action()
      setMode('viewing')
      onChanged(member)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  const saveRoles = () => run(() => api(`${url}/roles`, { method: 'PUT', body: { roles } }))
  const remove = () => run(() => api(url, { method: 'DELETE' }))

  const startEditing = () => {
    setRoles(member.roles)
    setError(null)
    setMode('editing')
  }

  return (
    <li className="space-y-2 rounded border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="font-medium">
          {member.full_name}
          {isYou && <span className="ml-1 text-sm font-normal text-slate-500">(you)</span>}
        </span>
        <span className="text-sm text-slate-600">{member.email}</span>
        {!member.is_active && (
          <span className="rounded bg-amber-100 px-2 text-xs text-amber-900">Deactivated</span>
        )}
      </div>
      <p className="text-sm text-slate-700">Roles: {member.roles.map(roleLabel).join(', ')}</p>

      {error && (
        <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-800">
          {error}
        </p>
      )}

      {mode === 'viewing' && (
        <div className="flex gap-2 text-sm">
          <button
            type="button"
            onClick={startEditing}
            aria-label={`Edit roles for ${member.full_name}`}
            className="rounded border border-slate-300 px-3 py-1"
          >
            Edit roles
          </button>
          <button
            type="button"
            onClick={() => {
              setError(null)
              setMode('confirming-removal')
            }}
            aria-label={`Remove ${member.full_name}`}
            className="rounded border border-slate-300 px-3 py-1"
          >
            Remove
          </button>
        </div>
      )}

      {mode === 'editing' && (
        <div className="space-y-2">
          <RoleCheckboxes
            legend={`Roles for ${member.full_name}`}
            options={ALL_ROLES}
            selected={roles}
            onChange={setRoles}
          />
          <div className="flex gap-2 text-sm">
            <button
              type="button"
              onClick={saveRoles}
              disabled={busy || roles.length === 0}
              className="rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-60"
            >
              Save roles
            </button>
            <button
              type="button"
              onClick={() => setMode('viewing')}
              className="rounded border border-slate-300 px-3 py-1"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === 'confirming-removal' && (
        <div className="space-y-2">
          <p className="text-sm">
            Remove {isYou ? 'yourself' : member.full_name} from {organizationName}? Access ends
            immediately. The account itself is kept.
          </p>
          <div className="flex gap-2 text-sm">
            <button
              type="button"
              onClick={remove}
              disabled={busy}
              className="rounded bg-red-700 px-3 py-1 text-white disabled:opacity-60"
            >
              Confirm removal
            </button>
            <button
              type="button"
              onClick={() => setMode('viewing')}
              className="rounded border border-slate-300 px-3 py-1"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </li>
  )
}
