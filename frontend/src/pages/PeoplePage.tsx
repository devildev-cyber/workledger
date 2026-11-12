import { useParams } from 'react-router'

import { useCurrentUser } from '../auth/auth-context.ts'
import { canInvite, canManageMembers, findMembership } from '../organizations/organizations.ts'
import { InvitationsSection } from '../people/InvitationsSection.tsx'
import { MembersSection } from '../people/MembersSection.tsx'
import { NotFoundPage } from './NotFoundPage.tsx'

export function PeoplePage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  // Roles without any people tools see the same page as for an address that does not exist.
  if (!membership || !canInvite(membership.roles)) {
    return <NotFoundPage />
  }

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold">People</h1>
      {canManageMembers(membership.roles) ? (
        <MembersSection
          organizationId={membership.organization_id}
          organizationName={membership.organization_name}
        />
      ) : (
        <p className="text-slate-600">
          You can invite residents and contractors and see the invitations you sent.
        </p>
      )}
      <InvitationsSection
        organizationId={membership.organization_id}
        heldRoles={membership.roles}
      />
    </div>
  )
}
