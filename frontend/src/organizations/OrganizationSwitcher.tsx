import { useNavigate, useParams } from 'react-router'

import { useCurrentUser } from '../auth/auth-context.ts'
import { organizationPath } from './organizations.ts'

export function OrganizationSwitcher() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const { organizationId } = useParams()

  if (user.memberships.length === 0) {
    return null
  }

  if (user.memberships.length === 1) {
    return <span className="font-medium">{user.memberships[0].organization_name}</span>
  }

  const current = user.memberships.some((m) => m.organization_id === organizationId)

  return (
    <select
      aria-label="Organization"
      value={current ? organizationId : ''}
      onChange={(event) => navigate(organizationPath(event.target.value))}
      className="rounded border border-slate-300 bg-white px-2 py-1"
    >
      {!current && (
        <option value="" disabled>
          Choose an organization
        </option>
      )}
      {user.memberships.map((membership) => (
        <option key={membership.organization_id} value={membership.organization_id}>
          {membership.organization_name}
        </option>
      ))}
    </select>
  )
}
