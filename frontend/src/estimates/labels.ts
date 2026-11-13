import type { EstimateStatus } from '../api/types.ts'

export const ESTIMATE_STATUS_LABELS: Record<EstimateStatus, string> = {
  pending: 'Waiting for approval',
  approved: 'Approved',
  rejected: 'Rejected',
  not_required: 'No approval needed',
}
