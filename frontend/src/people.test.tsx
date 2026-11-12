import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type { Invitation, Member, Membership, Role } from './api/types.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ME = '99999999-9999-4999-8999-999999999999'
const PEOPLE = `/organizations/${HARBOR.id}/people`
const MEMBERS_URL = `GET /api/organizations/${HARBOR.id}/members`
const INVITATIONS_URL = `/api/organizations/${HARBOR.id}/invitations`

function member(id: string, name: string, roles: Role[], userId = `user-${id}`): Member {
  return {
    id,
    user_id: userId,
    email: `${name.split(' ')[0].toLowerCase()}@example.com`,
    full_name: name,
    roles,
    is_active: true,
    joined_at: '2026-01-05T10:00:00Z',
  }
}

const ada = member('m-ada', 'Ada Admin', ['administrator'], ME)
const mo = member('m-mo', 'Mo Manager', ['manager'])
const rae = member('m-rae', 'Rae Resident', ['resident'])

function invitation(id: string, email: string, status: Invitation['status']): Invitation {
  return {
    id,
    email,
    roles: ['resident'],
    status,
    invited_by_name: 'Ada Admin',
    created_at: '2026-11-01T10:00:00Z',
    expires_at: '2026-11-08T10:00:00Z',
  }
}

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }
const asResident: Membership = { ...harborAdmin, roles: ['resident'] }

const emptyInvitations = { body: [] }

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function callsTo(requests: { method: string; path: string }[], key: string) {
  return requests.filter((request) => `${request.method} ${request.path}` === key)
}

describe('who can see the people page', () => {
  it('shows administrators a link and the member list', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin], 'csrf-1') },
      [MEMBERS_URL]: { body: [ada, mo, rae] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
    })

    renderAt(`/organizations/${HARBOR.id}`)
    fireEvent.click(await screen.findByRole('link', { name: 'People' }))

    expect(await screen.findByRole('heading', { name: 'Members' })).toBeInTheDocument()
    expect(screen.getByText('Mo Manager')).toBeInTheDocument()
    expect(screen.getByText('mo@example.com')).toBeInTheDocument()
    expect(screen.getByText('Roles: Manager')).toBeInTheDocument()
    expect(screen.getByText('(you)')).toBeInTheDocument()
  })

  it('hides the link and the page from roles without people tools', async () => {
    const { requests } = mockApi({ 'GET /api/auth/me': { body: sessionFor([asResident]) } })

    renderAt(PEOPLE)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'People' })).not.toBeInTheDocument()
    expect(requests).toHaveLength(1)
  })

  it('gives managers the invitation tools only', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
    })

    renderAt(PEOPLE)

    expect(await screen.findByRole('heading', { name: 'Invitations' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Members' })).not.toBeInTheDocument()
    expect(callsTo(requests, MEMBERS_URL)).toHaveLength(0)

    const roleGroup = screen.getByRole('group', { name: 'Roles' })
    expect(within(roleGroup).getAllByRole('checkbox').map((box) => box.parentElement?.textContent)).toEqual([
      'Resident',
      'Contractor',
    ])
  })
})

describe('changing roles', () => {
  it('saves the new roles and reloads the list', async () => {
    let members = [ada, mo, rae]
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin], 'csrf-1') },
      [MEMBERS_URL]: () => ({ body: members }),
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
      [`PUT /api/organizations/${HARBOR.id}/members/m-rae/roles`]: () => {
        members = [ada, mo, { ...rae, roles: ['manager', 'resident'] }]
        return { body: members[2] }
      },
    })
    renderAt(PEOPLE)

    fireEvent.click(await screen.findByRole('button', { name: 'Edit roles for Rae Resident' }))
    const group = screen.getByRole('group', { name: 'Roles for Rae Resident' })
    fireEvent.click(within(group).getByRole('checkbox', { name: 'Manager' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save roles' }))

    expect(await screen.findByText('Roles: Manager, Resident')).toBeInTheDocument()
    const save = requests.find((request) => request.method === 'PUT')
    expect(save?.body).toEqual({ roles: ['resident', 'manager'] })
    expect(save?.headers['X-CSRF-Token']).toBe('csrf-1')
    expect(callsTo(requests, MEMBERS_URL)).toHaveLength(2)
  })

  it('does not allow saving without any role', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [MEMBERS_URL]: { body: [ada, rae] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
    })
    renderAt(PEOPLE)

    fireEvent.click(await screen.findByRole('button', { name: 'Edit roles for Rae Resident' }))
    const group = screen.getByRole('group', { name: 'Roles for Rae Resident' })
    fireEvent.click(within(group).getByRole('checkbox', { name: 'Resident' }))

    expect(screen.getByRole('button', { name: 'Save roles' })).toBeDisabled()
  })

  it('shows why the last administrator cannot step down and keeps the editor open', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [MEMBERS_URL]: { body: [ada, rae] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
      [`PUT /api/organizations/${HARBOR.id}/members/m-ada/roles`]: {
        status: 409,
        body: { detail: 'An organization needs at least one administrator' },
      },
    })
    renderAt(PEOPLE)

    fireEvent.click(await screen.findByRole('button', { name: 'Edit roles for Ada Admin' }))
    const group = screen.getByRole('group', { name: 'Roles for Ada Admin' })
    fireEvent.click(within(group).getByRole('checkbox', { name: 'Manager' }))
    fireEvent.click(within(group).getByRole('checkbox', { name: 'Administrator' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save roles' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('at least one administrator')
    expect(screen.getByRole('group', { name: 'Roles for Ada Admin' })).toBeInTheDocument()
  })

  it('refreshes the session when someone changes their own roles', async () => {
    let signedInAs: Membership = harborAdmin
    const { requests } = mockApi({
      'GET /api/auth/me': () => ({ body: sessionFor([signedInAs]) }),
      [MEMBERS_URL]: { body: [ada, { ...mo, roles: ['administrator'] }] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
      [`PUT /api/organizations/${HARBOR.id}/members/m-ada/roles`]: () => {
        signedInAs = asManager
        return { body: { ...ada, roles: ['manager'] } }
      },
    })
    renderAt(PEOPLE)

    fireEvent.click(await screen.findByRole('button', { name: 'Edit roles for Ada Admin' }))
    const group = screen.getByRole('group', { name: 'Roles for Ada Admin' })
    fireEvent.click(within(group).getByRole('checkbox', { name: 'Manager' }))
    fireEvent.click(within(group).getByRole('checkbox', { name: 'Administrator' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save roles' }))

    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Members' })).not.toBeInTheDocument())
    expect(callsTo(requests, 'GET /api/auth/me')).toHaveLength(2)
    expect(screen.getByRole('heading', { name: 'Invitations' })).toBeInTheDocument()
  })
})

describe('removing members', () => {
  it('asks first, and does nothing if cancelled', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [MEMBERS_URL]: { body: [ada, rae] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
    })
    renderAt(PEOPLE)

    fireEvent.click(await screen.findByRole('button', { name: 'Remove Rae Resident' }))
    expect(screen.getByText(/Remove Rae Resident from Harbor Property Group\?/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.getByRole('button', { name: 'Remove Rae Resident' })).toBeInTheDocument()
    expect(requests.some((request) => request.method === 'DELETE')).toBe(false)
  })

  it('removes the member after confirmation and reloads the list', async () => {
    let members = [ada, rae]
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin], 'csrf-9') },
      [MEMBERS_URL]: () => ({ body: members }),
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
      [`DELETE /api/organizations/${HARBOR.id}/members/m-rae`]: () => {
        members = [ada]
        return { status: 204 }
      },
    })
    renderAt(PEOPLE)

    fireEvent.click(await screen.findByRole('button', { name: 'Remove Rae Resident' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }))

    await waitFor(() => expect(screen.queryByText('Rae Resident')).not.toBeInTheDocument())
    expect(requests.find((request) => request.method === 'DELETE')?.headers['X-CSRF-Token']).toBe(
      'csrf-9',
    )
  })

  it('explains when the last administrator cannot be removed', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [MEMBERS_URL]: { body: [ada] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
      [`DELETE /api/organizations/${HARBOR.id}/members/m-ada`]: {
        status: 409,
        body: { detail: 'An organization needs at least one administrator' },
      },
    })
    renderAt(PEOPLE)

    fireEvent.click(await screen.findByRole('button', { name: 'Remove Ada Admin' }))
    expect(screen.getByText(/Remove yourself from/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('at least one administrator')
  })

  it('shows not found once someone has removed themselves', async () => {
    let signedInAs: Membership[] = [harborAdmin]
    mockApi({
      'GET /api/auth/me': () => ({ body: sessionFor(signedInAs) }),
      [MEMBERS_URL]: { body: [ada, mo] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
      [`DELETE /api/organizations/${HARBOR.id}/members/m-ada`]: () => {
        signedInAs = []
        return { status: 204 }
      },
    })
    renderAt(PEOPLE)

    fireEvent.click(await screen.findByRole('button', { name: 'Remove Ada Admin' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }))

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})

describe('invitations', () => {
  it('sends an invitation and shows it in the list', async () => {
    let invitations: Invitation[] = []
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin], 'csrf-3') },
      [MEMBERS_URL]: { body: [ada] },
      [`GET ${INVITATIONS_URL}`]: () => ({ body: invitations }),
      [`POST ${INVITATIONS_URL}`]: () => {
        invitations = [invitation('i-1', 'new@example.com', 'pending')]
        return { status: 201, body: invitations[0] }
      },
    })
    renderAt(PEOPLE)
    expect(await screen.findByText('No invitations yet.')).toBeInTheDocument()

    const form = screen.getByRole('form', { name: 'Invite someone' })
    fireEvent.change(within(form).getByLabelText('Email address'), {
      target: { value: ' new@example.com ' },
    })
    fireEvent.click(within(form).getByRole('checkbox', { name: 'Resident' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: 'Contractor' }))
    fireEvent.click(within(form).getByRole('button', { name: 'Send invitation' }))

    expect(await screen.findByText('Invitation sent to new@example.com.')).toBeInTheDocument()
    expect(await screen.findByText('Pending')).toBeInTheDocument()
    const sent = requests.find((request) => request.method === 'POST')
    expect(sent?.body).toEqual({ email: 'new@example.com', roles: ['resident', 'contractor'] })
    expect(sent?.headers['X-CSRF-Token']).toBe('csrf-3')
    expect(within(form).getByLabelText('Email address')).toHaveValue('')
  })

  it('asks for a role before sending', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [MEMBERS_URL]: { body: [ada] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
    })
    renderAt(PEOPLE)
    const form = await screen.findByRole('form', { name: 'Invite someone' })

    fireEvent.change(within(form).getByLabelText('Email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Send invitation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose at least one role.')
    expect(requests.some((request) => request.method === 'POST')).toBe(false)
  })

  it('shows the server message when the person is already a member', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [MEMBERS_URL]: { body: [ada] },
      [`GET ${INVITATIONS_URL}`]: emptyInvitations,
      [`POST ${INVITATIONS_URL}`]: {
        status: 409,
        body: { detail: 'This person is already a member of the organization' },
      },
    })
    renderAt(PEOPLE)
    const form = await screen.findByRole('form', { name: 'Invite someone' })

    fireEvent.change(within(form).getByLabelText('Email address'), {
      target: { value: 'rae@example.com' },
    })
    fireEvent.click(within(form).getByRole('checkbox', { name: 'Resident' }))
    fireEvent.click(within(form).getByRole('button', { name: 'Send invitation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already a member')
  })

  it('revokes pending invitations only', async () => {
    let invitations = [
      invitation('i-1', 'waiting@example.com', 'pending'),
      invitation('i-2', 'joined@example.com', 'accepted'),
      invitation('i-3', 'late@example.com', 'expired'),
    ]
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin], 'csrf-4') },
      [MEMBERS_URL]: { body: [ada] },
      [`GET ${INVITATIONS_URL}`]: () => ({ body: invitations }),
      [`DELETE ${INVITATIONS_URL}/i-1`]: () => {
        invitations = [{ ...invitations[0], status: 'revoked' }, ...invitations.slice(1)]
        return { status: 204 }
      },
    })
    renderAt(PEOPLE)

    expect(await screen.findByText('waiting@example.com')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Revoke invitation/ })).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Revoke invitation for waiting@example.com' }))

    expect(await screen.findByText('Revoked')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Revoke invitation/ })).not.toBeInTheDocument()
    expect(requests.find((request) => request.method === 'DELETE')?.headers['X-CSRF-Token']).toBe(
      'csrf-4',
    )
  })
})
