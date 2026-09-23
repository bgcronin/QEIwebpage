"""Tests for the static site generator (src/build.py) and link checker."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import build  # noqa: E402


class HelperTests(unittest.TestCase):
    def test_rel_from_nested_page(self):
        build._current_url = "/eye-conditions/cataracts/"
        self.assertEqual(build.rel("/ophthalmologists/"), "../../ophthalmologists/")
        self.assertEqual(build.rel("/"), "../../")
        self.assertEqual(build.rel("https://example.org/x"), "https://example.org/x")
        self.assertEqual(build.rel("tel:+61732395000"), "tel:+61732395000")
        self.assertEqual(build.rel("#faq"), "#faq")

    def test_rel_from_root(self):
        build._current_url = "/"
        self.assertEqual(build.rel("/dry-eye-clinic/"), "./dry-eye-clinic/")
        self.assertEqual(build.rel("/assets/css/site.css"), "./assets/css/site.css")

    def test_slugify(self):
        self.assertEqual(build.slugify("Fuchs’ Endothelial Dystrophy"), "fuchs-endothelial-dystrophy")
        self.assertEqual(build.slugify("QEI Clinic"), "qei-clinic")

    def test_front_matter_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "page.md"
            p.write_text("---\ntitle: Test\nurl: /test/\nfaq:\n  - q: A?\n    a: B\n---\n\n## Heading\n\nBody text.\n", encoding="utf-8")
            meta, body = build.read_markdown(p)
        self.assertEqual(meta["title"], "Test")
        self.assertEqual(meta["faq"][0]["q"], "A?")
        self.assertTrue(body.startswith("## Heading"))

    def test_markdown_links_become_relative(self):
        build._current_url = "/patient-info/forms/"
        html = build.render_markdown("[Book](/patient-info/book-an-appointment/) and [live](https://qei.org.au/x/)")
        self.assertIn('href="../../patient-info/book-an-appointment/"', html)
        self.assertIn('href="https://qei.org.au/x/"', html)

    def test_fmt_date(self):
        self.assertEqual(build.Site.fmt_date("2026-08-20"), "20 August 2026")
        self.assertEqual(build.Site.fmt_date(""), "")

    def test_excerpt(self):
        text = build.Site.excerpt("<p>" + "word " * 100 + "</p>", 40)
        self.assertTrue(text.endswith("…"))
        self.assertLessEqual(len(text), 42)


class SiteModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.site = build.Site(Path(cls.tmp.name), verbose=False)
        cls.site.load()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_content_collections_loaded(self):
        self.assertGreaterEqual(len(self.site.doctors), 11)
        self.assertEqual(len(self.site.conditions), 12)
        self.assertGreater(len(self.site.news), 100)
        self.assertGreaterEqual(len(self.site.treatments), 8)
        self.assertTrue(all(d["photo"] for d in self.site.doctors), "every doctor needs a photo")

    def test_old_urls_map_to_new_site(self):
        s = self.site
        self.assertEqual(s.old_to_new_url("../../ophthalmologists/dr-brendan-cronin/index.html"), "/ophthalmologists/dr-brendan-cronin/")
        self.assertEqual(s.old_to_new_url("https://qei.org.au/patient-info/send-enquiry/"), "/patient-info/book-an-appointment/")
        self.assertEqual(s.old_to_new_url("../../eye-conditions/diabetic-ratinopathy/index.html"), "/eye-conditions/diabetic-retinopathy/")
        self.assertEqual(s.old_to_new_url("../../wp-content/uploads/2020/01/x.pdf"), "https://qei.org.au/wp-content/uploads/2020/01/x.pdf")
        self.assertTrue(s.old_to_new_url("../../no-such-page/index.html").startswith("https://qei.org.au/"))
        self.assertEqual(s.old_to_new_url("https://example.org/"), "https://example.org/")

    def test_clean_html_sanitises_and_rewrites(self):
        build._current_url = "/news/example/"
        out = self.site.clean_html('<p><span style="font-weight:400">Hi</span> <a href="../../ophthalmologists/dr-david-gunn/index.html" onclick="x()">Dr Gunn</a><script>alert(1)</script></p>')
        self.assertNotIn("<script", out)
        self.assertNotIn("onclick", out)
        self.assertNotIn("<span", out)
        self.assertIn('href="../../ophthalmologists/dr-david-gunn/"', out)

    def test_every_condition_has_doctors_and_urgent_guidance(self):
        for c in self.site.conditions:
            self.assertTrue(c.get("doctors"), c["slug"])
            self.assertTrue(c.get("urgent"), c["slug"])
            self.assertTrue(c.get("summary"), c["slug"])

    def test_dry_eye_clinic_is_in_primary_navigation(self):
        labels = [item["label"] for item in self.site.config["nav"]]
        self.assertEqual(labels[0], "Dry Eye Clinic")

    def test_treatment_groups(self):
        groups = {t.get("group") for t in self.site.treatments}
        self.assertEqual(groups, {"dry-eye", "therapeutic", "refractive"})
        self.assertGreaterEqual(len([t for t in self.site.treatments if t["group"] == "therapeutic"]), 7)
        refractive = [t for t in self.site.treatments if t["group"] == "refractive"]
        self.assertEqual([t["short_title"] for t in refractive],
                         ["LASIK", "TransPRK", "PRK", "CLEAR lenticule extraction", "EVO ICL", "Refractive lens exchange"])
        for t in refractive:
            self.assertTrue(t.get("procedure"), t["url"])
            self.assertTrue(t.get("facts"), t["url"])
            self.assertTrue(t.get("faq"), t["url"])

    def test_qeilaser_redirect_map_targets_exist(self):
        mapping = self.site.config["domain_redirects"]["qeilaser.com.au"]
        for old, new in mapping.items():
            self.assertIn(new, self.site.known_urls, f"{old} -> {new}")


class FullBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.site = build.Site(cls.out, verbose=False)
        cls.site.build(clean=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_key_pages_exist(self):
        for url in ["/", "/dry-eye-clinic/", "/dry-eye-clinic/treatments/ipl-optilight/", "/ophthalmologists/dr-brendan-cronin/",
                    "/eye-conditions/dry-eye/", "/patient-info/book-an-appointment/", "/referrers/", "/news/", "/search/", "/sitemap/",
                    "/qei-laser/", "/qei-laser/therapeutic/", "/qei-laser/therapeutic/cairs-eye-surgery/", "/qei-laser/therapeutic/health-fund-rebates/",
                    "/qei-laser/refractive/", "/qei-laser/refractive/lasik/", "/qei-laser/refractive/clear-lenticule-extraction/", "/qei-laser/refractive/icl/",
                    "/qei-laser/refractive/refractive-lens-exchange/", "/qei-laser/refractive/am-i-suitable/", "/qei-laser/refractive/compare-procedures/",
                    "/qei-laser/refractive/costs-and-payment/", "/qei-laser/refractive/your-journey/", "/qei-laser/refractive/faq/",
                    "/qei-clinics/woolloongabba-qei-clinic/", "/our-vision/"]:
            self.assertTrue((self.out / url.lstrip("/") / "index.html").exists(), url)
        self.assertTrue((self.out / "404.html").exists())
        self.assertTrue((self.out / "sitemap.xml").exists())
        self.assertTrue((self.out / "robots.txt").exists())
        self.assertTrue((self.out / "search-index.json").exists())

    def test_preview_is_not_indexable(self):
        home = (self.out / "index.html").read_text(encoding="utf-8")
        if self.site.config.get("indexable"):
            self.assertIn('content="index,follow', home)
            self.assertIn("Allow: /", (self.out / "robots.txt").read_text())
        else:
            self.assertIn('content="noindex,nofollow"', home)
            self.assertIn("Disallow: /", (self.out / "robots.txt").read_text())

    def test_no_root_absolute_links_in_pages(self):
        for page in list(self.out.rglob("index.html"))[:200]:
            html = page.read_text(encoding="utf-8")
            self.assertNotIn('href="/', html, page)
            self.assertNotIn('src="/', html, page)

    def test_structured_data_present(self):
        doc = (self.out / "ophthalmologists/dr-brendan-cronin/index.html").read_text(encoding="utf-8")
        self.assertIn('"@type": "Physician"', doc)
        cond = (self.out / "eye-conditions/cataracts/index.html").read_text(encoding="utf-8")
        self.assertIn('"@type": "FAQPage"', cond)
        self.assertIn('"@type": "MedicalWebPage"', cond)
        home = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('"@type": "MedicalOrganization"', home)

    def test_laser_treatment_pages_use_laser_sidebar_not_dry_eye(self):
        html = (self.out / "qei-laser/therapeutic/cairs-eye-surgery/index.html").read_text(encoding="utf-8")
        self.assertIn("Other QEI Laser Therapeutic treatments", html)
        self.assertNotIn("Other Dry Eye Clinic treatments", html)
        self.assertNotIn("Other vision correction options", html)
        lasik = (self.out / "qei-laser/refractive/lasik/index.html").read_text(encoding="utf-8")
        self.assertIn("Other vision correction options", lasik)
        self.assertIn("Book a laser vision assessment", lasik)
        self.assertNotIn("CAIRS eye surgery</a></h3>", lasik)
        self.assertIn('"@type": "MedicalProcedure"', lasik)
        self.assertIn('"howPerformed"', lasik)
        self.assertIn('"@type": "FAQPage"', lasik)

    def test_no_prices_or_external_refractive_brand_on_laser_pages(self):
        """Practice decision (September 2026): no procedure prices on the site and nothing reused from the surgeons' separate refractive practice."""
        import re
        for page in (self.out / "qei-laser").rglob("index.html"):
            html = page.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\$\s?\d[\d,.]*\d", html), page)  # "$2" in the donation footer is fine; "$4,250" is not
            self.assertNotIn("interest-free", html.lower(), page)
            self.assertNotIn("Guide price", html, page)
        for page in list((self.out / "qei-laser").rglob("index.html")) + list((self.out / "ophthalmologists").rglob("index.html")) + [self.out / "index.html"]:
            html = page.read_text(encoding="utf-8")
            self.assertNotIn("Focus Vision", html, page)
            self.assertNotIn("focusvision", html, page)
            self.assertNotIn("Ray Tracing", html, page)

    def test_old_laser_urls_redirect_to_new_sections(self):
        stub = (self.out / "qei-laser/treatments/cairs-eye-surgery/index.html").read_text(encoding="utf-8")
        self.assertIn("qei-laser/therapeutic/cairs-eye-surgery/", stub)
        stub = (self.out / "qei-laser/treatments/prk-asa-laser-vision-correction/index.html").read_text(encoding="utf-8")
        self.assertIn("qei-laser/refractive/prk/", stub)

    def test_laser_sections_are_in_navigation_and_footer(self):
        home = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("qei-laser/refractive/", home)
        self.assertIn("qei-laser/therapeutic/", home)
        labels = [item["label"] for item in self.site.config["nav"]]
        self.assertIn("Laser eye surgery", labels)
        dry = (self.out / "dry-eye-clinic/treatments/blephex/index.html").read_text(encoding="utf-8")
        self.assertIn("Other Dry Eye Clinic treatments", dry)
        self.assertNotIn("CAIRS", dry)

    def test_search_index_is_valid_json(self):
        data = json.loads((self.out / "search-index.json").read_text(encoding="utf-8"))
        self.assertGreater(len(data), 200)
        self.assertTrue(all({"t", "u", "s"} <= set(d) for d in data))

    def test_link_checker_passes(self):
        result = subprocess.run([sys.executable, str(ROOT / "src" / "check_links.py"), "--site", str(self.out), "--strict"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
