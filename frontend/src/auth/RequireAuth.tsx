import { Navigate, Outlet, useLocation } from 'react-router'

import { useAuth } from './auth-context.ts'

export function RequireAuth() {
  const { state } = useAuth()
  const location = useLocation()

  if (state.status === 'loading') {
    return (
      <p role="status" className="p-6 text-slate-600">
        Loading…
      </p>
    )
  }

  if (state.status === 'signed-out') {
    // Remember where the person was going so sign-in can take them back.
    const from = `${location.pathname}${location.search}${location.hash}`
    return <Navigate to="/sign-in" state={{ from }} replace />
  }

  return <Outlet />
}
