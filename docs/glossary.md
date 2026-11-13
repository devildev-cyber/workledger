# Glossary

Shared vocabulary for WorkLedger. Use these terms consistently in code, the interface, and documentation. Terms marked **Open** are not settled yet; the linked roadmap phase decides them.

## Organizations and people

**Organization**
A property management firm using WorkLedger. Every property, user membership, and maintenance record belongs to exactly one organization, and data never crosses organization boundaries.

**Firm principal**
The owner or operations lead of a management firm, typically the person who buys WorkLedger. Not a product role; use this term only when discussing customers. Do not call them an "owner", which is reserved for property owners.

**User account**
A person's single login. An account belongs to the person, not to an organization ([decision 0005](decisions/0005-accounts-and-memberships.md)).

**Membership**
The link between a user account and one organization, carrying that user's roles there. A user can have memberships in several organizations but always acts within one at a time.

**Invitation**
A single-use, expiring offer to join an organization with given roles, sent by email. The only way to gain a membership ([decision 0006](decisions/0006-invitation-only-accounts.md)).

**Role**
What a member is allowed to do: administrator, manager, resident, contractor, or property owner.

**Administrator**
A member who manages the organization's properties, units, memberships, and access settings.

**Manager**
A property manager or coordinator who triages requests, creates and dispatches work orders, and verifies completed work. Acts only on properties assigned to them ([decision 0008](decisions/0008-property-scoped-managers.md)).

**Resident**
A person living in a unit who reports problems and follows their own requests. The directory record may exist before the person has an account, and is linked to them by email ([decision 0016](decisions/0016-residents-and-tenancies.md)).

**Tenancy**
The period a resident lives in a unit: a move-in date and an optional move-out date. A resident can have several, and a unit can have several current ones.

**Contractor**
An independent tradesperson or company assigned to carry out work orders. Sees only assigned jobs. A contractor serving several organizations has one account with a membership in each.

**Maintenance staff**
In-house repair workers employed by the firm. **Open:** whether this is a separate role or the same as contractor ([Phase 5](../ROADMAP.md#phase-5--dispatch-and-contractor-workspace)).

**Property owner**
The person or entity that owns a property and approves spending above its approval threshold. Always write "property owner", never just "owner".

## Places

**Property**
A managed real estate asset, such as an apartment complex or a house, belonging to one organization.

**Building**
A structure within a property. An optional record: a property with no buildings holds its units directly ([decision 0015](decisions/0015-property-directory.md)).

**Unit**
A rentable space within a property, such as an apartment. Maintenance requests are reported against a unit.

## Maintenance workflow

**Maintenance request**
A resident's report of a problem, recorded as submitted. A request is not yet a commitment to do work.

**Reference number**
The human-readable identifier given to a maintenance request so residents and managers can refer to it, such as `REQ-0042`. Numbered per organization.

**Request status**
Where a request stands, in the words a resident sees: received, in review, in progress, resolved, closed, withdrawn, or declined ([decision 0017](decisions/0017-maintenance-requests.md), [0019](decisions/0019-work-orders-and-triage.md)).

**Timeline**
The list of things that happened on a request: when it was submitted, each status change, and each message or note. Every entry is either resident-visible or internal.

**Triage**
A manager's review of a new request: confirming urgency, checking for duplicates, and deciding whether to create a work order, mark it as a duplicate, or decline it with a reason. A request is "waiting for triage" until it is linked to a work order or another request, or finished.

**Duplicate**
A request that reports a problem already reported. It stays open and follows the original's work order.

**Work order lifecycle**
The statuses a work order moves through, from open to closed or cancelled, and the moves allowed between them ([decision 0019](decisions/0019-work-orders-and-triage.md)). A move the lifecycle does not allow is refused.

**Work order**
The durable record of the operational response to a request: scope, priority, assignment, estimates, approvals, work performed, costs, and history.

**Dispatch**
Assigning a work order to a contractor. A work order has one current contractor, who accepts the job or declines it with a reason ([decision 0020](decisions/0020-dispatch-and-contractor-access.md)).

**Assignment**
The record that a specific contractor is responsible for a work order during a period of time. Reassignment creates a new assignment and keeps the old one in history.

**Job**
A work order as a contractor sees it: only the details needed to do the work, and only while it is assigned to them.

**Ready for review**
The status a contractor sets when the work is done, with a note describing what was done. The manager decides whether it is complete.

**Verification**
A manager's review of work that is ready for review: either *verify* it (recording the resolution and optional final cost, which completes the work order) or *send it back* with a reason ([decision 0021](decisions/0021-verification-and-closure.md)).

**Resolution**
The manager's record of what was actually done, written when work is verified. Staff only.

**Final cost**
What the work cost, recorded when it is verified as an exact amount in whole cents with a currency. Optional, and staff only.

**Maintenance history**
The verified work at a property, or at one unit, with its cost.

**Estimate**
The expected cost of a work order, recorded by a manager as an exact amount in the property's currency. Never edited: a revision replaces it and the earlier one stays on record.

**Approval threshold**
The spending limit set for a property. An estimate above it (not at it) needs a property owner's decision before work can proceed. No threshold means no estimate needs approval.

**Approval decision**
A property owner's recorded approval or rejection of an estimate, with the decision-maker, timestamp, and reason. Rejecting needs a reason.

**Approval gate**
The rule that holds a work order while its current estimate needs approval and has not been approved. It is checked on every status change, not only in the screen.

**Verification**
A manager's confirmation that completed work resolves the problem.

**Closure**
The final state of a work order once work is verified and final costs are recorded.

**Blocked**
A work order that cannot move until someone acts: on hold, or waiting for a property owner's approval.

**Overdue**
Open work whose due date has passed. Finished work is never overdue.

## Records and visibility

**Work note**
A note attached to a work order. Each note is either internal or resident-visible.

**Internal note**
A note visible only to the organization's managers and authorized roles. Never shown to residents.

**Resident-visible update**
Information on a request or work order that the resident is allowed to see.

**Attachment**
A file, such as a photo or document, attached to a request or work order, with its own visibility rules.

**Activity event**
An entry in a record's history: who did what, when, and the relevant before and after values.

**Notification**
A short message telling one person that something needs their attention. It shows in the app, and as an email copy unless the person turned email off. It names a record by reference and title and never repeats its contents. See [decision 0023](decisions/0023-notifications-and-attention.md).

**Property team**
The managers assigned to a property, or the organization's administrators when nobody is assigned. It is who is told about events that need staff.

**Report period**
A range of whole UTC days, both ends included, that a report or export covers. The default is the last 90 days. Figures about the present, such as open requests, ignore it. See [decision 0024](decisions/0024-reports-and-exports.md).

**Time to resolve**
How long it took to put right a problem: from the resident's earliest linked request to the manager's verification of the work. A work order with no request starts at its creation.

**Repeat issue**
Two or more non-cancelled work orders of the same category at the same unit (or in the same property's common areas) created within the report period.

**Export**
A CSV file of records for operational review. It holds only what the person asking may already see, and never residents' names, descriptions or notes.

**Lock-out**
A short refusal of sign-in after too many wrong passwords for one account (default 5 in 15 minutes). It ends by itself and does not mark the account. See [decision 0025](decisions/0025-production-readiness.md).

**Backup**
A folder holding the database, the uploaded files and a manifest of checksums, made by `python -m app.ops backup`. It is only a backup once it is also stored off the machine and has been restored at least once.

**Housekeeping (purge)**
Routine deletion of expired operational records, such as old sessions and reset links. It never deletes requests, work orders, files or the activity history.

**Readiness check**
`/api/health/ready`: answers whether the API can reach its database. It is what monitors and the container health check use.
