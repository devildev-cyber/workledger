import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import { harborAdmin, mockApi, notSignedIn, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const PASSWORD = 'a brand new passphrase'
const SENT = 'If an account exists for that email address, a reset link has been sent.'

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function chooseNewPassword(password = PASSWORD, confirmation = PASSWORD) {
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: password } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: confirmation } })
  fireEvent.click(screen.getByRole('button', { name: 'Change password' }))
}

describe('asking for a reset link', () => {
  it('is reachable from the sign-in form', async () => {
    mockApi({ 'GET /api/auth/me': notSignedIn })
    renderAt('/sign-in')

    fireEvent.click(await screen.findByRole('link', { name: 'Forgot your password?' }))

    expect(await screen.findByRole('heading', { name: 'Reset your password' })).toBeInTheDocument()
  })

  it('shows the same message the server gives, whoever asks', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/auth/password-reset/request': { status: 202, body: { detail: SENT } },
    })
    renderAt('/forgot-password')

    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: ' ada@example.com ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByRole('status')).toHaveTextContent(SENT)
    expect(requests.find((r) => r.path.endsWith('/request'))?.body).toEqual({
      email: 'ada@example.com',
    })
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
  })

  it('shows an error when the server cannot be reached', async () => {
    mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/auth/password-reset/request': new TypeError('Failed to fetch'),
    })
    renderAt('/forgot-password')

    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'ada@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the server/i)
    expect(screen.getByRole('button', { name: 'Send reset link' })).toBeEnabled()
  })
})

describe('choosing a new password', () => {
  it('sends the token from the link and the new password', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/auth/password-reset/confirm': { status: 204 },
    })
    renderAt('/password-reset#token=reset-secret')

    chooseNewPassword()

    expect(await screen.findByRole('heading', { name: 'Password changed' })).toBeInTheDocument()
    expect(requests.find((r) => r.path.endsWith('/confirm'))?.body).toEqual({
      token: 'reset-secret',
      password: PASSWORD,
    })
    expect(screen.getByRole('link', { name: 'Go to sign in' })).toHaveAttribute('href', '/sign-in')
  })

  it('does not send anything when the passwords differ or are too short', async () => {
    const { requests } = mockApi({ 'GET /api/auth/me': notSignedIn })
    renderAt('/password-reset#token=reset-secret')
    await screen.findByLabelText('New password')

    chooseNewPassword(PASSWORD, 'different')
    expect(await screen.findByRole('alert')).toHaveTextContent('do not match')

    chooseNewPassword('short', 'short')
    expect(await screen.findByRole('alert')).toHaveTextContent('12 to 128 characters')

    expect(requests.some((r) => r.path.endsWith('/confirm'))).toBe(false)
  })

  it('offers a new link when the old one is rejected', async () => {
    mockApi({
      'GET /api/auth/me': notSignedIn,
      'POST /api/auth/password-reset/confirm': {
        status: 404,
        body: { detail: 'This reset link is not valid. It may have expired or already been used.' },
      },
    })
    renderAt('/password-reset#token=old')

    chooseNewPassword()

    expect(await screen.findByRole('alert')).toHaveTextContent('not valid')
    expect(screen.getByRole('link', { name: 'Send a new reset link' })).toHaveAttribute(
      'href',
      '/forgot-password',
    )
  })

  it('explains a link that has no token', async () => {
    const { requests } = mockApi({ 'GET /api/auth/me': notSignedIn })

    renderAt('/password-reset')

    expect(await screen.findByRole('heading', { name: 'Reset link not valid' })).toBeInTheDocument()
    expect(requests.some((r) => r.path.endsWith('/confirm'))).toBe(false)
  })

  it('forgets a session in this browser, since the server ended it', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      'POST /api/auth/password-reset/confirm': { status: 204 },
    })
    renderAt('/password-reset#token=reset-secret')
    // A person takes a moment to type, by which time the saved session has been recognized.
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)))

    chooseNewPassword()
    fireEvent.click(await screen.findByRole('link', { name: 'Go to sign in' }))

    expect(await screen.findByRole('heading', { name: 'Sign in to WorkLedger' })).toBeInTheDocument()
  })
})
