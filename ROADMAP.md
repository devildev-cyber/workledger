# WorkLedger Roadmap

This roadmap sequences the work described in [README.md](README.md) and [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md). It defines **what** gets built, **in what order**, and **how we know a phase is done**. It deliberately avoids solution design: each phase is planned in detail only when it starts, and decisions are recorded as they are made.

**Status legend:** ⬜ Not started · 🟨 In progress · ✅ Done · ⏸ Deferred

---

## Starting point

- The repository currently contains only the two product documents. There is no code, no `docs/` folder, no `.env.example`, and no git history yet.
- The product scope is maintenance coordination for firms managing roughly 20–300 units. Accounting, rent collection, lease management, and full property-management features are **out of scope**.
- The stack is already chosen: React + TypeScript + Vite + Tailwind on the frontend; FastAPI + Pydantic + SQLAlchemy 2 + Alembic on the backend; SQLite locally, PostgreSQL in production.

## Sequencing principles

1. **Boundaries before features.** Organization isolation, roles, and audit history underpin every later feature, so they come first.
2. **Core loop before breadth.** The basic repair loop (report → triage → dispatch → execute → close) works end to end before estimates, notifications, and reporting are layered on.
3. **The server owns the rules.** Permissions, workflow transitions, and approval gates are enforced by the backend; the UI reflects them.
4. **Every phase ends in a working, tested state.** No phase is "done" with failing tests or known authorization gaps.
5. **Decide only what the next phase needs.** Open questions are listed per phase and resolved when that phase begins.

---

## Overview

| # | Phase | Outcome | Depends on | Status |
| --- | --- | --- | --- | --- |
| 0 | Groundwork | A runnable, tested, empty monorepo | — | ✅ |
| 1 | Identity, organizations, and access | Secure sign-in, roles, and enforced organization isolation | 0 | ✅ |
| 2 | Property and unit directory | Organizations can model their properties, units, and residents | 1 | ✅ |
| 3 | Resident request intake | Residents can report issues and follow their status | 2 | 🟨 |
| 4 | Triage and work orders | Managers turn requests into controlled work orders | 3 | ✅ |
| 5 | Dispatch and contractor workspace | Contractors receive and carry out assigned work | 4 | 🟨 |
| 6 | Verification and closure | Work is verified, costed, and closed with a lasting history | 5 | ⬜ |
| ★ | **Milestone A: core repair loop** | One repair flows from report to closure | 0–6 | ⬜ |
| 7 | Estimates and owner approvals | Spending above a threshold requires a recorded decision | 6 | ⬜ |
| 8 | Notifications and activity | Participants learn about actionable events without asking | 6 | ⬜ |
| 9 | Reporting and export | Managers understand workload, patterns, and spend | 6, 7 | ⬜ |
| ★ | **Milestone B: feature-complete MVP** | All capabilities in the product documents exist | 0–9 | ⬜ |
| 10 | Production readiness | The product can be deployed and operated safely | B | ⬜ |
| ★ | **Milestone C: pilot** | A real (or realistic) firm uses WorkLedger day to day | 10 | ⬜ |

Phases 8 and 9 can run in parallel with Phase 7 once Milestone A is reached.

---

## Phase 0 — Groundwork

**Goal:** A contributor can clone the repository and run the backend, the frontend, and the tests with documented commands.

**Scope**
- Initialize the git repository and the monorepo layout described in the README.
- Backend and frontend applications that start and respond.
- Configuration via environment variables, a committed `.env.example`, and an initial database migration.
- Lint, test, and build commands for both sides, plus continuous integration running them.
- A `docs/` folder holding a glossary and a decision log.
- Development instructions for Linux/macOS as well as Windows (the README currently shows PowerShell only).

**Exit criteria**
- [x] A fresh clone runs both applications following only the README.
- [x] Backend and frontend lint, test, and build commands pass locally and in CI.
- [x] No secrets are committed; `.env.example` documents every required variable.
- [x] A glossary and a decision log exist and are linked from the README.

**Decisions made**
- The MVP is Milestone B, Phases 0–9 ([decision 0004](docs/decisions/0004-mvp-scope.md)).
- CI runs on GitHub Actions.
- "Firm principal" and "property owner" replace the ambiguous "owner" ([glossary](docs/glossary.md)).

---

## Phase 1 — Identity, organizations, and access

**Goal:** Users sign in securely, and every request to the API is limited to what the user's organization, role, and properties allow.

**Scope**
- User accounts, password hashing, and server-managed sessions (sign in and sign out).
- Organizations, memberships, and roles: administrator, manager, resident, contractor, property owner.
- A single, consistent permission-checking approach used by all endpoints, able to limit a role to certain properties. Assigning managers to properties happens in Phase 2, once properties exist.
- The activity-event foundation: actor, event type, timestamp, and before/after context.
- Safe error responses that do not reveal whether another organization's records exist.
- An email interface that records messages locally and in tests instead of sending them.
- Invitations, password reset, and a command-line tool to create the first organization and administrator.
- Basic membership administration: invite, change role, and remove members.

**Exit criteria**
- [x] Automated tests prove that users cannot read or change another organization's data, including by guessing IDs or URLs.
- [x] Each role is tested for both allowed and denied actions.
- [x] Membership and role changes produce activity events.
- [x] Session cookies are HTTP-only; passwords are never stored or logged in plain text.

**Decisions made**
- One account can hold memberships in several organizations ([decision 0005](docs/decisions/0005-accounts-and-memberships.md)).
- Accounts are created by invitation only ([decision 0006](docs/decisions/0006-invitation-only-accounts.md)).
- Email goes through a replaceable interface, and password reset is included now ([decision 0007](docs/decisions/0007-email-interface.md)).
- Managers act only on properties assigned to them ([decision 0008](docs/decisions/0008-property-scoped-managers.md)).
- Sessions use a cookie and a CSRF header ([decision 0009](docs/decisions/0009-session-authentication.md)); the organization is in the URL and roles are declared per endpoint ([decision 0010](docs/decisions/0010-organization-scoped-access.md)).
- Invitation, password reset, and membership rules are in decisions [0011](docs/decisions/0011-invitation-rules.md), [0012](docs/decisions/0012-password-reset.md), and [0013](docs/decisions/0013-membership-administration.md). The frontend follows [0014](docs/decisions/0014-frontend-api-access.md).

---

## Phase 2 — Property and unit directory

**Goal:** An administrator can represent their real portfolio, and residents are linked to the units they live in.

**Scope**
- Properties and units under an organization (and buildings, if confirmed as an entity).
- Residents associated with units, with contact details and access instructions.
- Assigning managers to the properties they act on.
- Property-level settings that later phases rely on, such as approval threshold and currency, defined but not yet enforced.
- Administration screens for properties, units, residents, and membership.
- Synthetic seed data representing a small, realistic firm.

**Exit criteria**
- [x] An administrator can set up properties, units, and residents through the UI.
- [x] Residents can see only the units they are associated with.
- [x] Private contact details are visible only to roles that need them.
- [x] The seed command produces a usable demo organization with no real personal data.

**Decisions made**
- Buildings are a real, optional record; properties, units, and manager assignment follow [decision 0015](docs/decisions/0015-property-directory.md).
- Residents and tenancies are separate records, a unit can have several residents and a resident several units, and a past resident loses the unit but keeps their own request history ([decision 0016](docs/decisions/0016-residents-and-tenancies.md)).

---

## Phase 3 — Resident request intake

**Goal:** A resident reports a problem and can follow its progress without contacting the manager.

**Scope**
- Request submission: unit, category, urgency, description, location, access notes, and attachments.
- A human-readable reference number and a confirmation.
- A resident request list and a status timeline.
- Separation between resident-visible updates and internal records, established here and kept in every later phase.
- Controlled attachment uploads (types, size limits, and who may view them).

**Exit criteria**
- [ ] A resident can submit, list, and track their own requests on desktop and mobile. (Done and tested; the layout is responsive but still needs a check on a real phone.)
- [x] API-level tests confirm that resident responses never include internal notes, private contacts, or restricted attachments.
- [x] Invalid or oversized uploads are rejected cleanly.

**Decisions made**
- Categories and urgencies are fixed for now, residents see six statuses, managers can enter a request for a resident, and resident-visible and internal records are separated in storage and in the response shapes ([decision 0017](docs/decisions/0017-maintenance-requests.md)).
- Attachments are limited to JPEG, PNG, WebP, and PDF, stored behind a replaceable interface, and served only through checked API routes ([decision 0018](docs/decisions/0018-attachments.md)).

---

## Phase 4 — Triage and work orders

**Goal:** Managers work from a clear queue and convert requests into work orders that follow an enforced lifecycle.

**Scope**
- A manager queue grouped by urgency, property, and age.
- Request review: accept, reject, mark as duplicate, or convert into a work order.
- Work orders with scope, priority, category, due date, and status.
- An enforced status lifecycle in which invalid transitions are rejected.
- A work-order page that is the single place to see scope, status, and history.
- Search and filtering by property, status, assignee, urgency, and age.

**Exit criteria**
- [x] Invalid status transitions are rejected and leave no partial changes in the work order or its history.
- [x] Every change records who made it and when.
- [x] A manager can triage the seeded queue without leaving the application.

**Decisions made**
- Several duplicate requests can share one work order, and one request produces at most one ([decision 0019](docs/decisions/0019-work-orders-and-triage.md)).
- The lifecycle has nine statuses and an explicit transition table, with `assigned` set by dispatch in Phase 5 and `awaiting approval` reserved for Phase 7. Only an administrator can reopen a closed or cancelled work order ([decision 0019](docs/decisions/0019-work-orders-and-triage.md)).

**Deferred**
- Nothing. The assignee filter arrived with Phase 5.

---

## Phase 5 — Dispatch and contractor workspace

**Goal:** Contractors see only their assigned jobs and can record what they do.

**Scope**
- Assigning and reassigning work orders, with a retained assignment history.
- A contractor workspace listing only assigned jobs.
- Job details containing just the information needed to do the work.
- Job notes, clarification requests, progress updates, and completion evidence.
- Marking work as ready for review.
- A layout usable on a phone in the field.

**Exit criteria**
- [x] Contractors cannot access unassigned jobs or internal records, including by direct ID.
- [x] Reassignment keeps the full history and attribution.
- [ ] The main contractor tasks work on a mobile screen. The layout is mobile first with large tap targets, but it still needs a check on a real phone.

**Decisions made**
- Internal staff and outside tradespeople share the contractor role, and a work order has one current contractor ([decision 0020](docs/decisions/0020-dispatch-and-contractor-access.md)).
- A contractor accepts a job or declines it with a reason, before starting ([decision 0020](docs/decisions/0020-dispatch-and-contractor-access.md)).
- A contractor sees the address and scope, then the resident's first name and entry instructions after accepting. Never a phone number, email, or full name. Questions go through the property team ([decision 0020](docs/decisions/0020-dispatch-and-contractor-access.md)).

---

## Phase 6 — Verification and closure

**Goal:** Managers confirm the outcome, record final costs, and close the work with a lasting history.

**Scope**
- Manager verification of work marked ready for review, with the ability to send it back.
- Recording the resolution and the final cost (exact decimal amounts with a currency).
- Closing the work order and updating the resident-visible status.
- Maintenance history visible at the property and unit level.

**Exit criteria**
- [ ] A seeded request can travel from report to closure through the UI.
- [ ] A closed work order shows a complete, correctly attributed timeline.
- [ ] Monetary values are stored and displayed exactly; times are stored in UTC.

**Decisions to make**
- What evidence is required before closure.
- Whether residents confirm the resolution or are only informed.

### ★ Milestone A — Core repair loop

The full maintenance lifecycle works end to end with real permissions. Review the product with this working slice before continuing, and adjust later phases if needed.

---

## Phase 7 — Estimates and owner approvals

**Goal:** Spending above a property's threshold cannot proceed without a recorded, authorized decision.

**Scope**
- Estimates recorded against a work order.
- Enforcement of property-level approval thresholds.
- Routing estimates above the threshold to authorized decision-makers.
- Approve or reject with a reason, recording the decision-maker and timestamp.
- An approval gate that blocks progress through **every** endpoint, not only the UI.
- An owner approval workspace showing the estimate, property, work requested, and decision history, without full access to internal management records.

**Exit criteria**
- [ ] Tests confirm that no endpoint or direct status change bypasses a required approval.
- [ ] Every decision is recorded with actor, timestamp, amount, and reason.
- [ ] Owners see only what their approval authority requires.

**Decisions to make**
- Who is authorized to approve: the property owner, a manager, or either depending on the amount.
- What happens when an estimate is revised after approval, or when the actual cost exceeds the approved amount.
- Whether a work order can have several competing estimates.
- What happens to a work order after a rejection.

---

## Phase 8 — Notifications and activity

**Goal:** Participants learn about events that need their action, and overdue or blocked work stands out.

**Scope**
- Notifications for assignment, status changes, estimate decisions, and closure.
- Highlighting of overdue and blocked work for managers.
- A polished, attribution-aware activity timeline for each role.
- Delivery channels behind a replaceable interface, so local development and tests need no external service.

**Exit criteria**
- [ ] Each actionable event notifies the right people and only them.
- [ ] Notifications respect the same visibility rules as the rest of the product.
- [ ] Tests run without any external messaging service.

**Decisions to make**
- Which channels the MVP includes: in-app only, or email as well.
- How "overdue" is defined, for example by urgency-based response targets or by due date only.
- Whether users can set notification preferences.

---

## Phase 9 — Reporting and export

**Goal:** Managers and owners understand workload, patterns, and spending.

**Scope**
- Open requests, work orders by status, overdue work, and contractor workload.
- Average resolution time.
- Repeat issues by property, unit, category, or contractor.
- Repair spend and approval activity.
- Export of records for operational review.

**Exit criteria**
- [ ] Every metric has a written definition and matches seeded test data.
- [ ] Reports respect organization, property, and role boundaries.
- [ ] Exports contain only data the requesting user is allowed to see.

**Decisions to make**
- Metric definitions, for example whether resolution time starts at request submission or at work-order creation.
- Export formats.
- Which time zone reports use (data is stored in UTC; properties have local times).

### ★ Milestone B — Feature-complete MVP

Every capability described in the product documents exists, is tested, and is respected by permissions.

---

## Phase 10 — Production readiness

**Goal:** WorkLedger can be deployed, operated, and recovered safely.

**Scope**
- Migrations and the test suite verified against PostgreSQL.
- Security hardening: HTTPS, session hardening, request validation review, upload safety, and protection against brute-force sign-in.
- A deployment environment for staging and production.
- Backups with a tested restore, plus data retention policies.
- Logging and monitoring that do not leak personal data.
- An accessibility and responsive-layout review.
- Performance checks at the upper target size (around 300 units, with multi-year history).
- User-facing help for each workspace.

**Exit criteria**
- [ ] A staging environment runs the product over HTTPS.
- [ ] A backup has been restored successfully.
- [ ] A security review has been completed and its findings resolved or accepted.
- [ ] Main pages stay responsive with realistic data volumes.

**Decisions to make**
- The hosting provider and the file-storage service.
- Retention periods for closed work, attachments, and departed residents.

### ★ Milestone C — Pilot

A real or realistic firm runs its maintenance through WorkLedger. Their feedback shapes the next roadmap.

---

## Cross-cutting work (every phase)

These are not separate phases. Each phase must account for them before it is marked done.

- **Authorization tests** for every new endpoint: allowed and denied cases, including cross-organization and direct-ID access.
- **Activity events** for every meaningful change.
- **Resident privacy:** no internal or sensitive data in resident-facing responses.
- **Transactional integrity:** failed operations leave no partial changes.
- **Time and money:** UTC timestamps and exact decimal amounts with a currency.
- **Responsive UI** usable on desktop and mobile.
- **Seed data** kept up to date so every feature can be demonstrated.
- **Decision log** entries for each resolved open question.

---

## Known gaps in the source documents

These came up while reviewing the product documents. Each is assigned to the phase where it must be resolved.

| Gap | Resolve in | Status |
| --- | --- | --- |
| "Owner" means both the firm's owner (the buyer) and a property owner (an approver). These need distinct terms. | 0 | ✅ [Glossary](docs/glossary.md) |
| The project description lists "maintenance staff" as daily users, but no such role appears in the README. | 5 | ⬜ |
| Independent contractors may work for several firms, which complicates strict organization isolation. | 1 | ✅ [0005](docs/decisions/0005-accounts-and-memberships.md) |
| Buildings appear in the README's capabilities but not in the domain model. | 2 | ⬜ |
| Request and work-order statuses and transitions are not defined. | 3, 4 | ⬜ |
| The relationship between requests and work orders (one-to-one or many-to-one) is not defined. | 4 | ⬜ |
| It is unclear whether approvals come from owners, managers, or both, and how revised estimates are handled. | 7 | ⬜ |
| Notification channels are unspecified, yet password reset and invitations may need email earlier. | 1, 8 | 🟨 Email interface in [0007](docs/decisions/0007-email-interface.md); channels in Phase 8 |
| Reporting metrics and export formats are named but not defined. | 9 | ⬜ |
| Development instructions cover only Windows PowerShell. | 0 | ✅ README |
| The README's layout references `docs/` and `.env.example`, which do not exist yet. | 0 | ✅ |

---

## Later (not planned)

These ideas are outside the current scope. They are listed so they are not lost, not as commitments.

- Preventive and recurring maintenance schedules.
- Contractor invoicing and payment tracking.
- Integrations with property-management or accounting systems.
- SMS or push notifications.
- Resident satisfaction feedback after closure.
- Multi-language support.
- A native mobile application.
