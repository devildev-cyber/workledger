import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { mockApi } from '../test/fetch-mock.ts'
import { api, ApiError, setCsrfToken, setUnauthorizedHandler } from './client.ts'

beforeEach(() => {
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api', () => {
  it('sends JSON to the /api prefix and returns the JSON reply', async () => {
    const { requests } = mockApi({ 'POST /api/things': { body: { id: 7 } } })

    const result = await api<{ id: number }>('/things', { method: 'POST', body: { name: 'x' } })

    expect(result).toEqual({ id: 7 })
    expect(requests[0].body).toEqual({ name: 'x' })
    expect(requests[0].headers['Content-Type']).toBe('application/json')
  })

  it('adds the CSRF token to changes but not to reads', async () => {
    const { requests } = mockApi({
      'GET /api/things': {},
      'DELETE /api/things/1': { status: 204 },
    })
    setCsrfToken('token-abc')

    await api('/things')
    await api('/things/1', { method: 'DELETE' })

    expect(requests[0].headers['X-CSRF-Token']).toBeUndefined()
    expect(requests[1].headers['X-CSRF-Token']).toBe('token-abc')
  })

  it('returns nothing for an empty 204 reply', async () => {
    mockApi({ 'DELETE /api/things/1': { status: 204 } })

    await expect(api('/things/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('uses the server message from a plain error', async () => {
    mockApi({ 'GET /api/things': { status: 409, body: { detail: 'Already exists' } } })

    await expect(api('/things')).rejects.toMatchObject({ status: 409, message: 'Already exists' })
  })

  it('joins the messages of a validation error', async () => {
    mockApi({
      'POST /api/things': {
        status: 422,
        body: { detail: [{ loc: ['body', 'a'], msg: 'Too short' }, { loc: ['body', 'b'], msg: 'Required' }] },
      },
    })

    await expect(api('/things', { method: 'POST', body: {} })).rejects.toThrow('Too short Required')
  })

  it('falls back to a generic message when the reply has no detail', async () => {
    mockApi({ 'GET /api/things': { status: 500, body: {} } })

    await expect(api('/things')).rejects.toThrow('Something went wrong. Please try again.')
  })

  it('explains a connection failure', async () => {
    mockApi({ 'GET /api/things': new TypeError('Failed to fetch') })

    const failure = await api('/things').catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).toMatchObject({ status: 0 })
    expect((failure as ApiError).message).toMatch(/could not reach the server/i)
  })

  it('reports an ended session only when the person was signed in', async () => {
    mockApi({ 'GET /api/things': { status: 401, body: { detail: 'Not authenticated' } } })
    const handler = vi.fn()
    setUnauthorizedHandler(handler)

    await api('/things').catch(() => undefined)
    expect(handler).not.toHaveBeenCalled()

    setCsrfToken('token-abc')
    await api('/things').catch(() => undefined)
    expect(handler).toHaveBeenCalledOnce()
  })
})
