# 0018. Attachments

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Residents attach photos of what is wrong, and staff attach quotes and documents. Uploaded files are the most common way for a web application to be attacked, and they are also private: a photo can show the inside of a home.

## Decision

- **Accepted files:** JPEG, PNG, WebP, and PDF only. The type is read from the file's own first bytes. What the browser claims, and the file name's extension, are ignored. SVG, HTML, and everything else are refused with `422`, because they can carry scripts.
- **Limits:** 10 MB per file (`WORKLEDGER_MAX_UPLOAD_MEGABYTES`) and 10 files per request. The size is checked from the declared length first and again while reading, so an oversized body is refused with `413` without being held in memory. Empty files are refused.
- **Upload format:** the file is the request body, with its name in the address (`?filename=`). This avoids adding a multipart library for one endpoint.
- **Storage:** behind a small interface (`save`, `read`) in `app/core/storage.py`. The local implementation writes into `WORKLEDGER_UPLOAD_DIR` (default `./uploads`, ignored by git). A hosted object store can replace it in production by implementing the same two methods. The uploads folder must be backed up together with the database.
- **Keys:** each file is stored under `organization/request/attachment`, all generated IDs. A person's file name is cleaned for display (folders and control characters removed) and is never used as a path.
- **Access:** files are served only through the API, after the same access checks as the request they belong to. There is no public file address. Each attachment is `resident` or `internal`. Resident uploads are visible to the resident and staff. Staff uploads are internal unless the manager shares them. A file the viewer may not see looks like a missing one (`404`).
- **Serving:** images are shown in the page, everything else is downloaded. Responses carry `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`.
- **Finished requests:** residents cannot add files to a closed or withdrawn request.

## Consequences

- iPhone HEIC photos are not accepted yet. Phones usually convert to JPEG when a browser file picker is used, and conversion on the server can be added later.
- Files are not scanned for malware. The accepted formats are limited and are never executed or rendered as HTML.
- A file saved just before a database failure can be left behind with no record. A cleanup task belongs with the other housekeeping in Phase 10.
- Deleting or replacing an attachment is not supported yet.
