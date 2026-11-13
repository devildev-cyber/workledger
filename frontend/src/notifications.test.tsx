import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type {
  AppNotification,
  Membership,
  NotificationList,
  WorkOrderSummary,
} from './api/types.ts'
import { authorLabel } from './organizations/organizations.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const ORG_PATH = `/organizations/${HARBOR.id}`

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }
const asContractor: Membership = { ...harborAdmin, roles: ['contractor'] }

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 'n-1',
    kind: 'work_order_assigned',
    title: 'WO-0001 was assigned to you: Replace kitchen tap',
    path: `${ORG_PATH}/nowhere`,
    read: false,
    created_at: '2026-11-10T10:00:00Z',
    ...overrides,
  }
}

function list(items: AppNotification[]): NotificationList {
  return { items, unread_count: items.filter((item) => !item.read).length }
}

const UNREAD = `GET ${ORG}/notifications?unread_only=true`
const ALL = `GET ${ORG}/notifications`
const PREFERENCES = `GET ${ORG}/notifications/preferences`

describe('the notifications link', () => {
  it('shows how many notifications are unread', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [UNREAD]: { body: list([notification(), notification({ id: 'n-2' })]) },
      [`GET ${ORG}/my-jobs`]: { body: [] },
    })

    renderAt(`${ORG_PATH}/my-jobs`)

    const link = await screen.findByRole('link', { name: /Notifications/ })
    expect(await within(link).findByText('2')).toBeInTheDocument()
    expect(within(link).getByText('unread')).toHaveClass('sr-only')
    expect(link).toHaveAttribute('href', `${ORG_PATH}/notifications`)
  })

  it('shows no count when everything has been read', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs`]: { body: [] },
    })

    renderAt(`${ORG_PATH}/my-jobs`)

    const link = await screen.findByRole('link', { name: 'Notifications' })
    expect(link).toHaveTextContent(/^Notifications$/)
  })
})

describe('the notifications page', () => {
  it('lists notifications, newest first as sent, with the unread ones marked', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [ALL]: {
        body: list([
          notification(),
          notification({ id: 'n-2', title: 'WO-0002 is now cancelled', read: true }),
        ]),
      },
      [PREFERENCES]: { body: { email_enabled: true } },
    })

    renderAt(`${ORG_PATH}/notifications`)

    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Unread: WO-0001 was assigned to you')
    expect(items[1]).not.toHaveTextContent('Unread')
    expect(screen.getByRole('button', { name: 'Mark all as read' })).toBeInTheDocument()
  })

  it('says so when there is nothing yet', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [ALL]: { body: list([]) },
      [PREFERENCES]: { body: { email_enabled: true } },
    })

    renderAt(`${ORG_PATH}/notifications`)

    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark all as read' })).not.toBeInTheDocument()
  })

  it('marks a notification read and then opens what it is about', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [ALL]: { body: list([notification()]) },
      [PREFERENCES]: { body: { email_enabled: true } },
      [`POST ${ORG}/notifications/n-1/read`]: { body: list([notification({ read: true })]) },
    })

    renderAt(`${ORG_PATH}/notifications`)
    fireEvent.click(await screen.findByRole('link', { name: /WO-0001 was assigned/ }))

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(requests.some((request) => request.path === `${ORG}/notifications/n-1/read`)).toBe(true)
  })

  it('marks everything read in one step', async () => {
    let current = list([notification(), notification({ id: 'n-2' })])
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [ALL]: () => ({ body: current }),
      [PREFERENCES]: { body: { email_enabled: true } },
      [`POST ${ORG}/notifications/read`]: () => {
        current = list(current.items.map((item) => ({ ...item, read: true })))
        return { body: current }
      },
    })

    renderAt(`${ORG_PATH}/notifications`)
    fireEvent.click(await screen.findByRole('button', { name: 'Mark all as read' }))

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Mark all as read' })).not.toBeInTheDocument(),
    )
    expect(requests.some((request) => request.path === `${ORG}/notifications/read`)).toBe(true)
  })

  it('lets a person turn the email copies off', async () => {
    let enabled = true
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [ALL]: { body: list([]) },
      [PREFERENCES]: () => ({ body: { email_enabled: enabled } }),
      [`PUT ${ORG}/notifications/preferences`]: (request) => {
        enabled = (request.body as { email_enabled: boolean }).email_enabled
        return { body: { email_enabled: enabled } }
      },
    })

    renderAt(`${ORG_PATH}/notifications`)
    const checkbox = await screen.findByRole('checkbox', {
      name: 'Also email me these notifications',
    })
    expect(checkbox).toBeChecked()

    fireEvent.click(checkbox)

    await waitFor(() => expect(checkbox).not.toBeChecked())
    expect(requests.find((request) => request.method === 'PUT')?.body).toEqual({
      email_enabled: false,
    })
  })

  it('shows the server’s message when notifications cannot be loaded', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [ALL]: { status: 500, body: { detail: 'The notifications are unavailable' } },
      [PREFERENCES]: { body: { email_enabled: true } },
    })

    renderAt(`${ORG_PATH}/notifications`)

    expect(await screen.findByRole('alert')).toHaveTextContent('The notifications are unavailable')
  })

  it('keeps people out of other organizations’ notifications', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asContractor]) } })

    renderAt('/organizations/33333333-3333-4333-8333-333333333333/notifications')

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})

function summary(overrides: Partial<WorkOrderSummary> = {}): WorkOrderSummary {
  return {
    id: 'w-1',
    reference: 'WO-0001',
    title: 'Replace kitchen tap',
    status: 'on_hold',
    priority: 'soon',
    category: 'plumbing',
    property_id: 'p-1',
    property_name: 'Maple Court',
    unit_label: '1A',
    building_name: null,
    due_date: null,
    overdue: false,
    blocked: true,
    blocked_reason: 'On hold',
    request_count: 1,
    assignee_id: null,
    assignee_name: null,
    assignment_response: null,
    final_cost_cents: null,
    currency: null,
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:00Z',
    ...overrides,
  }
}

describe('work that needs attention', () => {
  it('summarises overdue and blocked work on the organization home page', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders?attention=overdue`]: {
        body: [
          summary({
            id: 'w-9',
            reference: 'WO-0009',
            title: 'Fix gutter',
            blocked: false,
            blocked_reason: null,
            overdue: true,
          }),
        ],
      },
      [`GET ${ORG}/work-orders?attention=blocked`]: {
        body: [
          summary(),
          summary({
            id: 'w-2',
            reference: 'WO-0002',
            title: 'Heater',
            status: 'awaiting_approval',
            blocked_reason: 'Waiting for the owner’s approval',
          }),
        ],
      },
    })

    renderAt(ORG_PATH)

    const overdue = await screen.findByRole('link', { name: 'Overdue (1)' })
    expect(overdue).toHaveAttribute('href', `${ORG_PATH}/work-orders?show=overdue`)
    expect(screen.getByRole('link', { name: 'Blocked (2)' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/work-orders?show=blocked`,
    )
    expect(screen.getByRole('link', { name: 'WO-0009' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/work-orders/w-9`,
    )
    expect(screen.getByText('Waiting for the owner’s approval')).toBeInTheDocument()
  })

  it('shows nothing when no work needs attention', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asManager]) } })

    renderAt(ORG_PATH)

    await screen.findByRole('heading', { name: HARBOR.name })
    expect(screen.queryByRole('heading', { name: 'Needs attention' })).not.toBeInTheDocument()
  })

  it('opens the work order list already narrowed to blocked work', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: [] },
      [`GET ${ORG}/contractors`]: { body: [] },
      [`GET ${ORG}/work-orders?attention=blocked`]: { body: [summary()] },
    })

    renderAt(`${ORG_PATH}/work-orders?show=blocked`)

    expect(await screen.findByRole('link', { name: 'Replace kitchen tap' })).toBeInTheDocument()
    expect(screen.getByLabelText('Show')).toHaveValue('blocked')
    expect(screen.getAllByText('On hold', { selector: 'span' })).toHaveLength(2)
    expect(requests.some((request) => request.path.includes('attention=blocked'))).toBe(true)
  })
})

describe('who did something', () => {
  it('names the role beside the person', () => {
    expect(authorLabel('Mo Manager', 'manager')).toBe('Mo Manager (Manager)')
    expect(authorLabel('Rae Resident', 'resident')).toBe('Rae Resident (Resident)')
  })

  it('does not invent a role', () => {
    expect(authorLabel('Mo Manager', null)).toBe('Mo Manager')
    expect(authorLabel(null, null)).toBe('System')
  })
})
