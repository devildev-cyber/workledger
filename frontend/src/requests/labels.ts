import type { RequestCategory, RequestStatus, Urgency } from '../api/types.ts'

export const CATEGORY_LABELS: Record<RequestCategory, string> = {
  plumbing: 'Plumbing',
  electrical: 'Electrical',
  heating_cooling: 'Heating or cooling',
  appliances: 'Appliances',
  doors_windows: 'Doors or windows',
  pests: 'Pests',
  structure: 'Walls, ceilings or floors',
  other: 'Something else',
}

export const URGENCY_LABELS: Record<Urgency, string> = {
  routine: 'Routine, whenever convenient',
  soon: 'Soon, within a few days',
  urgent: 'Urgent, it is affecting daily life',
  emergency: 'Emergency, there is damage or danger',
}

// What a person sees on a badge, in words they would use themselves.
export const STATUS_LABELS: Record<RequestStatus, string> = {
  submitted: 'Received',
  in_review: 'In review',
  in_progress: 'In progress',
  resolved: 'Resolved',
  closed: 'Closed',
  cancelled: 'Withdrawn',
}

export const STATUS_ORDER: RequestStatus[] = [
  'submitted',
  'in_review',
  'in_progress',
  'resolved',
  'closed',
  'cancelled',
]

export const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS) as RequestCategory[]
export const URGENCY_ORDER = Object.keys(URGENCY_LABELS) as Urgency[]

// Files a request may carry. The server checks again from the file's own bytes.
export const ACCEPTED_FILE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
export const MAX_FILE_BYTES = 10 * 1024 * 1024
export const MAX_FILES = 10

export function describeFileProblem(file: File): string | null {
  if (!ACCEPTED_FILE_TYPES.includes(file.type)) {
    return `${file.name} is not a JPEG, PNG, WebP or PDF file.`
  }
  if (file.size > MAX_FILE_BYTES) {
    return `${file.name} is larger than 10 MB.`
  }
  if (file.size === 0) {
    return `${file.name} is empty.`
  }
  return null
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
