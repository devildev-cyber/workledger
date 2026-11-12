const CSRF_HEADER = 'X-CSRF-Token'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// The token lives only in memory. The server returns it again whenever the session is
// restored, so a page reload does not need it stored anywhere.
let csrfToken: string | null = null
let unauthorizedHandler: (() => void) | null = null

export function setCsrfToken(token: string | null): void {
  csrfToken = token
}

/** Called when the server rejects a request because the session ended while signed in. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

type RequestOptions = {
  method?: string
  body?: unknown
}

function messageFromDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail
  }

  // FastAPI reports validation problems as a list of { loc, msg }.
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item.msg === 'string' ? item.msg : null))
      .filter((message): message is string => message !== null)
    return messages.length > 0 ? messages.join(' ') : null
  }

  return null
}

async function errorFrom(response: Response): Promise<ApiError> {
  let message: string | null = null
  try {
    const payload: unknown = await response.json()
    if (payload && typeof payload === 'object' && 'detail' in payload) {
      message = messageFromDetail(payload.detail)
    }
  } catch {
    // The body was empty or not JSON; the generic message below is used.
  }

  return new ApiError(response.status, message ?? 'Something went wrong. Please try again.')
}

export async function api<T = void>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {}

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (!SAFE_METHODS.has(method) && csrfToken) {
    headers[CSRF_HEADER] = csrfToken
  }

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }

  if (!response.ok) {
    // A 401 while we believed we were signed in means the session ended (expired or
    // signed out elsewhere). A 401 from the sign-in form itself is just a wrong password.
    if (response.status === 401 && csrfToken) {
      unauthorizedHandler?.()
    }
    throw await errorFrom(response)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}
