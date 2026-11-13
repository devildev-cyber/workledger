import { useEffect } from 'react'
import { Link, useLocation } from 'react-router'

import type { NotificationList } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { notificationsPath } from '../organizations/organizations.ts'

// How often the count is refreshed while the page stays open.
const REFRESH_MILLISECONDS = 60_000

/** The navigation link to a person's notifications, with how many they have not read. */
export function NotificationsLink({ organizationId }: { organizationId: string }) {
  const { pathname } = useLocation()
  const { data, reload } = useApiData<NotificationList>(
    `/organizations/${organizationId}/notifications?unread_only=true`,
  )

  // Moving between screens is when someone is most likely to have acted on something.
  useEffect(() => {
    reload()
  }, [pathname, reload])

  useEffect(() => {
    const timer = setInterval(reload, REFRESH_MILLISECONDS)
    return () => clearInterval(timer)
  }, [reload])

  const unread = data?.unread_count ?? 0

  return (
    <Link to={notificationsPath(organizationId)}>
      Notifications
      {unread > 0 && (
        <span className="ml-1 rounded-full bg-red-600 px-2 py-0.5 text-xs font-medium text-white">
          {unread}
          <span className="sr-only"> unread</span>
        </span>
      )}
    </Link>
  )
}
