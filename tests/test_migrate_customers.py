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


class TestBuildWriteFields(unittest.TestCase):
    def test_resolves_phone_and_state(self):
        row = {
            "legacy_customer_id": "L1", "customer_name": "Sunrise Diner",
            "caller_phone_raw": "212-555-0101", "area": "Brooklyn",
            "service_state": "", "first_contact_date": "2023-04-01",
            "last_known_equipment": "Combi Oven",
        }
        w = mc.build_write_fields(row, source_system="legacy", batch_id="b1")
        self.assertEqual(w["normalized_phone"], "+12125550101")
        self.assertEqual(w["service_state"], "New York")
        self.assertEqual(w["customer_name"], "Sunrise Diner")
        self.assertEqual(w["city_area"], "Brooklyn")
        self.assertEqual(w["legacy_customer_id"], "L1")
        self.assertEqual(w["source_system"], "legacy")
        self.assertEqual(w["import_batch_id"], "b1")
        self.assertEqual(w["first_seen"], "2023-04-01")
        self.assertEqual(w["last_known_equipment"], "Combi Oven")


class TestValuesConflict(unittest.TestCase):
    def test_both_empty_no_conflict(self):
        self.assertFalse(mc.values_conflict("", ""))

    def test_fill_blank_is_not_conflict(self):
        self.assertFalse(mc.values_conflict("Miami", ""))
        self.assertFalse(mc.values_conflict("", "Miami"))

    def test_case_insensitive_equal_no_conflict(self):
        self.assertFalse(mc.values_conflict(" miami ", "Miami"))

    def test_differ_is_conflict(self):
        self.assertTrue(mc.values_conflict("Miami", "Orlando"))


class TestDetectFieldConflicts(unittest.TestCase):
    def test_name_conflict_surfaces(self):
        w = {"customer_name": "Joe Pizza", "city_area": "Miami",
             "service_state": "Florida", "last_known_equipment": "", "first_seen": ""}
        existing = {"customer_name": "Joes Pizzeria", "city_area": "Miami",
                    "service_state": "Florida", "last_known_equipment": "", "first_seen": ""}
        conflicts = mc.detect_field_conflicts(w, existing)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["field"], "customer_name")

    def test_no_conflict_when_existing_blank(self):
        w = {"customer_name": "Joe Pizza", "city_area": "Miami",
             "service_state": "Florida", "last_known_equipment": "Fryer", "first_seen": ""}
        existing = {"customer_name": "Joe Pizza", "city_area": "",
                    "service_state": "", "last_known_equipment": "", "first_seen": ""}
        self.assertEqual(mc.detect_field_conflicts(w, existing), [])


if __name__ == "__main__":
    unittest.main()
