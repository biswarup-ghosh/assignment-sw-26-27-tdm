"""Tests for the legacy spreadsheet importer (tools/import_legacy.py)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import import_legacy as imp                   # noqa: E402
from test_database import build_database      # noqa: E402

SAMPLE = ROOT / "data" / "legacy_sample.csv"


class TestParsing(unittest.TestCase):
    def test_date_formats(self):
        for text in ["15/09/2026", "2026-09-15", "15-09-2026", "15.09.2026", "15 Sep 2026"]:
            with self.subTest(text):
                self.assertEqual(imp.parse_date(text), "2026-09-15")

    def test_impossible_date_is_rejected(self):
        with self.assertRaises(imp.RowError):
            imp.parse_date("31/02/2026")

    def test_temperatures(self):
        self.assertEqual(imp.parse_temp("22,5", "temp"), 22.5)
        self.assertEqual(imp.parse_temp("30 °C", "temp"), 30.0)
        self.assertEqual(imp.parse_temp("24 C", "temp"), 24.0)
        self.assertIsNone(imp.parse_temp("", "temp"))

    def test_bad_temperatures_are_rejected(self):
        for text in ["hot", "500"]:
            with self.subTest(text), self.assertRaises(imp.RowError):
                imp.parse_temp(text, "temp")

    def test_lap_times(self):
        self.assertEqual(imp.parse_laps("62.3; 1:01,5"), [62.3, 61.5])
        self.assertEqual(imp.parse_laps(""), [])

    def test_bad_lap_times_are_rejected(self):
        for text in ["-3", "0", "abc"]:
            with self.subTest(text), self.assertRaises(imp.RowError):
                imp.parse_laps(text)


class TestImport(unittest.TestCase):
    def setUp(self):
        self.conn = build_database()
        self.conn.isolation_level = None      # the importer manages transactions itself

    def tearDown(self):
        self.conn.close()

    def do_import(self, dry_run=False):
        return imp.run_import(self.conn, SAMPLE, "RUP-EV-26", dry_run=dry_run)

    def scalar(self, sql):
        return self.conn.execute(sql).fetchone()[0]

    def test_row_counts(self):
        result = self.do_import()
        self.assertEqual(result["imported"], 4)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(len(result["rejected"]), 4)

    def test_reject_reasons(self):
        result = self.do_import()
        reasons = " | ".join(reason for _, _, reason in result["rejected"])
        for expected in ["Skidpad", "31/02/2026", "driver is missing", "'-3'"]:
            self.assertIn(expected, reasons)

    def test_mileage_after_import(self):
        self.do_import()
        self.assertAlmostEqual(self.scalar("SELECT SUM(distance_m) / 1000.0 FROM run_distance"), 16.8)
        marco = self.scalar(
            "SELECT SUM(distance_m) / 1000.0 FROM run_distance "
            "WHERE driver_id = (SELECT id FROM driver WHERE full_name = 'Marco Rossi')")
        self.assertAlmostEqual(marco, 10.0)

    def test_new_reference_rows_are_created_once(self):
        self.do_import()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM driver"), 3)     # + Luca Verdi
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM tyre_set"), 3)   # + SET-003

    def test_rejected_row_leaves_no_trace(self):
        self.do_import()
        # the row on 06/10/2026 was rejected, so no test day may exist for that date
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM test WHERE test_date = '2026-10-06'"), 0)

    def test_dry_run_changes_nothing(self):
        result = self.do_import(dry_run=True)
        self.assertEqual(result["imported"], 4)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM run"), 3)
        self.assertAlmostEqual(self.scalar("SELECT SUM(distance_m) / 1000.0 FROM run_distance"), 7.6)

    def test_importing_twice_adds_nothing(self):
        self.do_import()
        second = self.do_import()
        self.assertEqual(second["imported"], 0)
        self.assertEqual(second["skipped"], 5)
        self.assertAlmostEqual(self.scalar("SELECT SUM(distance_m) / 1000.0 FROM run_distance"), 16.8)

    def test_unknown_vehicle_stops_the_import(self):
        with self.assertRaises(imp.FatalError):
            imp.run_import(self.conn, SAMPLE, "NO-SUCH-CAR")


if __name__ == "__main__":
    unittest.main()