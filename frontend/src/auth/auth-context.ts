import { createContext, useContext } from 'react'

import type { CurrentUser } from '../api/types.ts'

export type AuthState =
  | { status: 'loading' }
  | { status: 'signed-out' }
  | { status: 'signed-in'; user: CurrentUser }

export type AuthContextValue = {
  state: AuthState
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return value
}

/** The signed-in user. Only call this below RequireAuth. */
export function useCurrentUser(): CurrentUser {
  const { state } = useAuth()
  if (state.status !== 'signed-in') {
    throw new Error('useCurrentUser needs a signed-in user')
  }
  return state.user
}
