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
A person living in a unit who reports problems and follows their own requests.

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
A structure within a property. **Open:** whether this is a separate record ([Phase 2](../ROADMAP.md#phase-2--property-and-unit-directory)).

**Unit**
A rentable space within a property, such as an apartment. Maintenance requests are reported against a unit.

## Maintenance workflow

**Maintenance request**
A resident's report of a problem, recorded as submitted. A request is not yet a commitment to do work.

**Reference number**
The human-readable identifier given to a maintenance request so residents and managers can refer to it.

**Triage**
A manager's review of a new request: confirming urgency, checking for duplicates, and deciding whether to create a work order.

**Work order**
The durable record of the operational response to a request: scope, priority, assignment, estimates, approvals, work performed, costs, and history.

**Dispatch**
Assigning a work order to a contractor.

**Assignment**
The record that a specific contractor is responsible for a work order during a period of time. Reassignment creates a new assignment and keeps the old one in history.

**Estimate**
A contractor's expected cost for a work order, recorded as an exact amount with a currency.

**Approval threshold**
The spending limit set for a property. Estimates above it need an approval decision before work can proceed.

**Approval decision**
A recorded approval or rejection of an estimate, with the decision-maker, timestamp, and reason.

**Verification**
A manager's confirmation that completed work resolves the problem.

**Closure**
The final state of a work order once work is verified and final costs are recorded.

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
