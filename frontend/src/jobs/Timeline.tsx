import type { JobEntry } from '../api/types.ts'
import { formatDate } from '../format.ts'
import { WORK_ORDER_STATUS_LABELS } from '../workorders/labels.ts'
import { TIMELINE_HEADLINES } from './labels.ts'

function headline(entry: JobEntry): string {
  if (entry.kind === 'status_changed' && entry.status) {
    return `Status changed to ${WORK_ORDER_STATUS_LABELS[entry.status]}`
  }
  return TIMELINE_HEADLINES[entry.kind]
}

export function Timeline({ entries }: { entries: JobEntry[] }) {
  return (
    <ol aria-label="Job history" className="space-y-3 border-l-2 border-slate-200 pl-4">
      {entries.map((entry) => (
        <li key={entry.id} className="space-y-1">
          <p className="text-sm font-medium">{headline(entry)}</p>
          {entry.body && <p className="whitespace-pre-wrap text-sm text-slate-800">{entry.body}</p>}
          <p className="text-xs text-slate-500">
            {entry.author} · {formatDate(entry.created_at)}
          </p>
        </li>
      ))}
    </ol>
  )
}
