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
