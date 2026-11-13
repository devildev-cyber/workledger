import { Link } from 'react-router'

import type { WorkOrderSummary } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { workOrdersPath } from '../organizations/organizations.ts'

const SHOWN = 5

/** Work that has passed its due date or cannot move until someone acts, for managers. */
export function AttentionSummary({ organizationId }: { organizationId: string }) {
  const base = `/organizations/${organizationId}/work-orders`
  const overdue = useApiData<WorkOrderSummary[]>(`${base}?attention=overdue`)
  const blocked = useApiData<WorkOrderSummary[]>(`${base}?attention=blocked`)

  const groups = [
    { key: 'overdue', title: 'Overdue', items: overdue.data ?? [] },
    { key: 'blocked', title: 'Blocked', items: blocked.data ?? [] },
  ].filter((group) => group.items.length > 0)

  if (groups.length === 0) return null

  return (
    <section aria-labelledby="attention-heading" className="space-y-3">
      <h2 id="attention-heading" className="text-xl font-semibold">
        Needs attention
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {groups.map((group) => (
          <div key={group.key} className="space-y-2 rounded border border-slate-200 bg-white p-4">
            <h3 className="font-semibold">
              <Link
                to={`${workOrdersPath(organizationId)}?show=${group.key}`}
                className="underline"
              >
                {group.title} ({group.items.length})
              </Link>
            </h3>
            <ul className="space-y-1 text-sm">
              {group.items.slice(0, SHOWN).map((item) => (
                <li key={item.id}>
                  <Link to={`${workOrdersPath(organizationId)}/${item.id}`} className="underline">
                    {item.reference}
                  </Link>{' '}
                  {item.title}
                  {item.blocked_reason && (
                    <span className="block text-xs text-amber-800">{item.blocked_reason}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}
