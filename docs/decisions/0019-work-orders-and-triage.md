# 0019. Work orders, triage, and the status lifecycle

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

A request is what a resident reported. A work order is what the firm decides to do about it. Managers need a queue to review new requests, and work orders need a lifecycle that cannot be bent: a job should not jump from open to completed, and a refused change must never leave half of itself behind.

## Decision

**Requests and work orders**

- A request links to at most one work order. Several requests can share one work order, which is how repeat reports of the same problem are handled. One request never produces several work orders. If a second job is needed, raise a work order without a request.
- A work order can also be raised on its own, with no request (for example routine upkeep).
- Triage has three outcomes, each available only while a request is `submitted` or `in_review` and not yet linked to anything:
  - **Create work order.** Details are copied from the request and can be changed first. Any reports already marked as duplicates of it join the same work order.
  - **Mark as duplicate.** Points at the original report at the same property. The resident keeps following their own request and is told it was linked to an earlier report, without being told who made it. If the original already has a work order, the duplicate joins it.
  - **Decline.** A new final request status, `declined`, with a reason that is always written to the resident.
- Once a request is linked to a work order, the work order decides its status (table below), and a manager can no longer change it by hand. A resident can no longer withdraw it, because the work is planned. They can still message.
- A request the resident withdrew, or one that was declined, is never touched by its work order.

**What the resident is told as the work order moves**

| Work order | Request shows |
| --- | --- |
| open | In review |
| assigned, in progress, on hold, awaiting approval, ready for review | In progress |
| completed | Resolved |
| closed, cancelled | Closed |

If an administrator reopens a closed work order, its closed requests reopen with it.

**Lifecycle**

Statuses: open, assigned, in progress, on hold, awaiting approval, ready for review, completed, closed, cancelled. Allowed moves:

| From | To |
| --- | --- |
| open | assigned, in progress, on hold, cancelled |
| assigned | open, in progress, on hold, awaiting approval, cancelled |
| in progress | on hold, awaiting approval, ready for review, cancelled |
| on hold | open, assigned, in progress, cancelled |
| awaiting approval | in progress, assigned, cancelled |
| ready for review | in progress, completed |
| completed | closed, in progress |
| closed | in progress |
| cancelled | open |

- `assigned` is set by dispatch ([decision 0020](0020-dispatch-and-contractor-access.md)) and `awaiting approval` belongs to Phase 7. Neither can be set by hand.
- Leaving `closed` or `cancelled` needs an administrator (`403` for a manager). Everything else is open to managers at the property.
- Leaving `ready for review` is a review, not a plain status change ([decision 0021](0021-verification-and-closure.md)).
- A move the table does not allow is refused with `409` and an explanation. Every check runs before anything is changed, so a refused move leaves the work order, its history, its requests, and the activity log exactly as they were.
- A closed or cancelled work order cannot be edited until an administrator reopens it.

**History**

- Every change is an entry on the work order: created, request linked, status changed (with an optional reason), details edited (each field with its value before and after), and notes. Each entry records who and when. Status changes, edits, creation, and each triage outcome also go to the activity log.
- A note is internal or shared with the resident. A shared note is copied to the timeline of every linked request, because that is where residents look.
- Work orders are numbered per organization as `WO-0001`, in the same way as requests.
- Overdue is worked out when read: the due date has passed and the work order is not completed, closed, or cancelled.

**Access**

Administrators and managers only, and managers only at properties assigned to them. A work order at another property looks missing (`404`). Contractors see only their own assigned jobs, through a separate workspace ([decision 0020](0020-dispatch-and-contractor-access.md)). Owners have no access yet (Phase 7).

## Consequences

- Filters are property, status, priority, contractor, search text, and age.
- Searching reads titles, scope text, and reference numbers. Residents' names are searchable on requests only.
- Lists show the newest 200. Paging is deferred until a real portfolio needs it.
- Moving a status back from `completed` reopens its requests too. This is intended: a resident told "resolved" should hear if the problem returns.
