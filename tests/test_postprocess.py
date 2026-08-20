from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from postprocess import process_html  # noqa: E402


class PostprocessTests(unittest.TestCase):
    def test_disables_forms_tracking_and_internal_links(self) -> None:
        config = {
            "root_domain": "qei.org.au",
            "canonical_host": "qei.org.au",
            "disable_tracking": True,
            "tracking_host_fragments": ["googletagmanager.com"],
            "disable_forms": True,
            "add_noindex": True,
        }
        source = """<!doctype html><html><head><script src='https://www.googletagmanager.com/gtm.js'></script></head>
        <body><form action='https://qei.org.au/send'><button>Send</button></form>
        <a href='https://qei.org.au/ophthalmologists/'>Doctors</a></body></html>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "index.html"
            page.write_text(source, encoding="utf-8")
            stats = process_html(page, root, config)
            output = page.read_text(encoding="utf-8")
            self.assertEqual(stats["forms_disabled"], 1)
            self.assertNotIn("googletagmanager.com", output)
            self.assertIn('data-qei-static-form="disabled"', output)
            self.assertIn('name="robots"', output)
            self.assertIn("ophthalmologists", output)


if __name__ == "__main__":
    unittest.main()
