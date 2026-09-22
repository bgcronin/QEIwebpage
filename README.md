# Queensland Eye Institute website

This repository contains two things:

1. **The redesigned QEI website** (`content/`, `src/`, `web/`): a fast, accessible, search-engine-ready static site built from editable content files. This is the site to review, refine and launch.
2. **The authorised static mirror of the current qei.org.au** (`site/`, `reports/`, `scripts/`): the crawler that produced it and its safety audit. The mirror is the source that the new site's content was imported from, and it is refreshed automatically each week. See [Mirror automation](#mirror-automation) below and `AUTHORIZATION.md`, `NOTICE.md`, `SECURITY.md`.

The project was commissioned as an authorised QEI reproduction and redesign.

## The redesigned website at a glance

- **Optometrist-led Dry Eye Clinic section**: landing page, eight treatment pages (Lumenis OptiLight IPL, Rexon-Eye QMR, Eye-light low level light therapy, BlephEx, meibomian gland expression, punctal plugs, Demodex treatment, prescription anti-inflammatory therapy), appointment guide and FAQ, promoted from the home page, main navigation, the dry eye condition page and the referrer pages. No referral needed, fast access.
- **QEI Laser section** (formerly qeilaser.com.au): hub, overview of treatments, eight treatment pages (irregular astigmatism, keratoconus Athens protocol, CAIRS, corneal scarring, post corneal transplant, recurrent erosion syndrome, corneal dystrophies, PRK/ASA), patient information and health fund rebates, with a redirect map for the old domain.
- **Patients**: booking, preparing for your visit, fees/Medicare/referrals, emergency eye care, rights and feedback, medical records, forms, clinic pages with parking and transport.
- **Clinical**: 11 ophthalmologist profiles with subspecialty tags, 12 plain-English eye condition guides (symptoms, causes, diagnosis, treatment, urgent signs, FAQ), a referrer hub with urgent-referral and subspecialty guides.
- **Institute**: about/history/governance, research (themes, five groups, 12 researcher profiles, publications, affiliates), clinical trials, education, the QEI Foundation (donate, bequests, workplace giving, people, reports), 133 news articles with categories, 20 patient stories and 9 events migrated from the current site.
- **Quality**: WCAG-oriented design with text-size, high-contrast and dark-theme controls; self-hosted fonts and no third-party trackers; structured data (MedicalOrganization, MedicalClinic, Physician, MedicalWebPage, FAQPage, NewsArticle, Event, BreadcrumbList, WebSite); XML sitemap; client-side site search; redirects from old URLs; print styles; 404 page; web manifest.

The preview build is deliberately **not indexable** (`"indexable": false` in `content/site.json`) so it cannot compete with the live qei.org.au in search results, and a banner tells visitors it is a preview. Forms that collect patient data (enquiries, referrals, medical record requests, donations, payments) link to the existing approved QEI services rather than being reimplemented here. See `docs/LAUNCH-CHECKLIST.md` for the steps to take the site live.

## Repository layout

```
content/            Editable content (JSON and Markdown with YAML front matter)
  site.json         Site-wide settings: contact details, clinics, navigation, footer, redirects, indexable flag
  pages/            Hand-written pages (Markdown). Folder structure mirrors the URL.
  conditions/       Eye condition guides (Markdown)
  doctors/          Ophthalmologist profiles (JSON)
  news/ stories/ events/ people/ researchers/ research-groups/   Imported collections (JSON)
src/
  build.py          Static site generator (Jinja2 templates, Markdown, Pillow media pipeline)
  import_mirror.py  Imports content from the mirror in site/ into content/
  check_links.py    Internal link, image and anchor checker for the built site
  templates/        Page templates
  assets/           Stylesheet, JavaScript, fonts and images
web/                The built website (committed; deployed to GitHub Pages)
tests/              Unit and full-build tests
docs/               Content guide and launch checklist
site/ reports/ scripts/ mirror.config.json   Authorised static mirror of qei.org.au and its tooling
```

## Build the website locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v   # tests (includes a full build)
python src/build.py                       # writes web/
python src/check_links.py --strict        # verifies every internal link, image and anchor
python -m http.server --directory web 8080
```

Open http://localhost:8080/. Links are relative, so the built site also works when opened from a folder or hosted under a sub-path.

`python src/import_mirror.py` re-imports news, patient stories and events from a refreshed mirror; hand-edited collections (doctors, people, researchers, research groups, conditions, policies) are only overwritten with `--force`.

## Editing content

See `docs/CONTENT-GUIDE.md` for how to add or change a doctor, condition, news article, treatment or page, and how the navigation, redirects and clinic details are configured.

## Deploying a preview

**Build and check QEI website** (`.github/workflows/build-site.yml`) runs the tests, builds the site and checks links on every push that touches `content/`, `src/`, `web/` or `tests/`, and fails if the committed `web/` is out of date.

**Deploy reviewed QEI website preview to GitHub Pages** (`.github/workflows/deploy-pages.yml`) is run manually from the Actions tab. It rebuilds `web/` (with the correct base path for the 404 page) and publishes it to GitHub Pages. Enable Pages with the "GitHub Actions" source in the repository settings first. GitHub Pages is suitable for a private review preview only when approved by QEI; production hosting should use QEI-controlled infrastructure (see `DEPLOYMENT.md`).

## Mirror automation

The mirror workflow (`.github/workflows/build-mirror.yml`) crawls the public qei.org.au, disables every form and transaction, removes tracking, adds `noindex`, audits the result and commits it to `site/` and `reports/`. It runs weekly and whenever crawler code changes. It never touches `content/`, `src/` or `web/`.

The generated mirror cannot submit patient enquiries, referrals, medical-record requests, clinical-trial registrations, newsletter subscriptions, donations, appointments or payments. Those functions require separately approved infrastructure, privacy assessment, access controls, secure storage, audit logging, spam controls and QEI governance. Do not weaken these safeguards until QEI has approved the target hostname, privacy policy, form processors, clinical governance, deployment controls and production security architecture.

Local mirror commands:

```bash
python scripts/discover_hosts.py
python scripts/discover_urls.py
bash scripts/mirror.sh
python scripts/postprocess.py
python scripts/audit.py
python scripts/serve.py --port 8080
```

Mirror outputs: `site/` (canonical static preview plus `_subdomains/`), `reports/active-hosts.txt`, `reports/host-discovery.json`, `reports/seed-urls.txt`, `reports/url-discovery.json`, `reports/wget.log`, `reports/postprocess.json`, `reports/AUDIT.md` and `reports/audit.json`.

Separate domains such as `qeilaser.com.au`, `sbdh.com.au`, clinicians' individual domains, third-party appointment systems, payment providers, maps, social networks and video platforms are not copied. A static mirror reproduces public front-end output only.
