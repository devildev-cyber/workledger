import type { CurrencyTotal } from '../api/types.ts'
import { formatMoney } from '../money.ts'
import { organizationPath } from '../organizations/organizations.ts'

/** The server returns at most this many repeat issues, the most repeated first. */
export const REPEAT_ISSUES_SHOWN = 50

export type Period = { from: string; to: string; propertyId?: string }

export function helpPath(organizationId: string): string {
  return `${organizationPath(organizationId)}/help`
}

export function reportsPath(organizationId: string): string {
  return `${organizationPath(organizationId)}/reports`
}

/** Blank dates are left out, so the server's default period (the last 90 days) applies. */
export function periodQuery(period: Period): string {
  const query = new URLSearchParams()
  if (period.from) query.set('from', period.from)
  if (period.to) query.set('to', period.to)
  if (period.propertyId) query.set('property_id', period.propertyId)
  const text = query.toString()
  return text ? `?${text}` : ''
}

/** "in_progress" becomes "In progress". */
export function humanize(key: string): string {
  const text = key.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Hours are exact; days read better for anything slower than two days. */
export function formatHours(hours: number | null): string {
  if (hours === null) return 'No data'
  if (hours < 48) return `${hours} h`
  return `${Math.round((hours / 24) * 10) / 10} days`
}

/** One amount per currency, since different currencies are never added together. */
export function formatTotals(totals: CurrencyTotal[]): string {
  if (totals.length === 0) return 'None'
  return totals.map((item) => formatMoney(item.total_cents, item.currency)).join(' · ')
}
