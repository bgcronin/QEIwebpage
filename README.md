# Queensland Eye Institute authorised static website mirror

This repository builds a static snapshot of the publicly accessible Queensland Eye Institute website at `qei.org.au`, including public HTML subdomains found through passive Certificate Transparency records.

The project was commissioned as an authorised QEI reproduction. See `AUTHORIZATION.md` and `NOTICE.md`.

## What the workflow does

1. Starts with `qei.org.au` and `www.qei.org.au`.
2. Passively discovers certificate-listed subdomains without DNS brute forcing.
3. Excludes common mail, login, administration, API, staging, test, VPN, and internal host names.
4. Rejects hosts that resolve to private, loopback, link-local, reserved, or otherwise non-public addresses, as well as out-of-scope redirects, access-controlled pages, and apparent login portals.
5. Reads `robots.txt` and common WordPress sitemap locations.
6. Mirrors public pages, stylesheets, scripts, images, documents, and other page requisites with `wget`, respecting source robots rules, a 90 MiB per-file ceiling, and a total crawl quota. Oversized media remains linked to its source instead of breaking GitHub uploads.
7. Promotes the canonical site to `site/` and stores other public host snapshots beneath `site/_subdomains/<hostname>/`.
8. Disables every form and form control, browser POST/PUT/PATCH/DELETE requests, beacons, and direct links to external payment, donation, appointment, referral, or registration processors. Ordinary internal QEI information pages remain navigable.
9. Removes configured analytics and tracking references.
10. Adds page-level `noindex,nofollow` directives and overwrites `site/robots.txt` with a site-wide crawler block.
11. Runs a safety, link, and GitHub file-size audit before saving a reviewable Actions artifact or committing a refreshed snapshot.

## Important safety behaviour

The generated clone cannot submit patient enquiries, referrals, medical-record requests, clinical-trial registrations, newsletter subscriptions, donations, appointments, or payments. This is intentional. Those functions require separately approved infrastructure, privacy assessment, access controls, secure storage, audit logging, spam controls, and QEI governance.

Every mirrored form is changed to a non-submitting GET form, all controls are disabled and stripped of active field names, sensitive hidden/password/file values are cleared, JavaScript submission APIs and non-read requests are blocked, and a visible notice is inserted. The audit fails if any of those controls are incomplete.

The preview also removes configured tracking references and is blocked from search indexing through both HTML metadata and `robots.txt`. Do not weaken these safeguards until QEI has approved the target hostname, privacy policy, form processors, clinical governance, deployment controls, and production security architecture.

## Generate the current clone in GitHub

The repository initially contains the crawler, sanitizer, audit tooling, and a safe placeholder page. The first push to `main`, `master`, or `qei-static-clone` automatically runs **Build authorised QEI mirror** when crawler code or configuration changes.

You can also open **Actions → Build authorised QEI mirror → Run workflow**. Leave **Commit the generated static site** enabled to save the generated `site/` and `reports/` directories into the current branch.

The job also creates a downloadable Actions artifact containing the complete generated site and reports. The first run can produce a large commit because it captures public images and downloadable documents.

If the default branch is protected, run the workflow with committing disabled, review the artifact, and publish through an approved branch or pull request.

## Local commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/discover_hosts.py
python scripts/discover_urls.py
bash scripts/mirror.sh
python scripts/postprocess.py
python scripts/audit.py
python scripts/serve.py --port 8080
```

The internet-facing discovery and mirroring steps require outbound HTTPS and DNS access.

## Outputs

- `site/` — canonical static preview, plus `_subdomains/` for additional public hosts
- `reports/active-hosts.txt` — included public web hosts
- `reports/host-discovery.json` — discovery evidence, network checks, and exclusions
- `reports/seed-urls.txt` — sitemap and root crawl seeds
- `reports/url-discovery.json` — sitemap results
- `reports/wget.log` — mirror log
- `reports/postprocess.json` — sanitisation totals
- `reports/AUDIT.md` and `reports/audit.json` — safety, file-size, and link audit

## Scope notes

Separate domains such as `qeilaser.com.au`, `sbdh.com.au`, clinicians' individual domains, third-party appointment systems, payment providers, maps, social networks, and video platforms are not subdomains of `qei.org.au` and are not copied. Ordinary external links remain external; direct links that appear to initiate a sensitive transaction are disabled in the static preview.

A static mirror reproduces public front-end output. It does not reproduce the source WordPress database, administrator interface, server configuration, private files, form mailers, CRM integrations, payment processing, analytics accounts, search back end, or other server-side systems.
