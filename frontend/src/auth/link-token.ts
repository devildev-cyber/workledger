import { useLocation } from 'react-router'

/**
 * The secret from an emailed link, which sits after the "#" (for example
 * /password-reset#token=abc). Browsers never send that part to a server.
 */
export function useLinkToken(): string | null {
  const { hash } = useLocation()
  return new URLSearchParams(hash.replace(/^#/, '')).get('token') || null
}
