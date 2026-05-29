"""Unit tests for the pure logic in scripts/migrate_customers.py.
No network, no .env. Run: python tests/test_migrate_customers.py -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import migrate_customers as mc  # noqa: E402


class TestNormalizePhone(unittest.TestCase):
    def test_us_10_digit(self):
        self.assertEqual(mc.normalize_phone_local("212-555-0101"), "+12125550101")

    def test_formatted_with_plus(self):
        self.assertEqual(mc.normalize_phone_local("+1 (212) 555-0101"), "+12125550101")

    def test_uk(self):
        self.assertEqual(mc.normalize_phone_local("+44 20 7946 0958"), "+442079460958")

    def test_empty(self):
        self.assertEqual(mc.normalize_phone_local(""), "")
        self.assertEqual(mc.normalize_phone_local(None), "")

    def test_garbage_no_digits(self):
        self.assertEqual(mc.normalize_phone_local("call me"), "")


class TestInferServiceState(unittest.TestCase):
    def test_explicit_abbrev(self):
        self.assertEqual(mc.infer_service_state("", "TX"), "Texas")

    def test_explicit_full_name_wins(self):
        self.assertEqual(mc.infer_service_state("Miami", "New York"), "New York")

    def test_infer_from_area_city(self):
        self.assertEqual(mc.infer_service_state("Brooklyn", ""), "New York")

    def test_infer_from_bare_code_token(self):
        self.assertEqual(mc.infer_service_state("Austin, TX", ""), "Texas")

    def test_no_match_returns_empty(self):
        self.assertEqual(mc.infer_service_state("Springfield", ""), "")


if __name__ == "__main__":
    unittest.main()
