import { Link, useParams } from 'react-router'

import { api } from '../api/client.ts'
import type { Property } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { PropertyForm } from '../directory/PropertyForm.tsx'
import type { PropertyValues } from '../directory/property-values.ts'
import { addressLine } from '../format.ts'
import {
  canManageMembers,
  canSeeDirectory,
  findMembership,
  propertiesPath,
} from '../organizations/organizations.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function PropertiesPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return (
    <PropertiesList
      organizationId={membership.organization_id}
      isAdministrator={canManageMembers(membership.roles)}
    />
  )
}

function PropertiesList({
  organizationId,
  isAdministrator,
}: {
  organizationId: string
  isAdministrator: boolean
}) {
  const url = `/organizations/${organizationId}/properties`
  const { data: properties, error, loading, reload } = useApiData<Property[]>(url)

  const create = async (values: PropertyValues) => {
    await api(url, { method: 'POST', body: values })
    reload()
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Properties</h1>

      {loading && (
        <p role="status" className="text-slate-600">
          Loading properties…
        </p>
      )}
      {error && (
        <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {properties && properties.length === 0 && (
        <p className="text-slate-600">
          {isAdministrator
            ? 'No properties yet. Add the first one below.'
            : 'No properties are assigned to you yet. Ask an administrator.'}
        </p>
      )}

      {properties && properties.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2">
          {properties.map((property) => (
            <li key={property.id} className="rounded border border-slate-200 bg-white p-4">
              <Link
                to={`${propertiesPath(organizationId)}/${property.id}`}
                className="text-lg font-medium underline"
              >
                {property.name}
              </Link>
              <p className="text-sm text-slate-600">{addressLine(property) || 'No address yet'}</p>
              <p className="text-sm text-slate-700">
                {property.unit_count} {property.unit_count === 1 ? 'unit' : 'units'}
              </p>
            </li>
          ))}
        </ul>
      )}

      {isAdministrator && (
        <section aria-labelledby="add-property-heading" className="space-y-2">
          <h2 id="add-property-heading" className="text-xl font-semibold">
            Add a property
          </h2>
          <PropertyForm label="Add property" submitLabel="Add property" onSubmit={create} />
        </section>
      )}
    </div>
  )
}
