# 0017. Maintenance requests and what residents can see

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

A request is the first thing a resident creates, and the first record that mixes information for residents with information only staff should have. Phase 3 has to establish the separation between the two, because every later phase (work orders, estimates, approvals) adds more internal material to the same pages.

## Decision

- **A request is a report, not a commitment** to do work. It records the unit, the resident it is about, a category, an urgency, a short summary, a description, an optional location in the home, and optional access notes.
- **Fixed lists, for now.** Categories (plumbing, electrical, heating or cooling, appliances, doors or windows, pests, structure, other) and urgencies (routine, soon, urgent, emergency) are built in. They can become per-organization settings later without changing stored data, because they are stored as plain text.
- **Statuses a resident sees:** *received* (stored as `submitted`), *in review*, *in progress*, *resolved*, *closed*, and *withdrawn* (`cancelled`). Staff may move a request between the open statuses in any order, but never back to *received*. *Closed* and *withdrawn* are final.
- **Withdrawing:** a resident may withdraw a request that is *received* or *in review*. After work has started they message the team instead.
- **Reference numbers** look like `REQ-0042`. They are numbered per organization from 1, handed out by a counter row that is locked until the transaction ends, so two requests submitted at once never share a number.
- **Timeline:** each request has a list of entries (submitted, status changed, message, internal note). Every entry stores whether it is visible to the resident or internal. A status change is always visible, because the resident is following it. The note that goes with it is internal unless the manager chooses to share it. Notes default to internal.
- **Separate response shapes.** Residents receive models that have no field for internal entries, staff identities, or other people's details. Staff authors appear as "Property team". The resident queries never load internal rows at all, so a leak would need two mistakes. Tests list the exact fields a resident response may contain.
- **Who can do what:**
  - Residents use `/my-requests`: list, read, submit for one of their current homes, message, withdraw, attach files. They see requests about their own directory record, including from homes they have since left (decision 0016). They cannot report a problem for a home they have left.
  - Administrators and managers use `/requests`, limited to their properties (decision 0008): list with filters, read with the resident's contact details, add internal notes or messages, change status, attach files, and enter a request for a resident, for example after a phone call. A request entered this way is marked as such.
  - Contractors and property owners have no access yet.
- **Activity:** submitting, status changes, and attachments are recorded. The wording of the report is not copied into the shared activity history.

## Consequences

- A screen to enter a request for a resident exists in the API only. The administration screens can add it when the need is clear.
- Triage, duplicate handling, and work orders (Phase 4) will add to the timeline and statuses without changing the visibility rule.
- A resident who is not linked to a directory record cannot report a problem. They are told to contact their property manager.
- No emails are sent yet. The confirmation is the reference shown on screen. Notifications arrive in a later phase.
