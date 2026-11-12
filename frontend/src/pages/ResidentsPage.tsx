import { useParams } from 'react-router'

import { api } from '../api/client.ts'
import type { Property, Resident } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { ResidentCard } from '../directory/ResidentCard.tsx'
import { ResidentForm, type ResidentValues } from '../directory/ResidentForm.tsx'
import { canManageMembers, canSeeDirectory, findMembership } from '../organizations/organizations.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function ResidentsPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return (
    <ResidentsList
      organizationId={membership.organization_id}
      isAdministrator={canManageMembers(membership.roles)}
    />
  )
}

function ResidentsList({
  organizationId,
  isAdministrator,
}: {
  organizationId: string
  isAdministrator: boolean
}) {
  const base = `/organizations/${organizationId}`
  const residents = useApiData<Resident[]>(`${base}/residents`)
  const properties = useApiData<Property[]>(`${base}/properties`)

  const create = async (values: ResidentValues) => {
    await api(`${base}/residents`, { method: 'POST', body: values })
    residents.reload()
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Residents</h1>

      {residents.loading && (
        <p role="status" className="text-slate-600">
          Loading residents…
        </p>
      )}
      <FormError message={residents.error ?? properties.error} />

      {residents.data && residents.data.length === 0 && (
        <p className="text-slate-600">
          {isAdministrator ? 'No residents yet. Add the first one below.' : 'No residents to show yet.'}
        </p>
      )}

      {residents.data && residents.data.length > 0 && (
        <ul className="space-y-3">
          {residents.data.map((resident) => (
            <ResidentCard
              key={resident.id}
              organizationId={organizationId}
              resident={resident}
              properties={properties.data ?? []}
              isAdministrator={isAdministrator}
              onChanged={residents.reload}
            />
          ))}
        </ul>
      )}

      {isAdministrator && (
        <section aria-labelledby="add-resident-heading" className="space-y-2">
          <h2 id="add-resident-heading" className="text-xl font-semibold">
            Add a resident
          </h2>
          <ResidentForm label="Add resident" submitLabel="Add resident" onSubmit={create} />
        </section>
      )}
    </div>
  )
}
