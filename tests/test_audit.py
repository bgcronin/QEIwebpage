from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit import candidate_paths, form_safety_issues  # noqa: E402
from postprocess import disable_form  # noqa: E402


class AuditTests(unittest.TestCase):
    def test_unsafe_form_is_detected(self) -> None:
        soup = BeautifulSoup(
            "<form action='/submit' method='post'><input name='patient'><button type='submit'>Send</button></form>",
            "lxml",
        )
        issues = form_safety_issues(soup.find("form"))
        self.assertIn("action is not #", issues)
        self.assertIn("method is not GET", issues)
        self.assertTrue(any("is enabled" in issue for issue in issues))
        self.assertTrue(any("retains a name" in issue for issue in issues))

    def test_disabled_form_passes_safety_check(self) -> None:
        soup = BeautifulSoup(
            "<form action='/submit' method='post'><input name='patient'><button type='submit'>Send</button></form>",
            "lxml",
        )
        form = soup.find("form")
        disable_form(form, soup)
        self.assertEqual(form_safety_issues(form), [])

    def test_link_candidates_cannot_escape_site_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory).resolve()
            page_dir = site / "section"
            page_dir.mkdir()
            target = site / "about" / "index.html"
            target.parent.mkdir()
            target.write_text("ok", encoding="utf-8")
            self.assertTrue(any(path.exists() for path in candidate_paths(page_dir, site, "../about/")))
            self.assertEqual(candidate_paths(page_dir, site, "../../../etc/passwd"), [])


if __name__ == "__main__":
    unittest.main()
