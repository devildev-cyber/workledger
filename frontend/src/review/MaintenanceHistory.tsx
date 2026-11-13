import { useState } from 'react'
import { Link } from 'react-router'

import type { Unit, WorkOrderSummary } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { formatDate } from '../format.ts'
import { formatMoney } from '../money.ts'
import { workOrdersPath } from '../organizations/organizations.ts'
import { CATEGORY_LABELS } from '../requests/labels.ts'
import { WorkOrderStatusBadge } from '../workorders/WorkOrderStatusBadge.tsx'

type MaintenanceHistoryProps = {
  organizationId: string
  propertyId: string
  units: Unit[] | null
}

/** Work that was done at a property, newest first, narrowed to one unit if asked. */
export function MaintenanceHistory({ organizationId, propertyId, units }: MaintenanceHistoryProps) {
  const [unitId, setUnitId] = useState('')
  const query = new URLSearchParams({ property_id: propertyId, history_only: 'true' })
  if (unitId) query.set('unit_id', unitId)
  const { data, error, loading } = useApiData<WorkOrderSummary[]>(
    `/organizations/${organizationId}/work-orders?${query.toString()}`,
  )

  return (
    <section aria-labelledby="history-heading" className="space-y-3">
      <h2 id="history-heading" className="text-xl font-semibold">
        Maintenance history
      </h2>
      <div className="max-w-xs">
        <SelectField
          id="history-unit"
          label="Unit"
          placeholder="Whole property"
          value={unitId}
          options={(units ?? []).map((unit) => ({ value: unit.id, label: unit.label }))}
          onChange={setUnitId}
        />
      </div>
      <FormError message={error} />
      {loading && (
        <p role="status" className="text-slate-600">
          Loading history…
        </p>
      )}
      {data && data.length === 0 && (
        <p className="text-slate-600">
          No finished work yet{unitId ? ' for this unit' : ''}. Work appears here once a manager
          verifies it.
        </p>
      )}
      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-3 py-2">Work order</th>
                <th className="px-3 py-2">Unit</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Cost</th>
                <th className="px-3 py-2">Last update</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {data.map((item) => (
                <tr key={item.id}>
                  <td className="px-3 py-2">
                    <Link to={`${workOrdersPath(organizationId)}/${item.id}`} className="underline">
                      {item.title}
                    </Link>
                    <span className="block text-xs text-slate-500">
                      {item.reference} · {CATEGORY_LABELS[item.category]}
                    </span>
                  </td>
                  <td className="px-3 py-2">{item.unit_label ?? 'Common areas'}</td>
                  <td className="px-3 py-2">
                    <WorkOrderStatusBadge status={item.status} />
                  </td>
                  <td className="px-3 py-2">
                    {item.final_cost_cents !== null && item.currency
                      ? formatMoney(item.final_cost_cents, item.currency)
                      : '—'}
                  </td>
                  <td className="px-3 py-2">{formatDate(item.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
