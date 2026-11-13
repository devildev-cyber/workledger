import { vi } from 'vitest'

import type { Membership, SessionResponse } from '../api/types.ts'

export type RecordedRequest = {
  method: string
  path: string
  headers: Record<string, string>
  body: unknown
}

type Reply = { status?: number; body?: unknown } | Error

type Handler = Reply | ((request: RecordedRequest) => Reply)

// Chrome that every screen loads, so tests about something else need not plan for it. A test
// that does care can still supply its own reply for the same key.
const SHARED_CHROME: [RegExp, unknown][] = [
  [
    /^GET \/api\/organizations\/[^/]+\/notifications\?unread_only=true$/,
    { items: [], unread_count: 0 },
  ],
  [/^GET \/api\/organizations\/[^/]+\/work-orders\?attention=(overdue|blocked)$/, []],
]

/**
 * Replaces fetch with a fake server. Keys look like "POST /api/auth/sign-in".
 * Requests nobody planned for fail the test instead of hitting the network.
 */
export function mockApi(routes: Record<string, Handler>) {
  const requests: RecordedRequest[] = []

  const fake = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request: RecordedRequest = {
      method: init?.method ?? 'GET',
      path: String(input),
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
    }
    const key = `${request.method} ${request.path}`
    const shared = SHARED_CHROME.find(([pattern]) => pattern.test(key))
    // Requests nobody asked about are not recorded, so tests can count what they did plan.
    if (!shared || routes[key]) requests.push(request)
    const handler = routes[key] ?? (shared ? { body: shared[1] } : undefined)
    if (!handler) {
      throw new Error(`Unexpected request: ${key}`)
    }

    const reply = typeof handler === 'function' ? handler(request) : handler
    if (reply instanceof Error) {
      throw reply
    }

    const status = reply.status ?? 200
    return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), { status })
  })

  vi.stubGlobal('fetch', fake)
  return { requests, fake }
}

export const HARBOR = { id: '11111111-1111-4111-8111-111111111111', name: 'Harbor Property Group' }
export const ELM = { id: '22222222-2222-4222-8222-222222222222', name: 'Elm Street Rentals' }

export function sessionFor(memberships: Membership[], csrfToken = 'csrf-123'): SessionResponse {
  return {
    user: {
      id: '99999999-9999-4999-8999-999999999999',
      email: 'ada@example.com',
      full_name: 'Ada Admin',
      memberships,
    },
    csrf_token: csrfToken,
  }
}

export const harborAdmin: Membership = {
  organization_id: HARBOR.id,
  organization_name: HARBOR.name,
  roles: ['administrator'],
}

export const elmManager: Membership = {
  organization_id: ELM.id,
  organization_name: ELM.name,
  roles: ['manager', 'resident'],
}

export const notSignedIn = { status: 401, body: { detail: 'Not authenticated' } }
