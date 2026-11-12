# WorkLedger — Product Description

## One-line description

**WorkLedger is a property maintenance coordination platform that connects resident repair requests, property managers, and independent contractors in one accountable workflow.**

## Short description

WorkLedger helps small residential property management firms coordinate maintenance from the first report to the final repair record. Residents report issues, managers assess and dispatch work, contractors provide updates and estimates, and owners review higher-cost decisions. Every request stays connected to its assignments, decisions, notes, and history, giving each participant the information they need without exposing details they should not see.

## Product concept

WorkLedger is built for firms responsible for roughly 20–300 rental units across one or more properties. These teams often coordinate repairs through email, telephone calls, spreadsheets, and contractor messaging. Information gets lost as a request passes from resident to manager to contractor, and nobody has a dependable answer to three simple questions: **What needs attention? Who owns the next action? What happened?**

The product replaces that fragmented process with a shared operational record. A resident reports a leaking sink. A manager checks urgency and creates a work order. A contractor accepts the assignment, shares an estimate if needed, and documents the repair. If the cost exceeds the property's approval threshold, an authorized owner or manager makes a recorded decision. When work is verified and closed, the property retains a useful maintenance history.

## Customer and business value

**Primary customer:** A small or midsize independent residential property management company overseeing multiple units and using its own staff or independent contractors for repairs.

**Primary buyer:** The firm's owner, operations lead, or head property manager.

**Daily users:** Property managers and coordinators, residents, contractors, maintenance staff, and property owners involved in approval decisions.

**Value delivered:**

- Fewer requests lost between intake and dispatch.
- Clear ownership and next actions for outstanding maintenance work.
- Less time spent asking for updates or searching message threads.
- Consistent records of estimates, approvals, work performed, and costs.
- Better visibility into overdue jobs and repeated property issues.
- A maintenance-specific workflow without requiring tenants and contractors to learn a broad enterprise management platform.

These are the problems the product is designed to address, not claimed performance results.

## What makes the product focused

WorkLedger does not try to replace accounting, rent collection, lease management, or an entire property management system. Its core responsibility is **maintenance coordination**, especially when work crosses organizational boundaries between a manager, a resident, a property owner, and an independent contractor.

The interface favors clear actions: report, assess, assign, estimate, approve, perform, verify, and close. Role-specific views keep operational details visible to the right people, while the underlying record remains consistent.

## End-to-end experience

### Resident

A resident opens their property workspace, selects the affected unit, describes an issue, attaches relevant evidence, and submits a maintenance request. The request has a reference number and an understandable status timeline. Updates visible to residents are separated from the manager's internal notes.

### Property manager

The manager opens a queue grouped by urgency, property, and age. They review new requests, reject duplicates when appropriate, create work orders, dispatch contractors, and monitor blocked or overdue jobs. The work-order page provides a single place to inspect the job scope, assignment, estimate, approvals, and history.

### Contractor

The contractor sees only assigned jobs and information necessary to perform them. They record progress, request clarification, submit estimates, attach completion evidence, and mark work ready for review. Assignment changes and status updates are attributed to the responsible actor.

### Property owner

An owner with approval authority sees the estimate, property, requested work, and decision history. They approve or reject amounts that require consent under the property's spending rules, without needing unrestricted access to every internal management record.

### Administration

An organization administrator manages the organization's properties, unit directory, membership, and access. Organization boundaries are enforced across the API and persistence layers.

## Key capabilities

**Maintenance intake:** Structured requests with unit association, categories, urgency, descriptions, and attachments.

**Work-order operations:** Triage, dispatch, assignment, priority, due dates, status progression, and resolution tracking.

**Contractor collaboration:** Job-specific notes, estimates, progress updates, and completion evidence.

**Approval controls:** Property-level spending thresholds with recorded approvals and rejections.

**Transparent history:** Attribution-aware activity events and separation of public updates from internal records.

**Operational insight:** Open-work queues, age and resolution reporting, contractor workload, repeat issues, and repair spend.

**Access boundaries:** Organization, property, role, and record-level permissions protecting resident and business information.

## Product and engineering characteristics

- Responsive web application suited to desktop operations and mobile field use.
- React and TypeScript frontend backed by a Python FastAPI service.
- Relational data modeling using SQLAlchemy, Alembic, and PostgreSQL-compatible persistence.
- Local SQLite execution and isolated automated tests without paid services.
- Server-side authorization, explicit workflow validation, transactional updates, and audit history.
- Clear APIs and a modular architecture for independently evolving product areas.

## Product outcome

WorkLedger gives a property management company one place to understand the full lifecycle of a repair: **what was reported, why it mattered, who handled it, what was approved, what was done, and when it was completed.** That record is valuable to residents looking for clarity, managers running daily operations, contractors delivering work, and owners overseeing their properties.
