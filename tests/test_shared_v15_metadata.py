"""Offline migration guards for the shared v15 Stock Settings metadata."""

import json
import unittest
from datetime import datetime
from pathlib import Path

STOCK_SETTINGS = (
	Path(__file__).resolve().parents[1] / "erpnext/stock/doctype/stock_settings/stock_settings.json"
)


class TestSharedV15StockSettings(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.metadata = json.loads(STOCK_SETTINGS.read_text())

	def test_field_order_contains_every_field_exactly_once(self):
		field_names = [field["fieldname"] for field in self.metadata["fields"]]
		self.assertEqual(len(field_names), len(set(field_names)), "Duplicate field definitions")
		self.assertEqual(
			len(self.metadata["field_order"]),
			len(set(self.metadata["field_order"])),
			"Repeated field order entries prevent native customization synchronization",
		)
		self.assertEqual(set(self.metadata["field_order"]), set(field_names))

	def test_migration_reloads_sites_with_the_earlier_v15_75_metadata_fix(self):
		# Immutable earlier fork correction ddc14ab7f6 (ERPNext #2).
		previous_correction = datetime.fromisoformat("2026-09-17 07:40:00.000000")
		self.assertGreater(datetime.fromisoformat(self.metadata["modified"]), previous_correction)

	def test_shared_metadata_does_not_enable_stock_policy_changes_by_default(self):
		fields = {field["fieldname"]: field for field in self.metadata["fields"]}
		# Existing sites retain their stored Single values; these are fresh-install defaults.
		for fieldname in (
			"allow_negative_stock",
			"allow_negative_stock_for_batch",
			"validate_material_transfer_warehouses",
			"allow_internal_transfer_at_arms_length_price",
		):
			with self.subTest(fieldname=fieldname):
				self.assertEqual(fields[fieldname]["fieldtype"], "Check")
				self.assertEqual(fields[fieldname]["default"], "0")


if __name__ == "__main__":
	unittest.main()
