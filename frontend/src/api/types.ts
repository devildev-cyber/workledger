export type Role = 'administrator' | 'manager' | 'resident' | 'contractor' | 'property_owner'

export type Membership = {
  organization_id: string
  organization_name: string
  roles: Role[]
}

export type CurrentUser = {
  id: string
  email: string
  full_name: string
  memberships: Membership[]
}

export type SessionResponse = {
  user: CurrentUser
  csrf_token: string
}

export type InvitationPreview = {
  organization_id: string
  organization_name: string
  email: string
  roles: Role[]
  // True when the invited email already has an account, so only a sign-in is needed.
  has_account: boolean
}

export type Member = {
  id: string
  user_id: string
  email: string
  full_name: string
  roles: Role[]
  is_active: boolean
  joined_at: string
}

export type InvitationStatus = 'pending' | 'accepted' | 'revoked' | 'expired'

export type Invitation = {
  id: string
  email: string
  roles: Role[]
  status: InvitationStatus
  invited_by_name: string
  created_at: string
  expires_at: string
}

export type Building = { id: string; name: string }

export type Property = {
  id: string
  name: string
  street: string
  city: string
  region: string
  postal_code: string
  currency: string
  approval_threshold_cents: number | null
  unit_count: number
  buildings: Building[]
}

export type ResidentRef = { id: string; full_name: string }

export type Unit = {
  id: string
  property_id: string
  building_id: string | null
  label: string
  current_residents: ResidentRef[]
}

export type Tenancy = {
  id: string
  unit_id: string
  unit_label: string
  building_name: string | null
  property_id: string
  property_name: string
  move_in_date: string
  move_out_date: string | null
  is_current: boolean
}

export type Resident = {
  id: string
  full_name: string
  email: string | null
  phone: string | null
  access_instructions: string | null
  has_account: boolean
  tenancies: Tenancy[]
}

export type ManagerChoice = {
  membership_id: string
  full_name: string
  email: string
  assigned: boolean
}

export type MyHome = {
  tenancy_id: string
  unit_id: string
  property_name: string
  street: string
  city: string
  region: string
  postal_code: string
  building_name: string | null
  unit_label: string
  move_in_date: string
  move_out_date: string | null
}

export type RequestCategory =
  | 'plumbing'
  | 'electrical'
  | 'heating_cooling'
  | 'appliances'
  | 'doors_windows'
  | 'pests'
  | 'structure'
  | 'other'

export type Urgency = 'routine' | 'soon' | 'urgent' | 'emergency'

export type RequestStatus =
  'submitted' | 'in_review' | 'in_progress' | 'resolved' | 'closed' | 'cancelled' | 'declined'

export type TimelineKind = 'submitted' | 'status_changed' | 'message' | 'note'

export type RequestSummary = {
  id: string
  reference: string
  status: RequestStatus
  category: RequestCategory
  urgency: Urgency
  title: string
  property_name: string
  unit_label: string
  building_name: string | null
  created_at: string
  updated_at: string
}

export type Attachment = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  created_at: string
  // Only staff responses say who can see a file.
  visibility?: 'resident' | 'internal'
}

export type TimelineEntry = {
  id: string
  kind: TimelineKind
  body: string | null
  status: RequestStatus | null
  created_at: string
  author: string
}

export type ResidentRequest = RequestSummary & {
  description: string
  location: string | null
  access_notes: string | null
  can_cancel: boolean
  can_message: boolean
  timeline: TimelineEntry[]
  attachments: Attachment[]
}

export type WorkOrderStatus =
  | 'open'
  | 'assigned'
  | 'in_progress'
  | 'on_hold'
  | 'awaiting_approval'
  | 'ready_for_review'
  | 'completed'
  | 'closed'
  | 'cancelled'

export type WorkOrderLink = { id: string; reference: string; status: WorkOrderStatus }

export type StaffRequestSummary = RequestSummary & {
  property_id: string
  resident_name: string
  submitted_on_behalf: boolean
  work_order: WorkOrderLink | null
  // Not yet linked to a work order or another request, and still open.
  needs_triage: boolean
}

export type StaffTimelineEntry = {
  id: string
  kind: TimelineKind
  visibility: 'resident' | 'internal'
  body: string | null
  status: RequestStatus | null
  created_at: string
  author_name: string | null
}

export type StaffRequest = StaffRequestSummary & {
  duplicate_of: { id: string; reference: string } | null
  description: string
  location: string | null
  access_notes: string | null
  resident: {
    id: string
    full_name: string
    email: string | null
    phone: string | null
    access_instructions: string | null
    has_account: boolean
  }
  timeline: StaffTimelineEntry[]
  attachments: Attachment[]
}

export type WorkOrderSummary = {
  id: string
  reference: string
  title: string
  status: WorkOrderStatus
  priority: Urgency
  category: RequestCategory
  property_id: string
  property_name: string
  unit_label: string | null
  building_name: string | null
  due_date: string | null
  overdue: boolean
  request_count: number
  assignee_id: string | null
  assignee_name: string | null
  assignment_response: AssignmentResponse | null
  // Whole minor units (cents). Set once a manager has verified the work.
  final_cost_cents: number | null
  currency: string | null
  created_at: string
  updated_at: string
}

export type EntryKind =
  | 'created'
  | 'status_changed'
  | 'edited'
  | 'note'
  | 'request_linked'
  | 'assigned'
  | 'unassigned'
  | 'assignment_accepted'
  | 'assignment_declined'
  | 'progress'
  | 'clarification'
  | 'verified'
  | 'sent_back'
  | 'estimate_submitted'
  | 'estimate_approved'
  | 'estimate_rejected'

export type AssignmentResponse = 'pending' | 'accepted' | 'declined'

export type Assignment = {
  id: string
  contractor_id: string
  contractor_name: string
  assigned_by_name: string
  assigned_at: string
  response: AssignmentResponse
  responded_at: string | null
  decline_reason: string | null
  ended_at: string | null
  ended_reason: 'reassigned' | 'unassigned' | 'declined' | 'cancelled' | null
}

export type Contractor = {
  id: string
  full_name: string
  email: string
  active_jobs: number
}

export type WorkOrderAttachment = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  contractor_visible: boolean
  uploaded_by_name: string | null
  created_at: string
}

export type WorkOrderEntry = {
  id: string
  kind: EntryKind
  visibility: 'resident' | 'internal'
  body: string | null
  status: WorkOrderStatus | null
  // For edits: each changed field with its value before and after. For a verification:
  // the final cost and currency.
  details: Record<string, unknown> | null
  author_name: string | null
  created_at: string
}

export type LinkedRequest = {
  id: string
  reference: string
  title: string
  status: RequestStatus
  resident_name: string
}

export type WorkOrder = WorkOrderSummary & {
  scope: string
  linked_requests: LinkedRequest[]
  history: WorkOrderEntry[]
  // What this person can move it to by hand right now.
  allowed_statuses: WorkOrderStatus[]
  assignment: Assignment | null
  // Every assignment the work order has had, oldest first.
  assignment_history: Assignment[]
  attachments: WorkOrderAttachment[]
  property_currency: string
  resolution: string | null
  verified_by_name: string | null
  verified_at: string | null
  // Newest first. Every estimate the work order has had, with the owner's decision on each.
  estimates: Estimate[]
  approval_threshold_cents: number | null
  // The property owners who would decide, by name. Empty means nobody can yet.
  owner_names: string[]
  // Why work cannot go ahead yet, if it cannot.
  approval_hold: string | null
  can_record_estimate: boolean
  cost_check: CostCheck | null
}

export type EstimateStatus = 'pending' | 'approved' | 'rejected' | 'not_required'

export type Estimate = {
  id: string
  version: number
  amount_cents: number
  currency: string
  description: string
  provider_name: string | null
  status: EstimateStatus
  approval_required: boolean
  threshold_cents: number | null
  // Whether this is the estimate the work order is currently held to.
  current: boolean
  submitted_by_name: string
  submitted_at: string
  decided_by_name: string | null
  decided_at: string | null
  decision_reason: string | null
}

export type CostCheck = {
  estimate_cents: number | null
  over_estimate_cents: number | null
  above_approval: boolean
}

export type ApprovalSummary = {
  id: string
  version: number
  reference: string
  title: string
  work_order_status: WorkOrderStatus
  property_name: string
  location: string | null
  amount_cents: number
  currency: string
  status: EstimateStatus
  current: boolean
  // Whether this person can decide on it right now.
  decidable: boolean
  submitted_at: string
  decided_at: string | null
}

export type ApprovalVersion = {
  id: string
  version: number
  amount_cents: number
  currency: string
  description: string
  provider_name: string | null
  status: EstimateStatus
  approval_required: boolean
  current: boolean
  submitted_by_name: string
  submitted_at: string
  decided_by_name: string | null
  decided_at: string | null
  decision_reason: string | null
}

export type Approval = ApprovalSummary & {
  description: string
  provider_name: string | null
  submitted_by_name: string
  decided_by_name: string | null
  decision_reason: string | null
  threshold_cents: number | null
  scope: string
  category: RequestCategory
  priority: Urgency
  due_date: string | null
  street: string
  city: string
  region: string
  postal_code: string
  versions: ApprovalVersion[]
}

export type JobSummary = {
  id: string
  reference: string
  title: string
  status: WorkOrderStatus
  priority: Urgency
  category: RequestCategory
  due_date: string | null
  overdue: boolean
  property_name: string
  unit_label: string | null
  building_name: string | null
  response: AssignmentResponse
}

export type JobEntry = {
  id: string
  kind: EntryKind
  // Left out of a status change made by someone else.
  body: string | null
  status: WorkOrderStatus | null
  author: string
  created_at: string
}

export type JobAttachment = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  mine: boolean
  created_at: string
}

export type Job = JobSummary & {
  scope: string
  street: string
  city: string
  region: string
  postal_code: string
  // First names and entry instructions arrive only once the job is accepted.
  residents: string[]
  access_notes: string[]
  can_accept: boolean
  can_decline: boolean
  allowed_statuses: WorkOrderStatus[]
  timeline: JobEntry[]
  attachments: JobAttachment[]
}
