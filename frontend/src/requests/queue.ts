import type { StaffRequestSummary, Urgency } from '../api/types.ts'
import { URGENCY_ORDER, URGENCY_SHORT } from './labels.ts'

export type GroupBy = 'none' | 'urgency' | 'property' | 'age'

// "Older than" choices, shared by the request and work order lists.
export const AGE_CHOICES = [
  { value: '1', label: 'Older than 1 day' },
  { value: '3', label: 'Older than 3 days' },
  { value: '7', label: 'Older than a week' },
  { value: '30', label: 'Older than a month' },
]

export type RequestGroup = { key: string; title: string; requests: StaffRequestSummary[] }

const DAY_MS = 24 * 60 * 60 * 1000

const AGE_BUCKETS = [
  { key: 'today', title: 'Today', maxDays: 1 },
  { key: 'week', title: 'Within a week', maxDays: 7 },
  { key: 'older', title: 'Older than a week', maxDays: Infinity },
]

function ageBucket(createdAt: string, now: Date): (typeof AGE_BUCKETS)[number] {
  const days = (now.getTime() - new Date(createdAt).getTime()) / DAY_MS
  return AGE_BUCKETS.find((bucket) => days < bucket.maxDays) ?? AGE_BUCKETS[2]
}

/** Splits a queue into labelled groups, most pressing first. Empty groups are left out. */
export function groupRequests(
  requests: StaffRequestSummary[],
  by: GroupBy,
  now: Date = new Date(),
): RequestGroup[] {
  if (by === 'none') {
    return [{ key: 'all', title: 'All', requests }]
  }

  if (by === 'urgency') {
    return URGENCY_ORDER.slice()
      .reverse()
      .map((urgency: Urgency) => ({
        key: urgency,
        title: URGENCY_SHORT[urgency],
        requests: requests.filter((request) => request.urgency === urgency),
      }))
      .filter((group) => group.requests.length > 0)
  }

  if (by === 'age') {
    // The oldest requests have waited longest, so they come first.
    return AGE_BUCKETS.slice()
      .reverse()
      .map((bucket) => ({
        key: bucket.key,
        title: bucket.title,
        requests: requests.filter((request) => ageBucket(request.created_at, now).key === bucket.key),
      }))
      .filter((group) => group.requests.length > 0)
  }

  const names = [...new Set(requests.map((request) => request.property_name))].sort((a, b) =>
    a.localeCompare(b),
  )
  return names.map((name) => ({
    key: name,
    title: name,
    requests: requests.filter((request) => request.property_name === name),
  }))
}
