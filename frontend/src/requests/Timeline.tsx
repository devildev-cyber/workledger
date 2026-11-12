import type { RequestStatus, TimelineKind } from '../api/types.ts'
import { formatDate } from '../format.ts'
import { STATUS_LABELS } from './labels.ts'

export type TimelineItem = {
  id: string
  kind: TimelineKind
  body: string | null
  status: RequestStatus | null
  created_at: string
  who: string
  internal?: boolean
}

function headline(item: TimelineItem): string {
  if (item.kind === 'submitted') return 'Request submitted'
  if (item.kind === 'status_changed' && item.status) {
    return `Status changed to ${STATUS_LABELS[item.status]}`
  }
  return item.kind === 'note' ? 'Internal note' : 'Message'
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <ol aria-label="Timeline" className="space-y-3 border-l-2 border-slate-200 pl-4">
      {items.map((item) => (
        <li key={item.id} className="space-y-1">
          <p className="text-sm">
            <span className="font-medium">{headline(item)}</span>
            {item.internal && (
              <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                Internal
              </span>
            )}
          </p>
          {item.body && <p className="whitespace-pre-wrap text-sm text-slate-800">{item.body}</p>}
          <p className="text-xs text-slate-500">
            {item.who} · {formatDate(item.created_at)}
          </p>
        </li>
      ))}
    </ol>
  )
}
