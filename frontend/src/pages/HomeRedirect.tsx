import { Navigate } from 'react-router'

import { useCurrentUser } from '../auth/auth-context.ts'
import { organizationPath, startingMembership } from '../organizations/organizations.ts'

export function HomeRedirect() {
  const user = useCurrentUser()
  const membership = startingMembership(user)

  if (!membership) {
    return (
      <section className="space-y-3">
        <h1 className="text-2xl font-semibold">No organization yet</h1>
        <p className="text-slate-600">
          Your account does not belong to an organization. Ask an administrator to invite you.
        </p>
      </section>
    )
  }

  return <Navigate to={organizationPath(membership.organization_id)} replace />
}
