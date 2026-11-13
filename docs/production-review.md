# Production review: performance, accessibility, and responsive layout

- **Date:** 2026-11-13

## Performance at the upper target size

**Data set** (built by `backend/tests/volume.py`, used by `tests/test_volume.py`): 10 properties of 30 units (300 units), three years of history, 3,600 requests, about 2,500 work orders, 8 contractors, 4,000 notifications.

**Result:** every endpoint a person uses answered in **under 250 ms** on both SQLite and PostgreSQL 16, as the administrator, a manager, an owner, a contractor and a resident. That covers the request and work-order lists, the directory, the resident's own pages, a contractor's jobs, an owner's approvals, notifications, the staff report and each CSV export. The tests assert generous ceilings (3 seconds and 1 MB per response) so that only a serious regression fails them, and that the report and exports are complete.

**Findings**

| Finding | Decision |
| --- | --- |
| The request and work-order lists are **not paginated**. Their responses were about 105 to 141 KB at this size | **Deferred.** Fast enough at the target size; add paging when a firm exceeds it or a list passes about 1 MB. The report and exports are bounded already (repeat issues are capped at 50, exports at 20,000 rows) |
| The report runs several queries, none of them per-row | No action |
| Test suite on PostgreSQL takes about 2 seconds a test | CI runs a subset on each pull request and everything weekly |

## Accessibility (code-level review)

Not a browser or assistive-technology audit: it is a review of the code and of the tests that query the interface by role and name, which fail if a control has no accessible name.

| Check | Result |
| --- | --- |
| Landmarks | A single `main` landmark and a labelled `nav`. **Added:** a "Skip to main content" link that appears on keyboard focus |
| Language and zoom | `lang="en"`, and a viewport that does not disable zooming |
| Images | Every `img` has an `alt` (the file name) and loads lazily |
| Form controls | Every field is a label, or has `aria-label`; the shared field components tie label, hint and error together |
| Errors and status | Errors use `role="alert"`; confirmations and empty states on the people screens use `role="status"`. Loading messages on other screens are plain text and are not announced; acceptable for now |
| Tables | Real tables with captions and column headers. **Added:** the scrollable wrappers on the report can be reached by keyboard |
| Keyboard | No click handlers sit on non-interactive elements (searched), and no focus outline is removed |
| Colour | Text uses slate-500 or darker; contrast was not measured. Status is given in words, not by colour alone |
| Help | **Added:** a Help page with guidance per role |

**Not done, and worth doing with real users:** a screen-reader pass on the main flows (reporting a problem, approving an estimate), and a contrast check of the final theme.

## Responsive layout

Not a device-lab test. The layout uses mobile-first utility classes.

- **Fixed:** the main navigation did not wrap. With a manager's seven links plus Help it ran off a narrow screen. It now wraps, and the page padding is smaller on phones.
- Wide tables (requests, work orders, report tables, maintenance history) scroll inside their own container, so the page itself never scrolls sideways.
- The main content has less padding on phones.

**Not done:** a pass on real phones, especially the photo upload from a phone camera. It is the first thing to try in the pilot.
