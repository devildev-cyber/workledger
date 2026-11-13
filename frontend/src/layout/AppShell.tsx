import { useState } from 'react'
import { Link, Outlet, useParams } from 'react-router'

import { useAuth, useCurrentUser } from '../auth/auth-context.ts'
import {
  approvalsPath,
  canInvite,
  canSeeDirectory,
  findMembership,
  isContractor,
  isPropertyOwner,
  isResident,
  myJobsPath,
  myRequestsPath,
  organizationPath,
  propertiesPath,
  requestsPath,
  workOrdersPath,
} from '../organizations/organizations.ts'
import { OrganizationSwitcher } from '../organizations/OrganizationSwitcher.tsx'

export function AppShell() {
  const user = useCurrentUser()
  const { signOut } = useAuth()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)
  const [signOutFailed, setSignOutFailed] = useState(false)

  const handleSignOut = async () => {
    setSignOutFailed(false)
    try {
      await signOut()
    } catch {
      setSignOutFailed(true)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex flex-wrap items-center gap-4 border-b border-slate-200 bg-white px-6 py-3">
        <Link to="/" className="text-lg font-semibold">
          WorkLedger
        </Link>
        <OrganizationSwitcher />
        {membership && (
          <nav aria-label="Main" className="flex gap-4">
            {canSeeDirectory(membership.roles) && (
              <>
                <Link to={requestsPath(membership.organization_id)}>Requests</Link>
                <Link to={workOrdersPath(membership.organization_id)}>Work orders</Link>
                <Link to={propertiesPath(membership.organization_id)}>Properties</Link>
                <Link to={`${organizationPath(membership.organization_id)}/residents`}>
                  Residents
                </Link>
              </>
            )}
            {isResident(membership.roles) && (
              <>
                <Link to={myRequestsPath(membership.organization_id)}>My requests</Link>
                <Link to={`${organizationPath(membership.organization_id)}/my-home`}>My home</Link>
              </>
            )}
            {isContractor(membership.roles) && (
              <Link to={myJobsPath(membership.organization_id)}>My jobs</Link>
            )}
            {isPropertyOwner(membership.roles) && (
              <Link to={approvalsPath(membership.organization_id)}>Approvals</Link>
            )}
            {canInvite(membership.roles) && (
              <Link to={`${organizationPath(membership.organization_id)}/people`}>People</Link>
            )}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span>{user.full_name}</span>
          <button
            type="button"
            onClick={handleSignOut}
            className="rounded border border-slate-300 px-3 py-1"
          >
            Sign out
          </button>
        </div>
      </header>

      {signOutFailed && (
        <p role="alert" className="bg-red-50 px-6 py-2 text-sm text-red-800">
          Could not sign out. Check your connection and try again.
        </p>
      )}

      <main className="mx-auto max-w-5xl p-6">
        <Outlet />
      </main>
    </div>
  )
}
