# Copyright (c) 2026, BOQ Budget Control and contributors
"""Pure parser tests for the BOQ Excel import (no database needed).

Run:  bench --site <site> run-tests --module boq_budget_control.boq_budget.test_boq_import
  or: python -m unittest boq_budget_control.boq_budget.test_boq_import  (from apps/boq_budget_control)
"""

import os
import unittest

from boq_budget_control.boq_budget import boq_import as bi

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "fixtures")
VILLA = os.path.join(FIXTURES, "BOQ_G_Only_Villa.xlsx")
REDWOOD = os.path.join(FIXTURES, "REDWOOD_Nursery.xlsx")
UOMS = ["Nos", "LS", "m2", "m3", "LM"]

VILLA_CATEGORIES = [
	"Preliminaries", "Sub Structure", "Super Structure", "Block Work", "Flooring and Skirting",
	"Ceramic wall Cladding", "Internal Walls & Ceiling Finishes", "False Ceiling Work",
	"External Wall Finishes", "Aluminum Works (Windows & Doors)", "Metal works",
	"Glass Partitions in Bathrooms", "Carpentry & joinery work", "Water Proofing",
	"Plumbing & Sanitary work", "Internal and External Drainage Work", "Electrical Work",
	"Supply and Installation of Air-conditioning System & fresh air", "Fire Fighting &Fire Alarm Works",
	"Intercom, Structral Cabling and CCTV Works", "External Works", "Boundary Wall", "Boundary Wall Gates",
]


def _masters(names):
	return [{"name": n, "category_name": n} for n in names]


class TestVillaImport(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.p = bi.build_preview(VILLA, _masters(VILLA_CATEGORIES), UOMS)
		cls.cats = {c["source_name"]: c for c in cls.p["categories"]}

	def test_header_and_columns(self):
		self.assertEqual(self.p["sheet"], "BOQ")
		self.assertEqual(self.p["header_row"], 16)
		self.assertEqual(self.p["columns"], {"number": "A", "description": "B", "unit": "C", "qty": "D",
											 "rate": "E", "amount": "F", "total": "G", "remarks": "H"})

	def test_counts_and_total(self):
		self.assertEqual(self.p["errors"], [])
		self.assertEqual(self.p["summary"]["categories"], 23)
		self.assertEqual(self.p["summary"]["lines"], 86)
		self.assertEqual(self.p["summary"]["total"], 1278508.0)

	def test_super_structure_subtotal_mismatch_warned(self):
		c = self.cats["Super Structure"]
		self.assertEqual(c["amount"], 133200.0)
		self.assertEqual(c["sheet_subtotal"], 118200.0)
		self.assertTrue(any("Super Structure" in w and "15,000.00" in w for w in self.p["warnings"]))

	def test_totals_and_discount_reported(self):
		values = [(t["label"], t["value"]) for t in self.p["totals"]]
		self.assertEqual(values, [("GRAND TOTAL AMOUNT", 1263508.0), ("Discount", 13508.0),
								  ("GRAND TOTAL AMOUNT", 1250000.0)])

	def test_line_without_sno_under_preliminaries(self):
		line = self.cats["Preliminaries"]["lines"][0]
		self.assertEqual(line["boq_ref"], "")
		self.assertEqual((line["qty"], line["rate"], line["amount"], line["uom"]), (1.0, 30000.0, 30000.0, "LS"))

	def test_category_with_own_qty_rate(self):
		c = self.cats["Boundary Wall Gates"]
		self.assertEqual(len(c["lines"]), 1)
		self.assertEqual(c["lines"][0]["amount"], 38000.0)
		self.assertIn("PS Item", c["lines"][0]["remarks"])

	def test_whitespace_rate_on_category_header(self):
		c = self.cats["Aluminum Works (Windows & Doors)"]
		self.assertEqual(c["boq_ref"], "13")
		self.assertEqual(len(c["lines"]), 1)

	def test_unpriced_lines(self):
		unpriced = {l["boq_ref"]: l for c in self.p["categories"] for l in c["lines"] if l["unpriced"]}
		self.assertEqual(sorted(unpriced), ["15.01", "16.04", "16.05", "7.01", "9.02"])
		for l in unpriced.values():
			self.assertEqual((l["qty"], l["rate"], l["amount"]), (1.0, 0.0, 0.0))
			self.assertTrue(l["remarks"].startswith(bi.UNPRICED_REMARK))

	def test_refs_normalised(self):
		refs = [l["boq_ref"] for l in self.cats["Sub Structure"]["lines"]]
		self.assertIn("2.10", refs)
		refs = [l["boq_ref"] for l in self.cats["Boundary Wall"]["lines"]]
		self.assertIn("33.12", refs)

	def test_live_masters_block(self):
		live = ["Preliminaries", "Sub Structure", "Super Structure", "Block Work", "Flooring and Skirting",
				"Ceramic wall Cladding", "Internal Walls & Ceiling Finishes", "False Ceiling Work",
				"External Wall Finishes", "Aluminum Works (Windows & Doors)", "Metal works", "Glass Partitions",
				"Carpentry & joinery work", "Water Proofing", "Plumbing & Sanitary work",
				"Internal and External Drainage Work", "Electrical Work", "Air-conditioning System & fresh air",
				"Fire Fighting &Fire Alarm Works", "Intercom, Structral Cabling and CCTV Works",
				"External / Landscape Works", "Boundary Wall", "Gates"]
		p = bi.build_preview(VILLA, _masters(live), UOMS)
		text = "\n".join(p["errors"])
		self.assertIn("Glass Partitions in Bathrooms", text)
		self.assertIn("Air-conditioning", text)
		self.assertIn("External Works", text)
		self.assertIn("both match category 'Boundary Wall'", text)
		self.assertNotIn("match category 'Metal works'", text)  # 'External Works' must not match 'Metal works'


class TestRedwoodImport(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.p = bi.build_preview(REDWOOD, _masters(["Preliminaries", "Metal works"]), UOMS)

	def test_header_with_swapped_columns(self):
		self.assertEqual(self.p["header_row"], 2)
		self.assertEqual(self.p["columns"]["qty"], "D")
		self.assertEqual(self.p["columns"]["unit"], "E")
		self.assertNotIn("Reference Images", self.p["columns"].values())

	def test_sections_and_stop_before_terms(self):
		names = [c["source_name"] for c in self.p["categories"]]
		self.assertEqual(len(names), 15)
		self.assertEqual(names[0], "GF Reception")
		self.assertEqual(names[-1], "All Outdoor Areas")
		self.assertFalse(any("Terms" in n or "quotation" in n.lower() for n in names))

	def test_skips(self):
		reasons = [s["reason"] for s in self.p["skipped"]]
		self.assertGreaterEqual(reasons.count("Subtotal"), 14)
		self.assertTrue(any(r.startswith("Qty is text") for r in reasons))
		self.assertIn("Inclusion / exclusion heading", reasons)
		self.assertIn("End of BOQ (notes / terms)", reasons)

	def test_all_unpriced_and_room_names_blocked(self):
		self.assertEqual(self.p["summary"]["unpriced_lines"], self.p["summary"]["lines"])
		self.assertEqual(self.p["summary"]["total"], 0.0)
		self.assertTrue(any("GF Reception" in e for e in self.p["errors"]))


class TestHelpers(unittest.TestCase):
	def test_similarity(self):
		self.assertEqual(bi.similarity("Blockwork", "Block Work"), 1.0)
		self.assertEqual(bi.similarity("Internal Walls and Ceiling Finishes", "Internal Walls & Ceiling Finishes"), 1.0)
		self.assertLess(bi.similarity("External Works", "Metal works"), bi.MATCH_THRESHOLD)
		self.assertGreaterEqual(bi.similarity("Electrical Works", "Electrical Work"), bi.MATCH_THRESHOLD)

	def test_uom(self):
		self.assertEqual(bi.match_uom("L.S.", UOMS), "LS")
		self.assertEqual(bi.match_uom("No.s", UOMS), "Nos")
		self.assertEqual(bi.match_uom("M3", UOMS), "m3")
		self.assertIsNone(bi.match_uom("Bag", UOMS))

	def test_format_ref(self):
		self.assertEqual(bi.format_ref(2.1), "2.10")
		self.assertEqual(bi.format_ref(33.1200000000001), "33.12")
		self.assertEqual(bi.format_ref(8.014), "8.014")
		self.assertEqual(bi.format_ref(3), "3")


if __name__ == "__main__":
	unittest.main()
