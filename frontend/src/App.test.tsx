import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import {
  ELM,
  elmManager,
  HARBOR,
  harborAdmin,
  mockApi,
  notSignedIn,
  sessionFor,
} from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

function fillAndSubmitSignIn(email = 'ada@example.com', password = 'a long password') {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('signing in', () => {
  it('sends a signed-out visitor to the sign-in form', async () => {
    mockApi({ 'GET /api/auth/me': notSignedIn })

    renderAt('/organizations/anything')

    expect(await screen.findByRole('heading', { name: 'Sign in to WorkLedger' })).toBeInTheDocument()
  })

  it('signs in and opens the first organization', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/auth/sign-in': { body: sessionFor([harborAdmin, elmManager]) },
    })
    renderAt('/')
    await screen.findByLabelText('Email')

    fillAndSubmitSignIn(' ada@example.com ')

    expect(await screen.findByRole('heading', { name: HARBOR.name })).toBeInTheDocument()
    expect(screen.getByText('Your roles: Administrator')).toBeInTheDocument()
    expect(screen.getByText('Ada Admin')).toBeInTheDocument()
    expect(requests.find((r) => r.path === '/api/auth/sign-in')?.body).toEqual({
      email: 'ada@example.com',
      password: 'a long password',
    })
  })

  it('shows the server message for a wrong password and stays on the form', async () => {
    mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/auth/sign-in': { status: 401, body: { detail: 'Invalid email or password' } },
    })
    renderAt('/')
    await screen.findByLabelText('Email')

    fillAndSubmitSignIn()

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
    expect(screen.getByLabelText('Email')).toHaveValue('ada@example.com')
  })

  it('returns to the page the person originally asked for', async () => {
    mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/auth/sign-in': { body: sessionFor([harborAdmin, elmManager]) },
    })
    renderAt(`/organizations/${ELM.id}`)
    await screen.findByLabelText('Email')

    fillAndSubmitSignIn()

    expect(await screen.findByRole('heading', { name: ELM.name })).toBeInTheDocument()
  })
})

describe('an existing session', () => {
  it('is restored on load without asking for a password', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([harborAdmin]) } })

    renderAt('/')

    expect(await screen.findByRole('heading', { name: HARBOR.name })).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })

  it('returns to the sign-in form when the server ends it', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin, elmManager]) },
      'POST /api/auth/sign-out': notSignedIn,
    })
    renderAt('/')
    await screen.findByRole('heading', { name: HARBOR.name })

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    expect(requests).toHaveLength(2)
  })
})

describe('signing out', () => {
  it('ends the session with the CSRF token and shows the sign-in form', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin], 'csrf-xyz') },
      'POST /api/auth/sign-out': { status: 204 },
    })
    renderAt('/')
    await screen.findByRole('heading', { name: HARBOR.name })

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    const signOut = requests.find((r) => r.path === '/api/auth/sign-out')
    expect(signOut?.headers['X-CSRF-Token']).toBe('csrf-xyz')
  })

  it('tells the person when signing out fails', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      'POST /api/auth/sign-out': { status: 500 },
    })
    renderAt('/')
    await screen.findByRole('heading', { name: HARBOR.name })

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not sign out')
    expect(screen.getByRole('heading', { name: HARBOR.name })).toBeInTheDocument()
  })
})

describe('organizations', () => {
  it('lets someone with several organizations switch between them', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([harborAdmin, elmManager]) } })
    renderAt('/')
    await screen.findByRole('heading', { name: HARBOR.name })

    const switcher = screen.getByRole('combobox', { name: 'Organization' })
    expect(switcher).toHaveValue(HARBOR.id)
    fireEvent.change(switcher, { target: { value: ELM.id } })

    expect(await screen.findByRole('heading', { name: ELM.name })).toBeInTheDocument()
    expect(screen.getByText('Your roles: Manager, Resident')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Organization' })).toHaveValue(ELM.id)
  })

  it('opens the organization used last time', async () => {
    localStorage.setItem('workledger.lastOrganizationId', ELM.id)
    mockApi({ 'GET /api/auth/me': { body: sessionFor([harborAdmin, elmManager]) } })

    renderAt('/')

    expect(await screen.findByRole('heading', { name: ELM.name })).toBeInTheDocument()
  })

  it('ignores a remembered organization the person no longer belongs to', async () => {
    localStorage.setItem('workledger.lastOrganizationId', ELM.id)
    mockApi({ 'GET /api/auth/me': { body: sessionFor([harborAdmin]) } })

    renderAt('/')

    expect(await screen.findByRole('heading', { name: HARBOR.name })).toBeInTheDocument()
  })

  it('shows just the name when there is only one organization', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([harborAdmin]) } })
    renderAt('/')
    await screen.findByRole('heading', { name: HARBOR.name })

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('explains what to do when the account belongs to no organization', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([]) } })

    renderAt('/')

    expect(await screen.findByRole('heading', { name: 'No organization yet' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('treats an organization the person does not belong to like one that does not exist', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([harborAdmin]) } })

    renderAt(`/organizations/${ELM.id}`)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(ELM.name)).not.toBeInTheDocument())
  })

  it('shows a not-found page for unknown addresses', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([harborAdmin]) } })

    renderAt('/nowhere/at/all')

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
