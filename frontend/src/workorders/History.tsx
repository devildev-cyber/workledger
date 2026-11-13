import type { WorkOrderEntry } from '../api/types.ts'
import { formatDate, formatDay } from '../format.ts'
import { formatMoney } from '../money.ts'
import { authorLabel } from '../organizations/organizations.ts'
import { CATEGORY_LABELS, URGENCY_SHORT } from '../requests/labels.ts'
import { ENTRY_HEADLINES, FIELD_LABELS, WORK_ORDER_STATUS_LABELS } from './labels.ts'

function headline(entry: WorkOrderEntry): string {
  if (entry.kind === 'status_changed') {
    return entry.status
      ? `Status changed to ${WORK_ORDER_STATUS_LABELS[entry.status]}`
      : 'Status changed'
  }
  return ENTRY_HEADLINES[entry.kind]
}

// Edits are stored as plain values. Show them the way the rest of the page does.
function show(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return 'none'
  const text = String(value)
  if (field === 'category') return CATEGORY_LABELS[text as keyof typeof CATEGORY_LABELS] ?? text
  if (field === 'priority') return URGENCY_SHORT[text as keyof typeof URGENCY_SHORT] ?? text
  if (field === 'due_date') return formatDay(text)
  return text
}

export function History({ entries }: { entries: WorkOrderEntry[] }) {
  return (
    <ol aria-label="History" className="space-y-3 border-l-2 border-slate-200 pl-4">
      {entries.map((entry) => (
        <li key={entry.id} className="space-y-1">
          <p className="text-sm">
            <span className="font-medium">{headline(entry)}</span>
            {entry.kind === 'note' && (
              <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                {entry.visibility === 'internal' ? 'Internal' : 'Shared with residents'}
              </span>
            )}
          </p>
          {entry.body && <p className="whitespace-pre-wrap text-sm text-slate-800">{entry.body}</p>}
          {entry.kind === 'verified' && entry.details && (
            <p className="text-sm text-slate-800">
              Final cost:{' '}
              {typeof entry.details.final_cost_cents === 'number' &&
              typeof entry.details.currency === 'string'
                ? formatMoney(entry.details.final_cost_cents, entry.details.currency)
                : 'not recorded'}
            </p>
          )}
          {(entry.kind === 'estimate_submitted' ||
            entry.kind === 'estimate_approved' ||
            entry.kind === 'estimate_rejected') &&
            entry.details &&
            typeof entry.details.amount_cents === 'number' &&
            typeof entry.details.currency === 'string' && (
              <p className="text-sm text-slate-800">
                Estimate {String(entry.details.version)}:{' '}
                {formatMoney(entry.details.amount_cents, entry.details.currency)}
                {entry.kind === 'estimate_submitted' && entry.details.approval_required
                  ? ' (needs approval)'
                  : ''}
              </p>
            )}
          {entry.kind === 'edited' && entry.details && (
            <ul className="text-sm text-slate-800">
              {Object.entries(entry.details).map(([field, change]) => {
                const [before, after] = change as [unknown, unknown]
                return (
                  <li key={field}>
                    {FIELD_LABELS[field] ?? field}:{' '}
                    {field === 'scope'
                      ? 'updated'
                      : `${show(field, before)} → ${show(field, after)}`}
                  </li>
                )
              })}
            </ul>
          )}
          <p className="text-xs text-slate-500">
            {authorLabel(entry.author_name, entry.author_role)} · {formatDate(entry.created_at)}
          </p>
        </li>
      ))}
    </ol>
  )
}
