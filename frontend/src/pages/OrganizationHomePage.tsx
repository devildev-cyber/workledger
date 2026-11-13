import { useEffect } from 'react'
import { Link, useParams } from 'react-router'

import { useCurrentUser } from '../auth/auth-context.ts'
import {
  approvalsPath,
  canSeeDirectory,
  findMembership,
  isContractor,
  isPropertyOwner,
  isResident,
  myJobsPath,
  myRequestsPath,
  rememberOrganization,
  requestsPath,
  roleLabel,
} from '../organizations/organizations.ts'
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
      <p className="text-slate-600">Your roles: {membership.roles.map(roleLabel).join(', ')}</p>
      {isResident(membership.roles) && (
        <p>
          <Link to={`${myRequestsPath(membership.organization_id)}/new`} className="underline">
            Report a problem
          </Link>
        </p>
      )}
      {isContractor(membership.roles) && (
        <p>
          <Link to={myJobsPath(membership.organization_id)} className="underline">
            See my jobs
          </Link>
        </p>
      )}
      {isPropertyOwner(membership.roles) && (
        <p>
          <Link to={approvalsPath(membership.organization_id)} className="underline">
            See estimates waiting for approval
          </Link>
        </p>
      )}
      {canSeeDirectory(membership.roles) && (
        <p>
          <Link to={requestsPath(membership.organization_id)} className="underline">
            See reported problems
          </Link>
        </p>
      )}
      <p className="text-slate-600">Work orders will appear here as they are built.</p>
    </section>
  )
}
