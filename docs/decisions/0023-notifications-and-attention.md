# 0023. Notifications, blocked and overdue work, and who did what

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Participants should learn about events that need them without having to ask, and managers should see stuck work stand out. Notifications are also the easiest place to leak: a message sent to the wrong person, or one that repeats an internal note or an amount, undoes the care taken in every screen. The rules for who is told, and what the message may say, have to be stricter than for the screens.

## Decision

**Channels and preferences**

- Every notification appears **in the app**, under *Notifications*, with an unread count in the navigation. This channel cannot be turned off: it is where an actionable event is guaranteed to be seen.
- An **email copy** is also sent, through the same replaceable `EmailSender` as invitations ([decision 0007](0007-email-interface.md)). Tests use the in-memory sender and local development writes `.eml` files, so nothing needs an external service.
- The only preference is email on or off, kept per person *per organization* (a person who works for two firms can quiet one). It is a column on the membership.
- SMS and push are not included ([ROADMAP](../../ROADMAP.md), "Later").
- Email copies are sent **after the commit**, so nobody is emailed about a change that was rolled back. A refused request creates no notification and sends no email. A failure to send is logged and never turns a saved change into an error.

**Who is told, and only them**

| Event | Told | Never told |
| --- | --- | --- |
| A request is submitted | The property's managers; if it has none, the organization's administrators | Anyone else. A resident whose request was logged for them by staff is told it exists |
| The resident replies | The property team | |
| A request changes status, or staff write to the resident | The resident | |
| A work order is assigned | The contractor | |
| A contractor is removed or replaced | That contractor | |
| The contractor accepts or declines | The property team | |
| The contractor marks the work ready for review | The property team | |
| The contractor puts the job on hold | The property team | |
| A manager or owner puts the job on hold, resumes it, cancels it, closes it, or holds it for approval | The contractor | |
| Work is verified, or sent back | The contractor | |
| An estimate needs a decision | The property's owners | The contractor, residents |
| An owner decides | Whoever recorded the estimate, and the property team | The owner who decided |
| Approved work is completed | The property's owners | |

- **The person who acted is never told about their own action.**
- A recipient must **still hold the role** the notification is for in that organization at the moment it is written. Removing a role, removing someone from a property, or removing the member ends the notifications with it.
- A notification **names a record, not its contents**. It carries a reference and a title the recipient can already read, such as "WO-0003 needs your decision: No hot water". It never carries amounts, notes, reasons (a decline, rejection or send-back reason), names of other people, phone numbers or access instructions. The reason lives on the record, behind its own permission checks. Tests scan every person's notifications for planted secrets.
- Each notification stores which **screen** it opens, chosen for the person it was written for: the same work order opens at *Work orders* for a manager, *My jobs* for the contractor and *Approvals* for an owner. A job a contractor no longer has opens their list instead of a missing page.
- A person reads and marks read only their **own** notifications, in the organization in the URL. Another person's notification, and any notification in another organization, looks like it does not exist (`404`).

**Blocked and overdue work**

- **Overdue** is defined by the due date alone: open work whose due date has passed. Urgency-based response targets are deferred, because they need a target per urgency that no firm has been asked for yet.
- **Blocked** is work that cannot move until someone acts: *on hold*, or *awaiting approval* (waiting for an owner). The reason is shown in words.
- Managers see both in the work order list (`attention=overdue` or `attention=blocked`, applied inside the manager's property scope, like every list), in a *Needs attention* panel on the organization home page, and as a reason under the status.
- An unanswered contractor question is not counted as blocked yet. That needs a rule for what counts as an answer.

**Who did what**

- Staff histories (the work order's history and a request's timeline) show each author's **role** beside their name, such as "Mo Manager (Manager)". A person holding several roles is shown with the most senior. Someone who has since left shows a name without a role.
- Residents and contractors do not see roles. Residents see "You" or "Property team"; contractors see "You", "Property team" or "System" ([decision 0020](0020-dispatch-and-contractor-access.md)).

## Consequences

- New work that changes a work order's status gets its notifications for free, because they are written in `change_status`. New features that send people messages should add an event function in `services/notifications.py` with an explicit audience and a table row above, rather than writing notifications ad hoc.
- Notifications are not retried. If an email fails, the in-app notification is still there.
- Notifications are never deleted or archived yet. A retention period belongs to production readiness.
