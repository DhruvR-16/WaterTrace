# Security and privacy

ChartCourt is a local hackathon MVP, not a hardened multi-tenant service.

## Keep private data out of Git

- Never commit API tokens, AWS credentials, private keys, `.env` files, real user uploads, or confidential exported reports.
- Use environment variables, an appropriate secrets manager, or your existing cloud credential provider when cloud integration is implemented. No API key is required by the current local application.
- Review `git diff --cached` and scan staged content and Git history with a secret scanner before publishing. `.gitignore` does not protect already-tracked files or secrets embedded in source code.
- The repository excludes local environments, common credential files, datasets, upload folders, caches, and generated artifacts. The Docker build context allowlists the application and runtime dependency file, with additional exclusions for common nested secrets.
- If a credential is accidentally committed, revoke or rotate it immediately. Removing it from the latest file does not remove it from Git history. Coordinate any history rewrite with collaborators.

## Runtime boundaries

- Run the development service on `127.0.0.1`. The README's container example binds the published port to loopback as well.
- PNG, JPEG, and WebP inputs are decoded and inspected; file extensions alone are not trusted. The analysis endpoint rejects uploads above 8 MB, images above 20 megapixels, and undersized images.
- OCR calls have time limits, and each server process admits at most two concurrent inspections. These controls are not a replacement for network-level rate limits or request-body limits: multipart parsing happens before the route-level size check.
- The application does not intentionally persist uploads. The multipart framework may temporarily spool larger uploads to disk, and the browser retains the current preview and result until the page is closed or replaced. Browser downloads contain the selected report or reconstruction.
- Chart images are not submitted to an external model. The stylesheet requests Google Fonts; system-font fallbacks work without it.
- Exported reports include the uploaded filename, image digest, OCR text, recovered values, and measurements. Treat reports as potentially sensitive even though they omit the original image payload.

## Before public deployment

Add HTTPS, authentication appropriate to the audience, proxy-level upload limits, rate limits, resource isolation, dependency auditing, and a reviewed retention/logging policy. Do not infer a verified AWS or COOL deployment from the configurable deployment label. The current code does not establish competition eligibility or production security.

Do not post credentials, private charts, or sensitive reproduction details in public issues. Share security reports with the repository owner through a private channel.
