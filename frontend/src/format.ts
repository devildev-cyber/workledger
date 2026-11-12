import { ApiError } from './api/client.ts'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

export function formatDate(isoTimestamp: string): string {
  return dateFormat.format(new Date(isoTimestamp))
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
}

/** A date without a time, such as a move-in day. It must not shift with the time zone. */
export function formatDay(isoDay: string): string {
  const [year, month, day] = isoDay.split('-').map(Number)
  return dateFormat.format(new Date(year, month - 1, day))
}

export function todayInput(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export function addressLine(parts: { street: string; city: string; region: string; postal_code: string }) {
  const cityLine = [parts.city, [parts.region, parts.postal_code].filter(Boolean).join(' ')]
    .filter(Boolean)
    .join(', ')
  return [parts.street, cityLine].filter(Boolean).join(', ')
}
