# 0024. Reports, metric definitions, and exports

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

A number in a report is only useful if everyone reads it the same way, and a report or file is a second route to the data that every screen protects. Two questions need written answers before any chart exists: what exactly each metric counts, and what the reader is allowed to see through it.

## Decision

**Who reads what**

| Reader | Report | Export |
| --- | --- | --- |
| Administrators | Everything in the organization | Work orders, requests, estimates |
| Managers | The same, for the properties they look after | The same, for those properties |
| Property owners | A summary of **approval activity** at their own properties (`/my-approvals/summary`) | Their estimates and the decisions on them (`/my-approvals/export.csv`) |
| Residents, contractors | Nothing (`403`) | Nothing |

- A property the reader may not see is reported as not found (`404`), as everywhere else. Totals never include properties outside the reader's scope: a manager's number is the number for their properties, not a share of a bigger one.
- An owner's summary leaves out spending, contractors and the rest of the staff report. Those describe how the firm runs, not what the owner decides.

**Periods and time zone**

- A period is whole **UTC calendar days**, both ends included. The default is the last 90 days; the longest is about ten years. A start after the end, or an unreadable date, is `422`.
- Dates are UTC because everything is stored in UTC and properties have no time zone yet. A report near midnight can therefore differ by a day from a property's local clock. Per-property time zones are deferred until a firm asks for them.
- Some figures describe **now** and ignore the period: open requests, work orders by status, overdue, blocked, and contractor workload. The rest describe **what happened in the period**.

**Definitions**

| Metric | Counts |
| --- | --- |
| Open requests | Submitted, in review, or in progress (now) |
| Waiting for triage | Submitted or in review, with no work order and not marked a duplicate (now). It matches the triage queue |
| Submitted in period | Requests created in the period |
| Work orders by status | Every work order, by its status now |
| Open work orders | Not completed, closed or cancelled |
| Overdue / Blocked | As in [0023](0023-notifications-and-attention.md) |
| Created in period | Work orders created in the period, by category and property |
| Time to resolve | For work verified in the period: the time from the **earliest linked request being submitted** to the **verification**. A work order with no request starts at its creation. Reopened work is measured to its latest verification. Reported as the average, the slowest, and the average by priority |
| Contractor workload | For each contractor, within scope: *active* jobs (current assignment, work not finished), *awaiting reply*, *overdue*, *finished* (verified in the period), *sent back* (a send-back during the period while they held the job), *declined* (declined in the period) |
| Repeat issue | Two or more work orders, created in the period and not cancelled, of the **same category at the same unit**, or in the **common areas** of the same property (no unit). Listed with the work order references |
| Repair spend | The **final cost** of work verified in the period. Estimates are not spend |
| Approvals | Estimates created in the period that were above the property's threshold: *waiting* (current and undecided), *approved*, *rejected*, *replaced* (a newer estimate arrived before anyone decided). Amounts are the estimated amounts. Average decision time runs from the estimate to the decision |

- **Resolution starts at the resident's report**, not at the work order, because the resident's wait is what the firm is judged on. The cost of that choice: work created in advance, such as inspections, has no request and starts at its creation.
- **Money is never added across currencies.** Every total is a list with one amount per currency, in whole cents.
- Contractor workload deliberately has no "score". It reports counts, and a send-back is not necessarily the contractor's fault.

**Exports**

- Format: **CSV** only, UTF-8 with a byte order mark so spreadsheet programs read accents correctly, one file per kind. A PDF or spreadsheet-native format can be added later without changing the rules below.
- An export holds the rows the reader could already open on screen, in the same scope, for the same period and optional property. It is built by the same filters as the report, not by a second set of rules.
- **Excluded by design:** residents' names, emails, phone numbers and access instructions; request and work order descriptions and scope; notes, histories, resolutions and attachments; contractors' quote text. Included: references, property, unit, category, priority, status, dates, assigned contractor's name, cost and currency, and who decided an estimate. The owner file also includes the decision reason, which that owner can already read.
- **Formula injection:** a cell that begins with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading apostrophe, so a title typed as a formula opens as text. Money is formatted from whole cents without floating point.
- A file is sent with `Content-Disposition: attachment`, `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
- An export is limited to **20,000 rows**. Beyond that, the reader is asked for a shorter period (`422`) rather than receiving a truncated file that looks complete.
- Every export is recorded as a `report.exported` activity event: who, which export, the period, and how many rows. Never the data itself.

## Consequences

- A new metric needs a row in the table above, a scope clause (`scope_clauses`) and a test against the seeded demonstration data. The report tests assert the demo's numbers, so a change to the seed shows up there.
- Reports are computed on request from the live tables. At the target size (around 300 units, several years of history) these are a handful of grouped queries; production readiness measures them. Pre-computed or cached reports are deferred until that measurement says otherwise.
- Exports are generated in memory, which the row limit keeps small. Streaming is unnecessary at that limit.
- Property time zones, response-time targets by urgency, repeat issues by contractor, and scheduled or emailed reports are deferred.
