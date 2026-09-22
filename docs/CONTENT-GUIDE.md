# Content guide

All website content lives in `content/`. After editing, run `python src/build.py` and commit both your content change and the regenerated `web/` folder (the CI workflow checks that they match).

## Site-wide settings: `content/site.json`

- **Contact details** (`phone`, emails), **clinics** (addresses, hours, parking, transport, map links, photos, coordinates) and **social links**.
- **`indexable`**: keep `false` for previews. Set to `true` at launch to remove `noindex`, allow crawling in `robots.txt` and drop the preview banner.
- **`canonical_base`**: the production domain used in canonical URLs, Open Graph tags, the XML sitemap and structured data.
- **`external_forms`**: where enquiry, referral, booking, medical record, feedback and donation links point. At launch replace these with QEI's approved processors.
- **`nav`**, **`footer_columns`** and **`legal_links`**: the menus. Nested `children` become dropdowns.
- **`redirects`**: old URL to new URL pairs. Each creates a small redirect page so old links and search results keep working.

## Pages: `content/pages/**/*.md`

Markdown files with YAML front matter. The folder path is the URL (`content/pages/patient-info/forms.md` becomes `/patient-info/forms/`; `index.md` is the folder's own page). Useful front matter keys:

| Key | Purpose |
| --- | --- |
| `title`, `summary` | Heading and lead paragraph (also the meta description) |
| `template` | `page` (default), `hub` (card grid), `landing` (Dry Eye Clinic), `treatment`, `contact`, `home` |
| `section`, `parent` | Breadcrumb label and parent URL |
| `actions` | Buttons under the heading: `{label, url, style}` |
| `cards` | Cards for hub pages or under a page body: `{title, url, text, badge, cta, image, icon}` |
| `sidebar` | Sidebar cards: `book`, `dryeye`, `contact`, `referrer`, `donate`, `urgent`, `conditions`, `treatments`, `prepare` |
| `faq` | List of `{q, a}`; rendered as an accordion and as FAQPage structured data |
| `urgent` | Highlighted urgent notice (Markdown) |
| `hero_image`, `hero_alt` | Image path (relative to `site/` for mirror images, e.g. `wp-content/uploads/...`) |
| `keywords` | Extra words for site search |
| `raw_html` | `true` for imported HTML bodies (privacy policy, terms) |
| `reviewed_by`, `reviewed_on` | Named clinical reviewer and date, shown on the page |

Links inside Markdown should be site-absolute (`/patient-info/forms/`); the build converts them to relative links so the site works anywhere.

### QEI Laser

- Hub: `content/pages/qei-laser/index.md`; treatments hub `content/pages/qei-laser/treatments/index.md`; treatment pages in `content/pages/qei-laser/treatments/*.md` with `template: treatment` and `group: laser` (Dry Eye Clinic treatments use `group: dry-eye`). Patient information and health fund pages sit alongside the hub.
- The old qeilaser.com.au URL mapping lives in `domain_redirects` in `content/site.json`.
- Images for these pages are expected in `content/media/qei-laser/` (names listed in `src/fetch_qeilaser_images.py`). Until they are downloaded, the pages simply render without them.

### Dry Eye Clinic

- Landing page: `content/pages/dry-eye-clinic/index.md` (hero, proof points, stats, symptom list, "why" points, steps and FAQ are all front matter).
- Treatments: `content/pages/dry-eye-clinic/treatments/*.md` with `template: treatment`, `order`, `badge` and a `facts` table. They are listed automatically on the landing page, the treatments hub and each treatment's sidebar.

## Eye conditions: `content/conditions/*.md`

Front matter: `title`, `slug`, `summary`, `icon`, `doctors` (doctor slugs shown as "QEI specialists for..."), `keywords`, `at_a_glance` (bullet list), `urgent` (red-flag symptoms), `faq`, `reviewed_by`, `reviewed_on`, and optionally `cta: dry-eye-clinic`. The body uses `##` headings: what it is, symptoms, causes and risk factors, diagnosis, treatment at QEI, living with the condition.

## Ophthalmologists: `content/doctors/*.json`

`name`, `role` (subspecialty line), `qualifications`, `photo`, `summary`, `bio_html`, `treats` (list), `subspecialties` (tags: `cataract`, `cornea`, `retina`, `glaucoma`, `neuro-ophthalmology`, `oculoplastics`, `refractive`, `uveitis`, `genetic`), `notes_html` (referral notes) and `order`. News articles mentioning the doctor's surname appear on their profile automatically.

## News, patient stories and events

`content/news/*.json`, `content/stories/*.json`, `content/events/*.json`. Each has `slug`, `title`, `date` (ISO), `hero`, `excerpt`, `body_html` and, for news, `categories` (`QEI Clinic`, `QEI Foundation`, `Research`, `Education`, `Events`, `Patient Stories`). Body HTML is sanitised at build time: only text formatting, lists, links, images, tables and figures are kept, images are optimised and internal links are rewritten. Run `python src/import_mirror.py` to import new articles after the mirror refreshes; existing files are replaced for these three collections.

## People and researchers

`content/people/*.json` (`group`: `our-board`, `management` or `ambassadors`) and `content/researchers/*.json`. Research groups are in `content/research-groups/*.json`.

## Images

Reference images by their path inside the mirror (`wp-content/uploads/...`) or place new images in `content/media/` and reference them as `content/media/<file>`. The build resizes and compresses them into `web/media/` (JPEG for photos, WebP for images with transparency, SVG copied as-is). Provide meaningful `alt` text; decorative images use an empty `alt`.

## Checks before committing

```bash
python -m unittest discover -s tests
python src/build.py
python src/check_links.py --strict
```
