# Security and privacy

FieldWatch is a local research prototype, not a hardened multi-tenant service.

## FieldWatch runtime boundaries

- Bind to `127.0.0.1`; the app allowlists localhost hosts and rejects cross-origin POSTs. There is no authentication, multi-user isolation or permission model. Do not expose it publicly or bind it to a LAN interface without a separate security review.
- Only trusted two-band GeoTIFF bytes are accepted; VRTs, archives and arbitrary remote URLs are not supported. Limits: 24 MiB/file, 49 MiB/request, 2 million raster pixels, 100 zones, 200 vertices/polygon, 200 KB GeoJSON and two in-process analyses. Limits do not bound total native GDAL/OpenCV memory or execution time.
- Upload requests are limited before parsing, including streamed bodies. Duplicate/conflicting lengths and compressed requests are rejected. The body-read deadline is 30 seconds. Disconnect/cancellation releases request admission. The browser's stop-waiting button does not terminate a native analysis already running.
- No external inference, map tiles, fonts, analytics or cloud API calls occur during local analysis. The explicit dataset-download script uses public HTTPS with certificate verification. The application does not read `.env` or cloud credentials.
- GDAL/Rasterio is not sandboxed. GeoTIFF validation is not a guarantee against native decoder vulnerabilities or pathological computation. Use process isolation, CPU/memory/time limits and dependency auditing before accepting untrusted public uploads.
- No intentional server-side retention: multipart files can spool temporarily to disk and are closed after processing. Reports and previews remain in browser memory. Exported locations, dates, source digests and reviewer notes may be sensitive even without pixel payloads; protect downloaded files.
- CLI reports use exclusive creation and POSIX mode `0600`. Browser download permissions depend on the browser/OS. Review notes are unverified human content, distinct from algorithmic evidence; text is inserted with DOM text APIs rather than HTML.
- Restoring notes reads a user-selected JSON file locally in the browser (2 MiB maximum). It checks source/reference metadata, policies and zone details against the active result, accepts at most 100 unique known-zone annotations with bounded notes and allowed outcomes, and never replaces algorithmic findings. These are consistency checks, not cryptographic signatures or reviewer authentication; an edited export is still untrusted human input. Notes remain in page memory, not localStorage or a database. Export warnings reduce accidental loss but are not backups.
- Unexpected analysis errors return generic messages and log exception type only. CSP restricts scripts/styles to the app and images to local/data sources; frame embedding is denied. These controls are defense in depth, not a public-hosting certification.
- Evidence Lab accepts only allowlisted case IDs and no request body, arbitrary file path or remote URL. It shares analysis admission limits. Reference labels are read from explicit local dataset paths after inference, never used to select classifications or review decisions. Lab exports omit preview images but retain evaluation disclosures and reference digests. A synthetic rejection returns no usable report, and the UI clears the previous map and disables export.

## Keep private data out of Git

- Never commit API tokens, AWS credentials, private keys, `.env` files, real user uploads, or confidential exported reports.
- Use environment variables, an appropriate secrets manager, or your existing cloud credential provider when cloud integration is implemented. No API key is required by the current local application.
- Review `git diff --cached` and scan staged content and Git history with a secret scanner before publishing. `.gitignore` does not protect already-tracked files or secrets embedded in source code.
- The repository excludes local environments, common credential files, datasets, upload folders, caches, and generated artifacts. The Docker build context allowlists the application and runtime dependency file, with additional exclusions for common nested secrets.
- If a credential is accidentally committed, revoke or rotate it immediately. Removing it from the latest file does not remove it from Git history. Coordinate any history rewrite with collaborators.

## Before public deployment

Add HTTPS, authentication appropriate to the audience, proxy-level upload limits, rate limits, resource isolation, dependency auditing, and a reviewed retention/logging policy. Do not infer a verified AWS or COOL deployment from the configurable deployment label. The current code does not establish competition eligibility or production security.

Do not post credentials, private charts, or sensitive reproduction details in public issues. Share security reports with the repository owner through a private channel.
