import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { api } from '../api/client.ts'
import type { Property, Unit } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { BuildingsSection } from '../directory/BuildingsSection.tsx'
import { ManagersSection } from '../directory/ManagersSection.tsx'
import { OwnersSection } from '../directory/OwnersSection.tsx'
import { PropertyForm } from '../directory/PropertyForm.tsx'
import type { PropertyValues } from '../directory/property-values.ts'
import { MaintenanceHistory } from '../review/MaintenanceHistory.tsx'
import { UnitsSection } from '../directory/UnitsSection.tsx'
import { addressLine } from '../format.ts'
import { formatMoney } from '../money.ts'
import {
  canManageMembers,
  canSeeDirectory,
  findMembership,
  propertiesPath,
} from '../organizations/organizations.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function PropertyPage() {
  const user = useCurrentUser()
  const { organizationId, propertyId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !propertyId || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return (
    <PropertyDetail
      organizationId={membership.organization_id}
      propertyId={propertyId}
      isAdministrator={canManageMembers(membership.roles)}
    />
  )
}

function PropertyDetail({
  organizationId,
  propertyId,
  isAdministrator,
}: {
  organizationId: string
  propertyId: string
  isAdministrator: boolean
}) {
  const url = `/organizations/${organizationId}/properties/${propertyId}`
  const property = useApiData<Property>(url)
  const units = useApiData<Unit[]>(`${url}/units`)
  const [editing, setEditing] = useState(false)

  // Missing, someone else's, and not assigned to this manager all look the same.
  if (property.error) {
    return <NotFoundPage />
  }
  if (!property.data) {
    return (
      <p role="status" className="text-slate-600">
        Loading property…
      </p>
    )
  }

  const current = property.data
  const reloadAll = () => {
    property.reload()
    units.reload()
  }

  const save = async (values: PropertyValues) => {
    await api(url, { method: 'PUT', body: values })
    setEditing(false)
    property.reload()
  }

  return (
    <div className="space-y-8">
      <div>
        <Link to={propertiesPath(organizationId)} className="text-sm text-slate-600 underline">
          All properties
        </Link>
        <h1 className="text-2xl font-semibold">{current.name}</h1>
      </div>

      <section aria-labelledby="details-heading" className="space-y-3">
        <h2 id="details-heading" className="text-xl font-semibold">
          Details
        </h2>
        {editing ? (
          <PropertyForm
            label="Edit property"
            initial={{
              name: current.name,
              street: current.street,
              city: current.city,
              region: current.region,
              postal_code: current.postal_code,
              currency: current.currency,
              approval_threshold_cents: current.approval_threshold_cents,
            }}
            submitLabel="Save changes"
            onSubmit={save}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
            <dt className="text-slate-600">Address</dt>
            <dd>{addressLine(current) || 'Not set'}</dd>
            <dt className="text-slate-600">Currency</dt>
            <dd>{current.currency}</dd>
            <dt className="text-slate-600">Approval threshold</dt>
            <dd>
              {current.approval_threshold_cents === null
                ? 'Not set'
                : formatMoney(current.approval_threshold_cents, current.currency)}
            </dd>
          </dl>
        )}
        {isAdministrator && !editing && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded border border-slate-300 px-3 py-1 text-sm"
          >
            Edit details
          </button>
        )}
      </section>

      <BuildingsSection
        url={url}
        buildings={current.buildings}
        isAdministrator={isAdministrator}
        onChanged={reloadAll}
      />
      <UnitsSection
        url={url}
        units={units.data}
        buildings={current.buildings}
        isAdministrator={isAdministrator}
        onChanged={reloadAll}
      />
      <MaintenanceHistory
        organizationId={organizationId}
        propertyId={propertyId}
        units={units.data}
      />
      {isAdministrator && <ManagersSection url={`${url}/managers`} />}
      {isAdministrator && <OwnersSection url={`${url}/owners`} />}
    </div>
  )
}
