import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, ApiError, setCsrfToken, setUnauthorizedHandler } from '../api/client.ts'
import type { SessionResponse } from '../api/types.ts'
import { AuthContext, type AuthContextValue, type AuthState } from './auth-context.ts'

function startSession(session: SessionResponse): AuthState {
  setCsrfToken(session.csrf_token)
  return { status: 'signed-in', user: session.user }
}

function endSession(): AuthState {
  setCsrfToken(null)
  return { status: 'signed-out' }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })

  // Ask the server whether the browser already has a valid session.
  useEffect(() => {
    let cancelled = false

    api<SessionResponse>('/auth/me')
      .then((session) => {
        if (!cancelled) setState(startSession(session))
      })
      .catch(() => {
        // No session, or the server could not be reached. Either way the sign-in form
        // comes next, and it reports a connection problem if there still is one.
        if (!cancelled) setState(endSession())
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => setState(endSession()))
    return () => setUnauthorizedHandler(null)
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const session = await api<SessionResponse>('/auth/sign-in', {
      method: 'POST',
      body: { email, password },
    })
    setState(startSession(session))
  }, [])

  const signOut = useCallback(async () => {
    try {
      await api('/auth/sign-out', { method: 'POST' })
    } catch (error) {
      // Already signed out on the server is the outcome we wanted; anything else is shown.
      if (!(error instanceof ApiError) || error.status !== 401) throw error
    }
    setState(endSession())
  }, [])

  const setSession = useCallback((session: SessionResponse | null) => {
    setState(session ? startSession(session) : endSession())
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ state, signIn, signOut, setSession }),
    [state, signIn, signOut, setSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
