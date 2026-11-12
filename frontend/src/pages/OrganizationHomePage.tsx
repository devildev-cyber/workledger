import { useEffect } from 'react'
import { useParams } from 'react-router'

import { useCurrentUser } from '../auth/auth-context.ts'
import { findMembership, rememberOrganization, roleLabel } from '../organizations/organizations.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function OrganizationHomePage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)
  const memberOrganizationId = membership?.organization_id

  useEffect(() => {
    if (memberOrganizationId) rememberOrganization(memberOrganizationId)
  }, [memberOrganizationId])

  // Same answer for an organization that does not exist and one the person is not part of.
  if (!membership) {
    return <NotFoundPage />
  }

  return (
    <section className="space-y-3">
      <h1 className="text-2xl font-semibold">{membership.organization_name}</h1>
      <p className="text-slate-600">
        Your roles: {membership.roles.map(roleLabel).join(', ')}
      </p>
      <p className="text-slate-600">
        Properties, requests, and work orders will appear here as they are built.
      </p>
    </section>
  )
}
