import { api } from '../api/client.ts'
import type { Member, SessionResponse } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useAuth, useCurrentUser } from '../auth/auth-context.ts'
import { MemberRow } from './MemberRow.tsx'

export function MembersSection({
  organizationId,
  organizationName,
}: {
  organizationId: string
  organizationName: string
}) {
  const user = useCurrentUser()
  const { setSession } = useAuth()
  const { data: members, error, loading, reload } = useApiData<Member[]>(
    `/organizations/${organizationId}/members`,
  )

  const handleChanged = async (member: Member) => {
    reload()

    // Changing your own roles, or leaving, changes what this browser may show.
    if (member.user_id === user.id) {
      try {
        setSession(await api<SessionResponse>('/auth/me'))
      } catch {
        // If this fails the next request will notice the session has changed.
      }
    }
  }

  return (
    <section aria-labelledby="members-heading" className="space-y-3">
      <h2 id="members-heading" className="text-xl font-semibold">
        Members
      </h2>

      {loading && (
        <p role="status" className="text-slate-600">
          Loading members…
        </p>
      )}
      {error && (
        <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {members && (
        <ul className="space-y-2">
          {members.map((member) => (
            <MemberRow
              key={member.id}
              member={member}
              organizationId={organizationId}
              organizationName={organizationName}
              isYou={member.user_id === user.id}
              onChanged={handleChanged}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
