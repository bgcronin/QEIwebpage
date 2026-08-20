from __future__ import annotations

import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import host_is_excluded, is_in_domain  # noqa: E402


class CommonTests(unittest.TestCase):
    def test_scope(self) -> None:
        self.assertTrue(is_in_domain("qei.org.au", "qei.org.au"))
        self.assertTrue(is_in_domain("www.qei.org.au", "qei.org.au"))
        self.assertFalse(is_in_domain("notqei.org.au", "qei.org.au"))

    def test_sensitive_host_exclusion(self) -> None:
        config = {"root_domain": "qei.org.au", "excluded_host_labels": ["mail", "admin"]}
        self.assertTrue(host_is_excluded("mail.qei.org.au", config)[0])
        self.assertFalse(host_is_excluded("www.qei.org.au", config)[0])


if __name__ == "__main__":
    unittest.main()
