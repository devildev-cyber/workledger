# WorkLedger

**Maintenance coordination for independent property management teams.**

WorkLedger brings residents, property managers, and service contractors into one accountable repair workflow. A maintenance request starts with a clear problem report and ends with a documented resolution—without losing information across emails, phone calls, spreadsheets, and messaging apps.

WorkLedger is designed for small and growing residential property management firms that oversee multiple buildings, coordinate outside contractors, and need a reliable record of maintenance activity without the overhead of a full property-management suite.

## Why WorkLedger

Maintenance is a coordination problem as much as a repair problem. Residents need to know their requests were received. Managers need to understand urgency, ownership, and cost. Contractors need clear instructions and a place to record what they did. Property owners need visibility into spending and outcomes.

WorkLedger keeps those interactions attached to the same maintenance record, from intake through closure.

## Who uses it

| User | What they need | WorkLedger workspace |
| --- | --- | --- |
| Property manager | Understand the repair queue, dispatch work, track response and cost | Operations dashboard, requests, work orders, approvals |
| Resident | Report a problem and see updates without chasing the manager | Resident request and status views |
| Contractor | See assigned jobs, clarify details, submit estimates, document work | Contractor job workspace |
| Property owner | Understand repair expenditure and approve work above agreed limits | Property-specific approvals and history |
| Organization administrator | Control properties, users, access, and organization settings | Administration and access controls |

## How maintenance flows through the product

1. **Report** — A resident describes a problem, identifies the unit, provides access notes, and can attach supporting photos.
2. **Triage** — A manager reviews the report, confirms urgency, checks for duplicates, and turns it into an actionable work order.
3. **Dispatch** — A contractor receives a clear assignment with scope, property location, timing information, and a contact path.
4. **Estimate and approve** — Repair estimates are recorded against the work order. Estimates above the property's spending threshold require an authorized approval decision.
5. **Execute** — The contractor records progress, notes, and evidence of work. Managers can see blockers and changes in one timeline.
6. **Verify and close** — The manager confirms the resolution, records final costs, and closes the work order. The history remains available for reporting and follow-up.

A work order is the durable record of the repair; messages, estimates, assignments, approvals, and activity are connected to it rather than scattered across separate tools.

## Product capabilities

### Property and unit directory

- Organize properties, buildings, and units under the correct management organization.
- Associate residents with units and maintain contacts and access instructions.
- Preserve maintenance history at both the property and unit level.
- Find recurring issues by property, unit, category, or contractor.

### Resident request intake

- Structured reports with category, description, urgency, location, and supporting attachments.
- Confirmation and an understandable status timeline for each request.
- Resident visibility restricted to their own unit's authorized requests.
- Clear separation between resident-visible updates and internal operational notes.

### Work-order management

- Convert approved intake reports into trackable work orders.
- Maintain priority, category, assignment, due dates, and status history.
- Search and filter by property, status, assignee, urgency, and age.
- Prevent unauthorized transitions, conflicting assignments, and invalid cross-property actions.

### Contractor coordination

- Show contractors only the work relevant to their assignments.
- Record job notes, attendance details, completion evidence, and repair outcomes.
- Track estimates, actual costs, and requests for clarification in the context of a job.
- Maintain accountability when an assignment changes hands.

### Estimates and owner approvals

- Define property-specific spending limits and approval rules.
- Route estimates above the configured limit to an authorized decision-maker.
- Record the estimate, approval or rejection, decision-maker, and timestamps.
- Block work from advancing past the approval gate when required.

### Notifications and activity

- Surface actionable events such as assignment, status changes, estimate decisions, and closure.
- Preserve a chronological, attribution-aware activity history.
- Keep internal notes separate from resident-facing updates.
- Present overdue and blocked work prominently for operational follow-up.

### Reporting

- Monitor open requests, work orders by status, average resolution time, overdue work, and contractor workload.
- Understand maintenance patterns across properties and individual units.
- Track repair costs, approval activity, and closed-work history.
- Export useful records for operational review.

## Workspaces

**Manager dashboard** — Queue overview, urgent and overdue work, property filters, assignment actions, and recent activity.

**Resident portal** — New request form, request list, status timeline, and resident-visible messages.

**Contractor workspace** — Assigned work, job details, progress updates, estimates, and completion evidence.

**Owner approvals** — Estimates awaiting a decision, approval history, and property-level cost context.

**Administration** — Organization membership, properties, units, roles, and permission settings.

## Core operating rules

WorkLedger treats data separation and workflow correctness as product requirements, not optional interface details.

- **Organization isolation:** Users and resources belong to an organization; authorization is enforced by the server on every access, including direct URL or ID access.
- **Principle of least privilege:** Residents see their permitted requests; contractors see assigned work; managers act within their assigned organization and properties; owner approvals follow explicit authority.
- **Consistent state changes:** Invalid transitions are rejected without partially modifying a work order or its activity history.
- **Approval protection:** Work requiring an approval cannot bypass it through another endpoint or a direct status update.
- **Reliable attribution:** Meaningful changes record the actor, event type, timestamp, and relevant before/after context.
- **Resident privacy:** Internal notes, private contacts, and sensitive attachments are never exposed through resident-facing responses.
- **Predictable time and money handling:** Times are stored in UTC; monetary amounts use exact decimal types and a declared currency.

## Technology and architecture

| Layer | Technology |
| --- | --- |
| Web application | React, TypeScript, Vite, Tailwind CSS |
| Backend API | Python 3.11+, FastAPI, Pydantic |
| Data access | SQLAlchemy 2.x, Alembic |
| Persistence | SQLite for local development and tests; PostgreSQL for production deployment |
| Authentication | Secure, server-managed sessions with role-based authorization |
| Backend quality | Pytest, httpx2, Ruff |
| Frontend quality | Vitest, React Testing Library, ESLint |
| API documentation | OpenAPI via FastAPI |

The application is organized as a small monorepo. Domain logic lives in backend services rather than being duplicated in route handlers or React components. External integrations are behind replaceable interfaces so local development and automated tests do not depend on paid services.

```text
workledger/
├── backend/
│   ├── app/
│   │   ├── api/                 # Authenticated HTTP routes
│   │   ├── core/                # Configuration, security, permissions
│   │   ├── db/                  # Session and migration integration
│   │   ├── models/              # Persistent entities
│   │   ├── schemas/             # API contracts
│   │   ├── services/            # Business rules and workflows
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── features/
│   │   ├── pages/
│   │   └── routes/
│   └── package.json
├── docs/
├── .env.example
└── README.md
```

## Domain model

The central records are **Organization**, **Property**, **Unit**, **Membership**, **Resident**, **MaintenanceRequest**, **WorkOrder**, **Assignment**, **Estimate**, **ApprovalDecision**, **WorkNote**, **Attachment**, and **ActivityEvent**.

A maintenance request records the resident's report. A work order records the operational response. Linking, rather than conflating, these records makes it possible to triage repeat reports, capture the reason for work, and retain an accurate timeline.

## Project documentation

- [Roadmap](ROADMAP.md): delivery phases, exit criteria, and open questions
- [Glossary](docs/glossary.md): shared product vocabulary
- [Decision log](docs/decisions/README.md): significant decisions and their reasons

## Local development

**Requirements:** Python 3.11+, Node.js 20+, and Git. Local development uses SQLite and does not require Docker, hosted infrastructure, or paid credentials.

### 1. Configure the environment (once)

From the repository root, copy the example settings and generate a secret key:

```bash
# Linux and macOS
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the printed value after `WORKLEDGER_SECRET_KEY=` in `.env`. The backend refuses to start without it. Every setting is documented in [`.env.example`](.env.example). Never commit `.env`, secrets, or real customer data.

### 2. Backend

```bash
# Linux and macOS
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

```powershell
# Windows (PowerShell)
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

`alembic upgrade head` creates or updates the local SQLite database, `backend/workledger.db`. Run it again whenever new migrations arrive.

Accounts are created by invitation only, so a new installation needs its first organization and administrator. Create them once, from `backend/` with the virtual environment active. The password is requested at a hidden prompt:

```bash
python -m app.bootstrap --organization "Harbor Property Management" \
  --email admin@example.com --name "Alex Rivera"
```

The command refuses to run if the email already has an account.

Photos and PDFs attached to requests are saved in `backend/uploads/` (change it with `WORKLEDGER_UPLOAD_DIR`). Back that folder up together with the database.

During development no email is actually sent. Each message the backend would send, such as an invitation or password reset link, is written to `backend/outbox/` as an `.eml` file you can open in any mail client or text editor.

### 3. Frontend (second terminal)

The commands are the same on every platform:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173` and sign in with the administrator you created in step 2. The backend must be running. The frontend development server forwards every `/api` request to `http://localhost:8000`, so the browser only ever talks to one address. If your backend runs elsewhere, set `WORKLEDGER_API_URL` before `npm run dev`.

### Local addresses

- Frontend: `http://localhost:5173`
- API health check: `http://localhost:8000/api/health`
- API reference: `http://localhost:8000/docs`

To explore a filled-in system, load the synthetic demo organization (a separate command, for a fresh database):

```bash
python -m app.seed
```

It creates "Harbor Demo Properties" with three properties, 24 units, 18 residents, 10 maintenance requests (five waiting for triage and five already turned into work orders in different statuses, three of them assigned to the demo contractor, one waiting for the manager to verify), plus sign-ins for each role (`admin@demo.example`, `manager@demo.example`, `resident@demo.example`, `contractor@demo.example`, `owner@demo.example`). One random password is printed once, so note it down. All names, emails, and phone numbers are invented. The command refuses to run twice.

## Tests and code quality

These are the same checks that CI runs on every pull request:

```bash
# From backend/, with the virtual environment active
ruff check .
ruff format --check .
pytest -q

# From frontend/
npm run lint
npm test
npm run build
```

Test coverage prioritizes tenant isolation, role permissions, assignment validation, status transitions, request visibility, audit events, and failure-path transaction integrity. The test suite uses its own disposable data and does not require an external service.

## Design principles

- **One clear record for each repair:** Intake, dispatch, estimates, execution, and closure remain connected.
- **Useful to smaller teams:** Straightforward screens and focused actions matter more than enterprise configuration.
- **Operational accountability:** Important decisions have an actor, a timestamp, and a reason.
- **Real data integrity:** Permissions, state transitions, and approval rules are enforced below the UI.
- **Practical local development:** Contributors can reproduce issues and run meaningful tests on a laptop.

## Security and data handling

Use environment-based secrets, hashed passwords, HTTP-only session cookies, explicit authorization checks, request validation, controlled uploads, and safe error responses. Never store real tenant personal data in demo fixtures. Deployment requires HTTPS, session hardening, backup and retention policies, and operational monitoring.

