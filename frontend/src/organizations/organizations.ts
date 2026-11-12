import type { CurrentUser, Membership, Role } from '../api/types.ts'

const LAST_ORGANIZATION_KEY = 'workledger.lastOrganizationId'

const ROLE_LABELS: Record<Role, string> = {
  administrator: 'Administrator',
  manager: 'Manager',
  resident: 'Resident',
  contractor: 'Contractor',
  property_owner: 'Property owner',
}

export function roleLabel(role: Role): string {
  return ROLE_LABELS[role] ?? role
}

export function organizationPath(organizationId: string): string {
  return `/organizations/${organizationId}`
}

export function findMembership(user: CurrentUser, organizationId: string | undefined) {
  return user.memberships.find((membership) => membership.organization_id === organizationId)
}

export function rememberOrganization(organizationId: string): void {
  try {
    localStorage.setItem(LAST_ORGANIZATION_KEY, organizationId)
  } catch {
    // Storage can be blocked; the person simply lands on their first organization next time.
  }
}

function recalledOrganization(): string | null {
  try {
    return localStorage.getItem(LAST_ORGANIZATION_KEY)
  } catch {
    return null
  }
}

/** The organization to open first: the one used last time if still a member, else the first. */
export function startingMembership(user: CurrentUser): Membership | undefined {
  return findMembership(user, recalledOrganization() ?? undefined) ?? user.memberships[0]
}

export const ALL_ROLES: Role[] = ['administrator', 'manager', 'resident', 'contractor', 'property_owner']

// Mirrors the server's rule (decision 0011), only to hide choices that would be refused.
const INVITABLE: Partial<Record<Role, Role[]>> = {
  administrator: ALL_ROLES,
  manager: ['resident', 'contractor'],
}

export function invitableRoles(heldRoles: Role[]): Role[] {
  return ALL_ROLES.filter((role) => heldRoles.some((held) => INVITABLE[held]?.includes(role)))
}

export function canManageMembers(roles: Role[]): boolean {
  return roles.includes('administrator')
}

export function canInvite(roles: Role[]): boolean {
  return roles.includes('administrator') || roles.includes('manager')
}
