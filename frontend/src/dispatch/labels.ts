import type {
  Assignment,
  AssignmentResponse,
  WorkOrderStatus,
} from "../api/types.ts";

export const RESPONSE_LABELS: Record<AssignmentResponse, string> = {
  pending: "Waiting for a reply",
  accepted: "Accepted",
  declined: "Declined",
};

export const ENDED_LABELS: Record<
  NonNullable<Assignment["ended_reason"]>,
  string
> = {
  reassigned: "Reassigned",
  unassigned: "Contractor removed",
  declined: "Declined by the contractor",
  cancelled: "Work order cancelled",
};

// Mirrors the server (decision 0020), only to hide a panel that would be refused.
export const ASSIGNABLE_STATUSES: WorkOrderStatus[] = [
  "open",
  "assigned",
  "in_progress",
  "on_hold",
];

export const SHARE_WITH_CONTRACTOR = (share: boolean) => ({
  contractor_visible: share ? "true" : "false",
});
