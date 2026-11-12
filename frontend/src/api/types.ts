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
