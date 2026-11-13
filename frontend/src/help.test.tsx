import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type { Membership, Report } from './api/types.ts'
import { REPEAT_ISSUES_SHOWN } from './reports/reports.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const ORG_PATH = `/organizations/${HARBOR.id}`

const as = (...roles: Membership['roles']): Membership => ({ ...harborAdmin, roles })

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the help page', () => {
  it('shows a resident only the resident guidance', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([as('resident')]) } })

    renderAt(`${ORG_PATH}/help`)

    expect(await screen.findByRole('heading', { name: 'For residents' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Report a problem' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'For everyone' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'For managers' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'For contractors' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Approvals' })).not.toBeInTheDocument()
  })

  it('shows each role the guidance for the roles they hold', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([as('manager', 'property_owner')]) } })

    renderAt(`${ORG_PATH}/help`)

    expect(await screen.findByRole('heading', { name: 'For managers' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'For property owners' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Inviting people' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'For residents' })).not.toBeInTheDocument()
  })

  it('explains the sign-in lock to everyone', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([as('contractor')]) } })

    renderAt(`${ORG_PATH}/help`)

    expect(await screen.findByRole('heading', { name: 'For contractors' })).toBeInTheDocument()
    expect(screen.getByText(/locked for 15 minutes/)).toBeInTheDocument()
  })

  it('is linked from the navigation', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([as('resident')]) } })

    renderAt(`${ORG_PATH}/my-requests`)

    const link = await screen.findByRole('link', { name: 'Help' })
    expect(link).toHaveAttribute('href', `${ORG_PATH}/help`)
  })
})

describe('the application shell', () => {
  it('offers a skip link that targets the main landmark', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([as('resident')]) } })

    renderAt(`${ORG_PATH}/help`)

    const skip = await screen.findByRole('link', { name: 'Skip to main content' })
    expect(skip).toHaveAttribute('href', '#main-content')
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content')
  })
})

describe('the repeat issues note', () => {
  const issue = (index: number) => ({
    property_id: 'p-1',
    property_name: 'Maple Court',
    unit_label: `Unit ${index}`,
    category: 'plumbing',
    count: 2,
    references: [`WO-${index}`],
  })

  const emptyReport = (repeats: number): Report =>
    ({
      period_start: '2026-08-16',
      period_end: '2026-11-13',
      requests: { open: 0, waiting_for_triage: 0, submitted_in_period: 0, by_status: {} },
      work_orders: {
        by_status: {},
        open: 0,
        overdue: 0,
        blocked: 0,
        created_in_period: 0,
        created_by_category: {},
        created_by_property: [],
      },
      resolution: { completed: 0, average_hours: null, slowest_hours: null, by_priority: [] },
      contractors: [],
      repeat_issues: Array.from({ length: repeats }, (_, index) => issue(index)),
      spend: { work_orders: 0, total: [], by_property: [], by_category: [] },
      approvals: {
        estimates_recorded: 0,
        needed_approval: 0,
        pending: 0,
        approved: 0,
        rejected: 0,
        replaced: 0,
        pending_amounts: [],
        approved_amounts: [],
        rejected_amounts: [],
        average_decision_hours: null,
        by_property: [],
      },
    }) as Report

  it('says when the list was cut short', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([as('manager')]) },
      [`GET ${ORG}/properties`]: { body: [] },
      [`GET ${ORG}/reports`]: { body: emptyReport(REPEAT_ISSUES_SHOWN) },
    })

    renderAt(`${ORG_PATH}/reports`)

    expect(
      await screen.findByText(`Showing the ${REPEAT_ISSUES_SHOWN} most repeated problems.`),
    ).toBeInTheDocument()
  })

  it('stays quiet when nothing was cut', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([as('manager')]) },
      [`GET ${ORG}/properties`]: { body: [] },
      [`GET ${ORG}/reports`]: { body: emptyReport(3) },
    })

    renderAt(`${ORG_PATH}/reports`)

    expect(await screen.findByRole('heading', { name: 'Repeat issues' })).toBeInTheDocument()
    expect(screen.queryByText(/most repeated problems/)).not.toBeInTheDocument()
  })
})
