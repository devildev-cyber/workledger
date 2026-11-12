import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type { InvitationPreview } from './api/types.ts'
import {
  ELM,
  elmManager,
  harborAdmin,
  mockApi,
  notSignedIn,
  sessionFor,
} from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const LINK = '/invitations/accept#token=secret-token'
const PASSWORD = 'a long enough password'

const newPersonInvitation: InvitationPreview = {
  organization_id: ELM.id,
  organization_name: ELM.name,
  email: 'newcomer@example.com',
  roles: ['manager', 'resident'],
  has_account: false,
}

const existingAccountInvitation: InvitationPreview = {
  ...newPersonInvitation,
  email: 'ada@example.com',
  has_account: true,
}

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function fillCreateAccountForm(name = ' Nia Newcomer ', password = PASSWORD, confirmation = PASSWORD) {
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: name } })
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: password } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: confirmation } })
  fireEvent.click(screen.getByRole('button', { name: 'Create account and join' }))
}

describe('accepting an invitation as a new person', () => {
  it('describes the invitation, creates the account, and opens the organization', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/invitations/preview': { body: newPersonInvitation },
      'POST /api/invitations/accept': { body: sessionFor([elmManager]) },
    })

    renderAt(LINK)

    expect(await screen.findByRole('heading', { name: 'Create your account' })).toBeInTheDocument()
    expect(screen.getByText(ELM.name)).toBeInTheDocument()
    expect(screen.getByText(/as Manager, Resident/)).toBeInTheDocument()
    expect(screen.getByText(/newcomer@example.com/)).toBeInTheDocument()
    expect(requests.find((r) => r.path === '/api/invitations/preview')?.body).toEqual({
      token: 'secret-token',
    })

    fillCreateAccountForm()

    expect(await screen.findByRole('heading', { name: ELM.name })).toBeInTheDocument()
    expect(screen.getByText('Ada Admin')).toBeInTheDocument()
    expect(requests.find((r) => r.path === '/api/invitations/accept')?.body).toEqual({
      token: 'secret-token',
      full_name: 'Nia Newcomer',
      password: PASSWORD,
    })
  })

  it('does not send anything when the two passwords differ', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/invitations/preview': { body: newPersonInvitation },
    })
    renderAt(LINK)
    await screen.findByLabelText('Full name')

    fillCreateAccountForm('Nia', PASSWORD, 'something else entirely')

    expect(await screen.findByRole('alert')).toHaveTextContent('do not match')
    expect(requests.some((r) => r.path === '/api/invitations/accept')).toBe(false)
  })

  it('does not send anything when the password is too short', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/invitations/preview': { body: newPersonInvitation },
    })
    renderAt(LINK)
    await screen.findByLabelText('Full name')

    fillCreateAccountForm('Nia', 'short', 'short')

    expect(await screen.findByRole('alert')).toHaveTextContent('12 to 128 characters')
    expect(requests.some((r) => r.path === '/api/invitations/accept')).toBe(false)
  })

  it('shows the server message when accepting fails', async () => {
    mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/invitations/preview': { body: newPersonInvitation },
      'POST /api/invitations/accept': { status: 404, body: { detail: 'This invitation is not valid.' } },
    })
    renderAt(LINK)
    await screen.findByLabelText('Full name')

    fillCreateAccountForm()

    expect(await screen.findByRole('alert')).toHaveTextContent('This invitation is not valid.')
    expect(screen.getByRole('button', { name: 'Create account and join' })).toBeEnabled()
  })
})

describe('invitation links that do not work', () => {
  it('explains an invitation the server rejects', async () => {
    mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/invitations/preview': {
        status: 404,
        body: { detail: 'This invitation is not valid. It may have expired or already been used.' },
      },
    })

    renderAt(LINK)

    expect(await screen.findByRole('heading', { name: 'Invitation not valid' })).toBeInTheDocument()
    expect(screen.getByText(/may have expired or already been used/)).toBeInTheDocument()
  })

  it('explains a link that has no token', async () => {
    const { requests } = mockApi({ 'GET /api/auth/me': notSignedIn })

    renderAt('/invitations/accept')

    expect(await screen.findByText(/link is incomplete/)).toBeInTheDocument()
    expect(requests.some((r) => r.path === '/api/invitations/preview')).toBe(false)
  })
})

describe('accepting an invitation with an existing account', () => {
  it('asks the person to sign in first, then brings them back to accept', async () => {
    mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/invitations/preview': { body: existingAccountInvitation },
      'POST /api/auth/sign-in': { body: sessionFor([harborAdmin]) },
    })
    renderAt(LINK)

    fireEvent.click(await screen.findByRole('link', { name: 'Sign in' }))
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'ada@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: PASSWORD } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('button', { name: 'Accept invitation' })).toBeInTheDocument()
  })

  it('joins with one click and opens the new organization', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin], 'csrf-777') },
      'POST /api/invitations/preview': { body: existingAccountInvitation },
      'POST /api/invitations/accept': { body: sessionFor([harborAdmin, elmManager], 'csrf-777') },
    })
    renderAt(LINK)

    fireEvent.click(await screen.findByRole('button', { name: 'Accept invitation' }))

    expect(await screen.findByRole('heading', { name: ELM.name })).toBeInTheDocument()
    const accept = requests.find((r) => r.path === '/api/invitations/accept')
    expect(accept?.body).toEqual({ token: 'secret-token' })
    expect(accept?.headers['X-CSRF-Token']).toBe('csrf-777')
    expect(screen.getByRole('combobox', { name: 'Organization' })).toHaveValue(ELM.id)
  })

  it('asks to switch accounts when signed in as someone else', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      'POST /api/invitations/preview': {
        body: { ...existingAccountInvitation, email: 'someone.else@example.com' },
      },
      'POST /api/auth/sign-out': { status: 204 },
    })
    renderAt(LINK)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'signed in as ada@example.com. Sign out and sign in as someone.else@example.com',
    )
    expect(screen.queryByRole('button', { name: 'Accept invitation' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('link', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('compares email addresses ignoring capital letters', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      'POST /api/invitations/preview': {
        body: { ...existingAccountInvitation, email: 'ADA@Example.com' },
      },
    })

    renderAt(LINK)

    expect(await screen.findByRole('button', { name: 'Accept invitation' })).toBeInTheDocument()
  })
})
