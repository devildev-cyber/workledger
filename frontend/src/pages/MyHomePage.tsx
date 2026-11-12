import { useParams } from 'react-router'

import type { MyHome } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { addressLine, formatDay } from '../format.ts'
import { findMembership, isResident } from '../organizations/organizations.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function MyHomePage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !isResident(membership.roles)) {
    return <NotFoundPage />
  }

  return <HomeList organizationId={membership.organization_id} />
}

function HomeList({ organizationId }: { organizationId: string }) {
  const { data: homes, error, loading } = useApiData<MyHome[]>(`/organizations/${organizationId}/my-home`)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">My home</h1>

      {loading && (
        <p role="status" className="text-slate-600">
          Loading your home…
        </p>
      )}
      <FormError message={error} />

      {homes && homes.length === 0 && (
        <p className="text-slate-600">
          No home is linked to your account yet. Contact your property manager and ask them to add
          you to your unit.
        </p>
      )}

      {homes && homes.length > 0 && (
        <ul className="space-y-3">
          {homes.map((home) => (
            <li key={home.tenancy_id} className="rounded border border-slate-200 bg-white p-4">
              <h2 className="text-lg font-medium">
                {home.building_name ? `${home.building_name} · ` : ''}
                {home.unit_label}, {home.property_name}
              </h2>
              <p className="text-sm text-slate-600">{addressLine(home) || 'No address on file'}</p>
              <p className="text-sm text-slate-700">Moved in {formatDay(home.move_in_date)}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
