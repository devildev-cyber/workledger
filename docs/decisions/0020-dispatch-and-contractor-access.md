# 0020. Dispatch and what a contractor can see

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

A contractor works inside someone else's properties and homes. They need enough to do the job, and no more: not other contractors' work, not the manager's private notes, not residents' contact details. Managers need to hand work over, take it back, and see exactly who held it and when.

## Decision

**Who can be assigned**

- Internal maintenance staff are not a separate role. Anyone who does the work holds the `contractor` role, whether they are a firm's own employee or an outside tradesperson.
- A work order has **one current contractor**. Handing it to someone else ends the first assignment and starts another. Two people on one job is two work orders.
- Managers assign only people who hold the contractor role in the same organization. An unknown ID, a manager, and a contractor from another organization all get the same `404`.
- Assigning follows the work order's property scope, so a manager cannot assign work at a property they do not look after.

**Assignment record**

- Every assignment is a row: who, assigned by whom, when, the contractor's reply, and how and when it ended (`reassigned`, `unassigned`, `declined`, `cancelled`). Nothing is overwritten or deleted. A database rule allows only one open assignment per work order.
- Assigning, reassigning, removing, accepting, and declining each add a history entry on the work order and an activity event.

**Accept and decline**

- A new assignment waits for the contractor's reply. They can **accept** it, or **decline** it with a reason, but only before accepting. A declined job returns to the manager as `open` with the reason in its history. Once accepted, a contractor who cannot continue tells the manager, who reassigns.
- Until the job is accepted, the contractor sees the address, the scope, and the due date, and whatever notes or files the manager chose to share. No resident details.

**Status**

- Assigning an open or on-hold work order moves it to `assigned`. Reassigning a job already in progress keeps its status. Removing the contractor, or a decline, returns an `assigned` job to `open`. Cancelling the work order ends the assignment.
- A contractor makes only four moves: start (assigned to in progress), pause (in progress to on hold), resume (on hold to in progress), and finish (in progress to **ready for review**). Pausing and finishing need a written note. Completing, closing, cancelling, and everything else belong to the manager.
- A work order can be assigned while it is open, assigned, in progress, or on hold. Not once it is waiting for review, finished, or awaiting approval.
- A refused action changes nothing: the checks run before anything is written.

**What a contractor can see**

A contractor sees only jobs where they hold the current assignment. Any other job, whether it is unassigned, someone else's, in another organization, or a job they used to hold, looks missing (`404`), including when the address is typed by hand. Lists, details, files, and every action use the same lookup.

- Shown: reference, title, scope, kind of work, priority, due date, property and unit, street address, and the status.
- Shown after accepting: the resident's **first name** and their entry instructions (the access notes from the request and the resident's standing instructions).
- Never shown: a resident's phone number, email, or full name, other contractors, the people on the manager's side, linked request numbers, the activity log, costs, and internal notes.
- Questions for a resident go through the property team, using a "question" entry.
- The contractor response models have no fields for the withheld data, so it cannot leak by accident.
- Manager notes and files are internal unless the manager chooses to share them with the contractor.
- A status change made by someone else shows its new status but not its reason, in case the reason is internal. The contractor's own reasons are shown to them.
- Other people's names are replaced with "You", "Property team", or "System".

**Notes, progress, and evidence**

- A contractor can add a note, a progress update, or a question for the property team. Managers read all of them in the work order history.
- Evidence is a photo or PDF attached to the job. It uses the same rules as request attachments (type from the file's bytes, size limit), with a limit of 20 files per work order. Files a contractor adds are visible to the job's contractor and to staff, never to the resident.
- A finished job can still be read but no longer changed.

**Filters**

Managers filter work orders by contractor or by "not assigned", which Phase 4 deferred.

## Consequences

- A contractor who needs a resident's phone number must ask the property team. This is slower for the contractor, and deliberate.
- First names can still identify someone in a small building. This is accepted; the alternative is a contractor knocking on a door without knowing whom to ask for.
- Evidence is not yet tied to a specific update, only to the job.
- A contractor is not told about a new job until they open the app. Notifications arrive in Phase 8.
- Estimates and the approval gate (`awaiting approval`) arrive in Phase 7. They will add to what a contractor can do, but not what they can see.
