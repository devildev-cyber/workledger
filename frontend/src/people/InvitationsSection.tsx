import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { Invitation, Role } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'
import { errorMessage, formatDate } from '../format.ts'
import { invitableRoles, roleLabel } from '../organizations/organizations.ts'
import { RoleCheckboxes } from './RoleCheckboxes.tsx'

const STATUS_LABELS: Record<Invitation['status'], string> = {
  pending: 'Pending',
  accepted: 'Accepted',
  revoked: 'Revoked',
  expired: 'Expired',
}

export function InvitationsSection({
  organizationId,
  heldRoles,
}: {
  organizationId: string
  heldRoles: Role[]
}) {
  const url = `/organizations/${organizationId}/invitations`
  const options = invitableRoles(heldRoles)
  const { data: invitations, error: loadError, loading, reload } = useApiData<Invitation[]>(url)

  const [email, setEmail] = useState('')
  const [roles, setRoles] = useState<Role[]>([])
  const [formError, setFormError] = useState<string | null>(null)
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [listError, setListError] = useState<string | null>(null)

  const handleInvite: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    setSentTo(null)

    if (roles.length === 0) {
      setFormError('Choose at least one role.')
      return
    }

    setFormError(null)
    setSending(true)
    try {
      await api(url, { method: 'POST', body: { email: email.trim(), roles } })
      setSentTo(email.trim())
      setEmail('')
      setRoles([])
      reload()
    } catch (caught) {
      setFormError(errorMessage(caught))
    } finally {
      setSending(false)
    }
  }

  const handleRevoke = async (invitation: Invitation) => {
    setListError(null)
    try {
      await api(`${url}/${invitation.id}`, { method: 'DELETE' })
      reload()
    } catch (caught) {
      setListError(errorMessage(caught))
    }
  }

  return (
    <section aria-labelledby="invitations-heading" className="space-y-4">
      <h2 id="invitations-heading" className="text-xl font-semibold">
        Invitations
      </h2>

      <form
        onSubmit={handleInvite}
        aria-label="Invite someone"
        className="space-y-3 rounded border border-slate-200 bg-white p-4"
      >
        <FormError message={formError} />
        {sentTo && (
          <p role="status" className="rounded bg-green-50 p-3 text-sm text-green-900">
            Invitation sent to {sentTo}.
          </p>
        )}
        <TextField
          id="invite-email"
          label="Email address"
          type="email"
          required
          value={email}
          onChange={setEmail}
        />
        <RoleCheckboxes legend="Roles" options={options} selected={roles} onChange={setRoles} />
        <button
          type="submit"
          disabled={sending}
          className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {sending ? 'Sending…' : 'Send invitation'}
        </button>
      </form>

      {loading && (
        <p role="status" className="text-slate-600">
          Loading invitations…
        </p>
      )}
      <FormError message={loadError ?? listError} />

      {invitations && invitations.length === 0 && (
        <p className="text-slate-600">No invitations yet.</p>
      )}
      {invitations && invitations.length > 0 && (
        <ul className="space-y-2">
          {invitations.map((invitation) => (
            <li
              key={invitation.id}
              className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-slate-200 bg-white p-3 text-sm"
            >
              <span className="font-medium">{invitation.email}</span>
              <span>{invitation.roles.map(roleLabel).join(', ')}</span>
              <span className="rounded bg-slate-100 px-2">{STATUS_LABELS[invitation.status]}</span>
              <span className="text-slate-600">
                Invited by {invitation.invited_by_name}
                {invitation.status === 'pending' && `, expires ${formatDate(invitation.expires_at)}`}
              </span>
              {invitation.status === 'pending' && (
                <button
                  type="button"
                  onClick={() => handleRevoke(invitation)}
                  aria-label={`Revoke invitation for ${invitation.email}`}
                  className="ml-auto rounded border border-slate-300 px-3 py-1"
                >
                  Revoke
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
