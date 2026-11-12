import { ApiError } from './api/client.ts'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

export function formatDate(isoTimestamp: string): string {
  return dateFormat.format(new Date(isoTimestamp))
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
}
