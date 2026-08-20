from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from postprocess import link_is_external_transaction, process_html  # noqa: E402


class PostprocessTests(unittest.TestCase):
    def config(self) -> dict:
        return {
            "root_domain": "qei.org.au",
            "canonical_host": "qei.org.au",
            "disable_tracking": True,
            "tracking_host_fragments": ["googletagmanager.com"],
            "disable_forms": True,
            "add_noindex": True,
            "disable_external_transactions": True,
            "transaction_words": ["donate", "registration", "book appointment"],
            "transaction_host_fragments": ["payments.example"],
        }

    def test_disables_forms_tracking_and_external_transactions(self) -> None:
        source = """<!doctype html><html><head>
        <script src='https://www.googletagmanager.com/gtm.js'></script>
        <script>window.dataLayer=[]; gtag('config','TEST');</script>
        </head><body>
        <form action='https://qei.org.au/send' method='post'>
          <input type='hidden' name='token' value='secret'>
          <input type='text' name='patient_name'>
          <input type='password' name='password' value='secret'>
          <input type='file' name='attachment'>
          <button type='submit' name='send' formaction='https://qei.org.au/submit'>Send</button>
        </form>
        <a id='internal-donate' href='https://qei.org.au/qei-foundation/donate/'>Donate</a>
        <a id='external-donate' href='https://payments.example/donate'>Donate now</a>
        <a id='ordinary-external' href='https://www.youtube.com/watch?v=1'>Watch video</a>
        <a href='https://qei.org.au/ophthalmologists/'>Doctors</a>
        </body></html>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "index.html"
            page.write_text(source, encoding="utf-8")

            stats = process_html(page, root, self.config())
            output = page.read_text(encoding="utf-8")
            soup = BeautifulSoup(output, "lxml")

            self.assertEqual(stats["forms_disabled"], 1)
            self.assertEqual(stats["form_controls_disabled"], 5)
            self.assertEqual(stats["transactions_disabled"], 1)
            self.assertEqual(stats["tracking_nodes_removed"], 2)
            self.assertNotIn("googletagmanager.com", output)
            self.assertNotIn("gtag('config'", output)

            form = soup.find("form")
            self.assertIsNotNone(form)
            self.assertEqual(form.get("action"), "#")
            self.assertEqual(form.get("method"), "get")
            self.assertEqual(form.get("data-qei-static-form"), "disabled")
            self.assertEqual(form.get("data-original-action"), "https://qei.org.au/send")
            for control in form.find_all(["input", "textarea", "select", "button"]):
                self.assertTrue(control.has_attr("disabled"))
                self.assertFalse(control.has_attr("name"))
                self.assertFalse(control.has_attr("formaction"))
            sensitive_inputs = form.find_all("input", attrs={"type": ["hidden", "password", "file"]})
            self.assertTrue(all(control.get("value", "") == "" for control in sensitive_inputs))
            self.assertEqual(form.find("button").get("type"), "button")

            internal = soup.find("a", id="internal-donate")
            self.assertNotEqual(internal.get("href"), "#")
            self.assertIn("qei-foundation/donate", internal.get("href"))
            external = soup.find("a", id="external-donate")
            self.assertEqual(external.get("href"), "#")
            self.assertEqual(external.get("data-qei-disabled-transaction"), "true")
            self.assertEqual(external.get("data-original-href"), "https://payments.example/donate")
            self.assertEqual(soup.find("a", id="ordinary-external").get("href"), "https://www.youtube.com/watch?v=1")

            self.assertIsNotNone(soup.find("script", id="qei-static-mirror-safety"))
            self.assertIsNotNone(soup.find("style", id="qei-static-mirror-safety-style"))
            self.assertIsNotNone(soup.find(class_="qei-static-form-notice"))
            self.assertIn('name="robots"', output)
            self.assertIn("ophthalmologists", output)

    def test_processing_is_idempotent(self) -> None:
        source = """<!doctype html><html><body>
        <form action='/send' method='post'><input name='email'><button type='submit'>Send</button></form>
        </body></html>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "index.html"
            page.write_text(source, encoding="utf-8")
            process_html(page, root, self.config())
            process_html(page, root, self.config())
            soup = BeautifulSoup(page.read_text(encoding="utf-8"), "lxml")
            self.assertEqual(len(soup.find_all(class_="qei-static-form-notice")), 1)
            self.assertEqual(len(soup.find_all("script", id="qei-static-mirror-safety")), 1)
            self.assertEqual(len(soup.find_all("style", id="qei-static-mirror-safety-style")), 1)
            self.assertEqual(soup.find("form").get("data-original-action"), "/send")

    def test_transaction_classification_preserves_internal_pages(self) -> None:
        config = self.config()
        self.assertFalse(
            link_is_external_transaction("https://qei.org.au/qei-foundation/donate/", "Donate", config)
        )
        self.assertTrue(link_is_external_transaction("https://payments.example/start", "Donate now", config))
        self.assertFalse(link_is_external_transaction("https://example.com/article", "Read more", config))


if __name__ == "__main__":
    unittest.main()
