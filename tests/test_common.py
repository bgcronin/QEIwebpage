from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import address_is_public, addresses_are_public, host_is_excluded, is_in_domain  # noqa: E402


class CommonTests(unittest.TestCase):
    def test_scope(self) -> None:
        self.assertTrue(is_in_domain("qei.org.au", "qei.org.au"))
        self.assertTrue(is_in_domain("www.qei.org.au", "qei.org.au"))
        self.assertFalse(is_in_domain("notqei.org.au", "qei.org.au"))

    def test_sensitive_host_exclusion(self) -> None:
        config = {"root_domain": "qei.org.au", "excluded_host_labels": ["mail", "admin"]}
        self.assertTrue(host_is_excluded("mail.qei.org.au", config)[0])
        self.assertTrue(host_is_excluded("portal.admin.qei.org.au", config)[0])
        self.assertFalse(host_is_excluded("www.qei.org.au", config)[0])

    def test_public_network_guard(self) -> None:
        self.assertTrue(address_is_public("1.1.1.1"))
        self.assertFalse(address_is_public("127.0.0.1"))
        self.assertFalse(address_is_public("10.0.0.7"))
        self.assertFalse(address_is_public("169.254.1.8"))
        self.assertFalse(address_is_public("192.0.2.1"))
        self.assertFalse(address_is_public("::1"))
        self.assertTrue(addresses_are_public(["1.1.1.1", "2606:4700:4700::1111"]))
        self.assertFalse(addresses_are_public(["1.1.1.1", "10.0.0.7"]))
        self.assertFalse(addresses_are_public([]))


if __name__ == "__main__":
    unittest.main()
