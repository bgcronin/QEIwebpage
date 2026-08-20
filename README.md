# Queensland Eye Institute authorised static website mirror

This repository creates a faithful static snapshot of the publicly accessible Queensland Eye Institute website at `qei.org.au`, including public HTML subdomains discovered through passive Certificate Transparency records.

The project was commissioned as an authorised QEI reproduction. See `AUTHORIZATION.md` and `NOTICE.md`.

## What it does

1. Starts with `qei.org.au` and `www.qei.org.au`.
2. Passively discovers certificate-listed subdomains without brute-force scanning.
3. Excludes common mail, login, administration, API, staging, test, VPN, and internal hosts.
4. Verifies that candidates resolve and return public HTML.
5. Reads `robots.txt` and common WordPress sitemap locations.
6. Mirrors public pages, stylesheets, scripts, images, documents, and other page requisites with `wget` while respecting `robots.txt`.
7. Promotes the canonical site to `site/` and stores other public host snapshots under `site/_subdomains/<hostname>/`.
8. Disables all form submissions, non-GET browser requests, sensitive transaction links, analytics, and tracking pixels.
9. Adds `noindex`, audits the result, and saves a reviewable GitHub Actions artifact.
10. Optionally commits the generated snapshot back to the repository and can deploy a manually approved GitHub Pages preview.

## Important safety behaviour

The generated clone cannot submit patient enquiries, referrals, medical-record requests, clinical-trial registrations, newsletter subscriptions, donations, or payments. This is intentional. Those functions require a separately approved application architecture, privacy impact assessment, access controls, secure data storage, audit logging, spam controls, and QEI governance.

The preview also removes common analytics/tracking references and adds `noindex,nofollow`. Do not remove these safeguards until the target hostname, privacy policy, form processors, clinical governance, and deployment controls have been reviewed.

## Generate the clone in GitHub

Open **Actions → Build authorised QEI mirror → Run workflow**. Leave **Commit the generated static site** enabled to save the snapshot into `site/` and `reports/`.

The job also produces a downloadable Actions artifact containing the complete generated site and reports. The first run may create a large commit because it captures media and downloadable documents.

If the default branch is protected, run with committing disabled, review the artifact, and then publish from an approved branch or pull request.

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

The internet-facing discovery and mirror steps need normal outbound HTTPS and DNS access.

## Outputs

- `site/` — canonical static preview, plus `_subdomains/` for additional public hosts
- `reports/active-hosts.txt` — included public web hosts
- `reports/host-discovery.json` — discovery evidence and exclusions
- `reports/seed-urls.txt` — sitemap and root crawl seeds
- `reports/url-discovery.json` — sitemap results
- `reports/wget.log` — mirror log
- `reports/postprocess.json` — sanitisation totals
- `reports/AUDIT.md` and `reports/audit.json` — safety and link audit

## Scope notes

Separate domains such as `qeilaser.com.au`, `sbdh.com.au`, doctor websites, external appointment systems, payment providers, maps, social networks, and video platforms are not subdomains of `qei.org.au` and are not copied. Links to ordinary external resources remain external; sensitive transaction links are disabled in the static preview.

A static mirror reproduces public front-end output, not the original WordPress database, administrator interface, server configuration, private files, form mailers, CRM integrations, payment processing, analytics accounts, or other back-end systems.
