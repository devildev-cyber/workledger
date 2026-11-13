import { Link, useNavigate, useParams } from 'react-router'

import { api } from '../api/client.ts'
import type { AppNotification, NotificationList, NotificationPreferences } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { formatDate } from '../format.ts'
import { findMembership } from '../organizations/organizations.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function NotificationsPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership) {
    return <NotFoundPage />
  }

  return <NotificationInbox organizationId={membership.organization_id} />
}

function NotificationInbox({ organizationId }: { organizationId: string }) {
  const base = `/organizations/${organizationId}/notifications`
  const inbox = useApiData<NotificationList>(base)
  const preferences = useApiData<NotificationPreferences>(`${base}/preferences`)
  const action = useAction()
  const navigate = useNavigate()

  const open = async (item: AppNotification) => {
    // Opening a notification marks it read first, so the unread count is right on the next
    // screen. If that fails the notification stays unread, and the link still works.
    if (!item.read) {
      await api(`${base}/${item.id}/read`, { method: 'POST' }).catch(() => undefined)
    }
    await navigate(item.path)
  }

  const markAllRead = async () => {
    if (await action.run(() => api(`${base}/read`, { method: 'POST' }))) inbox.reload()
  }

  const setEmail = async (enabled: boolean) => {
    if (
      await action.run(() =>
        api(`${base}/preferences`, { method: 'PUT', body: { email_enabled: enabled } }),
      )
    ) {
      preferences.reload()
    }
  }

  const items = inbox.data?.items ?? []
  const unread = inbox.data?.unread_count ?? 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-semibold">Notifications</h1>
        {unread > 0 && (
          <button
            type="button"
            onClick={markAllRead}
            disabled={action.busy}
            className="rounded border border-slate-300 px-3 py-1 text-sm"
          >
            Mark all as read
          </button>
        )}
      </div>

      <FormError message={inbox.error ?? action.error} />

      {preferences.data && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={preferences.data.email_enabled}
            disabled={action.busy}
            onChange={(event) => setEmail(event.target.checked)}
          />
          Also email me these notifications
        </label>
      )}

      {inbox.loading && (
        <p role="status" className="text-slate-600">
          Loading notifications…
        </p>
      )}

      {inbox.data && items.length === 0 && (
        <p className="text-slate-600">
          Nothing yet. You will be told here when something needs you.
        </p>
      )}

      {items.length > 0 && (
        <ul className="divide-y divide-slate-200 rounded border border-slate-200 bg-white">
          {items.map((item) => (
            <li key={item.id}>
              <Link
                to={item.path}
                onClick={(event) => {
                  // Let the browser handle opening in a new tab or window.
                  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return
                  event.preventDefault()
                  void open(item)
                }}
                className="flex items-baseline justify-between gap-4 px-4 py-3"
              >
                <span className={item.read ? 'text-slate-700' : 'font-semibold'}>
                  {!item.read && <span className="sr-only">Unread: </span>}
                  {item.title}
                </span>
                <span className="shrink-0 text-xs text-slate-500">
                  {formatDate(item.created_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
