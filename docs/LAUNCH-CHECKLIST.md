# Launch checklist for the redesigned website

The redesigned site in `web/` is a review build. Complete these steps before it replaces qei.org.au.

## Content sign-off

- [ ] Assign a named ophthalmologist or optometrist reviewer to each eye condition page and each Dry Eye Clinic page; record them in `reviewed_by` / `reviewed_on` so the review appears on the page and in structured data.
- [ ] Confirm the Dry Eye Clinic details: which clinic(s) it operates from, opening days, the optometrists' names and photos (add them to the landing page), consultation and treatment fees, and the exact device names (Lumenis OptiLight, Rexon-Eye QMR, Eye-light LLLT mask, BlephEx).
- [ ] Supply photographs of the Dry Eye Clinic and its equipment to replace the interim clinic photos.
- [ ] Verify every doctor profile, subspecialty tag and "conditions and procedures" list with the doctor concerned.
- [ ] Verify clinic addresses, hours, parking and transport text, and the postal address.
- [ ] Review imported news, patient stories and events; retire anything out of date. Set `hero_alt` text for imported images.
- [ ] Check the affiliate logos on `/research/affiliates/` and replace generic alt text with organisation names.
- [ ] Confirm consent for all photographs of patients, staff and supporters.

## qeilaser.com.au

- [ ] The QEI Laser pages (`content/pages/qei-laser/`) were reconciled with the Squarespace export on 22 September 2026. Photos could not be downloaded from this environment: run the **Fetch QEI Laser images** workflow from the Actions tab (or `python src/fetch_qeilaser_images.py` locally) to download them from the Squarespace CDN into `content/media/qei-laser/`; the pages pick them up automatically on the next build.
- [ ] The Squarespace privacy policy, terms and medical disclaimer were not migrated; the main site's own policies and the new `/medical-disclaimer/` page apply.
- [ ] Confirm the surgeons, procedures and health fund statements (including the Medicare item number quoted on the rebates page) with Dr Cronin and Dr Gunn.
- [ ] At launch, redirect every qeilaser.com.au page to its new home. The mapping is in `domain_redirects` in `content/site.json`. Options: keep the Squarespace subscription temporarily and add 301 URL mappings to the new URLs, or point the domain at the new host and configure the redirects there. Update Google Business Profile, Search Console (change of address) and any printed material that lists qeilaser.com.au.
- [ ] Note that the Squarespace site lists the former South Brisbane address; the new pages use 87 Ipswich Road, Woolloongabba.

## QEI Laser Refractive (laser vision correction)

- [ ] The refractive pages were written on 23 September 2026 from published sources (manufacturer labelling, peer-reviewed studies and Australian pricing and coverage information). Every clinical statement, figure and criterion must be reviewed by the laser surgeons before launch and the `reviewed_by` and `reviewed_on` fields completed. Specific items to confirm: the treatable ranges quoted for each procedure; the residual-bed and percentage-tissue-altered thresholds; the ICL age range (labelled 21 to 45 in Australia; the United States labelling was extended to 21 to 60 in 2026) and the statement that older patients are considered individually; the complication rates quoted; the claim that our surgeons were the first in Queensland to offer Ray Tracing LASIK; the statement that the Ziemer Z8 is the lowest-energy femtosecond laser available; and the lens brands referred to on the lens exchange page.
- [ ] Guide prices (TransPRK and PRK from $3,500; LASIK and CLEAR from $4,250; ICL from $7,000; lens exchange from $6,000 per eye; assessment fee credited; enhancement within 12 months included; medicines excluded; interest-free plans over up to 24 months) were taken from the surgeons' current published refractive pricing. Confirm they apply to QEI Laser Refractive, confirm the finance provider and any establishment fee, and decide whether the assessment fee should be stated.
- [ ] Decide how QEI Laser Refractive relates to the surgeons' existing refractive brand (the doctor profiles mention it) and whether that name, its website and its Google Business Profile should redirect to, or be cross-linked with, these pages.
- [ ] Confirm the health fund statement (some extras policies contribute a fixed amount after a waiting period; hospital cover does not apply) and the tax and superannuation wording with the practice manager.
- [ ] Add photographs of the excimer laser, the Z8, the ICL and the lens implants when available; the pages currently reuse existing clinic and theatre photographs.

## Forms, transactions and integrations

- [ ] Replace the `external_forms` links in `content/site.json` with approved, privacy-assessed processors for enquiries, referrals, online booking, medical record requests (with payment), feedback, donations and event registration.
- [ ] Decide whether to embed the online booking widget and any maps; both load third-party scripts and require a cookie/consent decision.
- [ ] Newsletter and optometry education mailing-list sign-ups.

## Search engines and analytics

- [ ] Set `"indexable": true` and `canonical_base` to the production domain in `content/site.json`, then rebuild. This removes the preview banner and `noindex`, and enables crawling in `robots.txt`.
- [ ] Publish 301 redirects on the web server for the old URLs listed in `redirects` (the meta-refresh pages are a fallback for hosts that cannot redirect) and for `/eye-conditions/diabetic-ratinopathy/`.
- [ ] Submit `sitemap.xml` in Google Search Console; verify the site (a verification meta tag can be added to `src/templates/base.html`).
- [ ] Add privacy-respecting analytics with consent management if required by QEI's privacy policy; none is included in the build.
- [ ] Review Open Graph images (`src/assets/img/og-default.jpg` and page hero images).

## Hosting and security

- [ ] Host on QEI-controlled infrastructure with HTTPS, HSTS and the security headers in `web/_headers` (Content-Security-Policy should be added once the final set of third-party embeds is known; the only inline script is the small display-preference loader in the page head).
- [ ] Configure the custom domain (add a `CNAME` file if using GitHub Pages).
- [ ] Set caching for `assets/` and `media/`; set up uptime monitoring, backups and a rollback plan.

## Accessibility and testing

- [ ] Test with screen readers (NVDA, VoiceOver), keyboard only, 200 to 400 per cent zoom, high contrast and dark themes, and on representative phones and tablets.
- [ ] Check all PDFs linked from the site for accessibility or provide accessible alternatives.
- [ ] Run Lighthouse or equivalent for performance and best practices.

## Governance

- [ ] Nominate a content owner and a review cycle (for example, clinical pages every 12 months).
- [ ] Record the launch date and the version of the content in the annual report or governance records.
