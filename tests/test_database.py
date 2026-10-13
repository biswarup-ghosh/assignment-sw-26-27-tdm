"""Automated tests for the Test Data Manager database.

Run from the project folder with:
    python3 -m unittest discover -s tests -v
"""
import sqlite3
import unittest
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "db"


def build_database():
    """Create a fresh in-memory database from schema.sql and seed.sql."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    for file_name in ["schema.sql", "seed.sql"]:
        conn.executescript((DB_DIR / file_name).read_text())
    return conn


class DatabaseTestCase(unittest.TestCase):
    """Base class: gives every test its own fresh database."""

    def setUp(self):
        self.conn = build_database()

    def tearDown(self):
        self.conn.close()

    def query(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def assertRejected(self, sql, params=()):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(sql, params)


# ---------------------------------------------------------------------
# Mileage
# ---------------------------------------------------------------------
class TestMileage(DatabaseTestCase):
    def test_distance_per_run(self):
        rows = self.query("SELECT run_id, distance_m FROM run_distance ORDER BY run_id")
        # run 1: 3 laps x 800 m, run 2: 3 laps x 1200 m, run 3: 2 laps x 800 m
        self.assertEqual(rows, [(1, 2400.0), (2, 3600.0), (3, 1600.0)])

    def test_total_km_per_driver(self):
        rows = self.query(
            "SELECT driver_id, SUM(distance_m) / 1000.0 FROM run_distance "
            "GROUP BY driver_id ORDER BY driver_id"
        )
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0][1], 4.0)   # driver 1: runs 1 and 3
        self.assertAlmostEqual(rows[1][1], 3.6)   # driver 2: run 2

    def test_total_km_per_vehicle_and_season(self):
        vehicle = self.query(
            "SELECT SUM(distance_m) / 1000.0 FROM run_distance WHERE vehicle_id = 1")
        season = self.query(
            "SELECT SUM(distance_m) / 1000.0 FROM run_distance WHERE season_id = 1")
        self.assertAlmostEqual(vehicle[0][0], 7.6)
        self.assertAlmostEqual(season[0][0], 7.6)

    def test_total_km_per_test(self):
        rows = self.query(
            "SELECT SUM(distance_m) / 1000.0 FROM run_distance WHERE test_id = 1")
        self.assertAlmostEqual(rows[0][0], 7.6)

    def test_run_without_laps_has_zero_distance(self):
        self.conn.execute(
            "INSERT INTO run (test_id, run_number, driver_id, track_layout_id) "
            "VALUES (1, 4, 1, 1)")
        rows = self.query("SELECT laps, distance_m FROM run_distance WHERE run_id = 4")
        self.assertEqual(rows, [(0, 0.0)])

    def test_mileage_updates_when_a_lap_is_added(self):
        self.conn.execute(
            "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (3, 3, 61.0)")
        rows = self.query("SELECT distance_m FROM run_distance WHERE run_id = 3")
        self.assertEqual(rows, [(2400.0,)])


# ---------------------------------------------------------------------
# Best lap
# ---------------------------------------------------------------------
class TestBestLap(DatabaseTestCase):
    BEST_LAP_SQL = (
        "SELECT run_id, MIN(lap_time_s + penalty_s) FROM lap "
        "GROUP BY run_id ORDER BY run_id"
    )

    def test_best_lap_per_run(self):
        rows = self.query(self.BEST_LAP_SQL)
        self.assertEqual([row[0] for row in rows], [1, 2, 3])
        self.assertAlmostEqual(rows[0][1], 61.8)
        self.assertAlmostEqual(rows[1][1], 94.6)
        self.assertAlmostEqual(rows[2][1], 61.2)

    def test_penalty_counts_towards_best_lap(self):
        # raw 61.0 would be the fastest, but with +2.0 s it becomes 63.0
        self.conn.execute(
            "INSERT INTO lap (run_id, lap_number, lap_time_s, penalty_s) "
            "VALUES (1, 4, 61.0, 2.0)")
        rows = self.query(self.BEST_LAP_SQL)
        self.assertAlmostEqual(rows[0][1], 61.8)

    def test_best_lap_updates_automatically(self):
        self.conn.execute(
            "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (1, 4, 60.0)")
        rows = self.query(self.BEST_LAP_SQL)
        self.assertAlmostEqual(rows[0][1], 60.0)


# ---------------------------------------------------------------------
# Historical (multi-filter) queries
# ---------------------------------------------------------------------
class TestHistoricalQueries(DatabaseTestCase):
    HISTORY_SQL = """
        SELECT run.id
        FROM run
        JOIN driver        ON driver.id = run.driver_id
        JOIN tyre_set      ON tyre_set.id = run.tyre_set_id
        JOIN tyre_compound ON tyre_compound.id = tyre_set.compound_id
        JOIN test          ON test.id = run.test_id
        JOIN season        ON season.id = test.season_id
        WHERE season.name = ?
          AND driver.full_name = ?
          AND tyre_compound.name = ?
          AND run.asphalt_temp_c BETWEEN ? AND ?
        ORDER BY run.id
    """

    def test_driver_compound_and_temperature_range(self):
        rows = self.query(self.HISTORY_SQL, ("2026/2027", "Marco Rossi", "Soft", 30, 40))
        self.assertEqual(rows, [(1,), (3,)])

    def test_narrower_temperature_range(self):
        rows = self.query(self.HISTORY_SQL, ("2026/2027", "Marco Rossi", "Soft", 34.5, 40))
        self.assertEqual(rows, [(3,)])

    def test_other_driver_and_compound(self):
        rows = self.query(self.HISTORY_SQL, ("2026/2027", "Giulia Bianchi", "Medium", 30, 40))
        self.assertEqual(rows, [(2,)])

    def test_no_match_for_wrong_compound(self):
        rows = self.query(self.HISTORY_SQL, ("2026/2027", "Marco Rossi", "Medium", 30, 40))
        self.assertEqual(rows, [])

    def test_no_match_for_other_season(self):
        rows = self.query(self.HISTORY_SQL, ("2025/2026", "Marco Rossi", "Soft", 30, 40))
        self.assertEqual(rows, [])


# ---------------------------------------------------------------------
# Setup story and plan versus actual
# ---------------------------------------------------------------------
class TestSetupStory(DatabaseTestCase):
    def test_changes_between_run_1_and_run_2(self):
        rows = self.query(
            "SELECT parameter, corner FROM setup_change WHERE run_id = 2")
        expected = {
            ("Spring rate", "FL"), ("Spring rate", "FR"),
            ("Static camber", "FL"), ("Static camber", "FR"),
            ("Power limit", "VEH"),
        }
        self.assertEqual(len(rows), 5)
        self.assertEqual(set(rows), expected)

    def test_old_and_new_value_and_reason(self):
        rows = self.query(
            "SELECT old_value, new_value, unit, changed_at, reason FROM setup_change "
            "WHERE run_id = 2 AND parameter = 'Power limit'")
        self.assertEqual(len(rows), 1)
        old, new, unit, changed_at, reason = rows[0]
        self.assertEqual((old, new, unit), (60.0, 80.0, "kW"))
        self.assertEqual(changed_at, "2026-10-12 11:30:00")
        self.assertIn("Understeer", reason)

    def test_no_changes_when_setup_is_the_same(self):
        # run 3 uses the same setup as run 2
        self.assertEqual(self.query("SELECT * FROM setup_change WHERE run_id = 3"), [])

    def test_first_run_has_nothing_to_compare_with(self):
        self.assertEqual(self.query("SELECT * FROM setup_change WHERE run_id = 1"), [])


class TestPlannedVsActual(DatabaseTestCase):
    def test_outcomes(self):
        rows = self.query("SELECT plan_number, run_number, outcome FROM planned_vs_actual")
        expected = {
            (1, 1, "as planned"),
            (2, 2, "modified"),
            (3, None, "cancelled"),
            (None, 3, "added"),
        }
        self.assertEqual(set(rows), expected)
        self.assertEqual(len(rows), 4)

    def test_cancelled_plan_shows_its_reason(self):
        rows = self.query(
            "SELECT cancel_reason FROM planned_vs_actual WHERE outcome = 'cancelled'")
        self.assertEqual(rows, [("Battery temperature too high, slot dropped",)])

    def test_plan_without_run_is_not_executed(self):
        self.conn.execute(
            "INSERT INTO planned_run (test_id, plan_number, driver_id, track_layout_id, "
            "expected_laps) VALUES (1, 4, 1, 1, 2)")
        rows = self.query(
            "SELECT outcome FROM planned_vs_actual WHERE plan_number = 4")
        self.assertEqual(rows, [("not executed",)])


# ---------------------------------------------------------------------
# Database constraints
# ---------------------------------------------------------------------
class TestConstraints(DatabaseTestCase):
    def test_valid_lap_is_accepted(self):
        self.conn.execute(
            "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (1, 4, 60.5)")
        count = self.query("SELECT COUNT(*) FROM lap WHERE run_id = 1")[0][0]
        self.assertEqual(count, 4)

    BAD_STATEMENTS = [
        ("negative lap time",
         "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (1, 4, -5)"),
        ("zero lap time",
         "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (1, 4, 0)"),
        ("negative penalty",
         "INSERT INTO lap (run_id, lap_number, lap_time_s, penalty_s) VALUES (1, 4, 60, -1)"),
        ("lap number zero",
         "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (1, 0, 60)"),
        ("lap of a run that does not exist",
         "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (99, 1, 60)"),
        ("duplicate lap number in a run",
         "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (1, 1, 60)"),
        ("invalid test status",
         "INSERT INTO test (season_id, vehicle_id, track_location_id, test_date, status) "
         "VALUES (1, 1, 1, '2026-11-01', 'banana')"),
        ("test with a vehicle that does not exist",
         "INSERT INTO test (season_id, vehicle_id, track_location_id, test_date, status) "
         "VALUES (1, 99, 1, '2026-11-01', 'planned')"),
        ("season that ends before it starts",
         "INSERT INTO season (name, start_date, end_date) "
         "VALUES ('X', '2027-01-01', '2026-01-01')"),
        ("track layout with zero length",
         "INSERT INTO track_layout (track_location_id, name, activity_type, length_m) "
         "VALUES (1, 'Bad', 'autocross', 0)"),
        ("track layout with unknown activity type",
         "INSERT INTO track_layout (track_location_id, name, activity_type, length_m) "
         "VALUES (1, 'Bad', 'drifting', 500)"),
        ("duplicate tyre set code",
         "INSERT INTO tyre_set (compound_id, code) VALUES (1, 'SET-001')"),
        ("negative tyre pressure",
         "INSERT INTO tyre_measurement (run_id, phase, corner, pressure_kpa) "
         "VALUES (3, 'pre', 'FL', -1)"),
        ("unknown tyre corner",
         "INSERT INTO tyre_measurement (run_id, phase, corner, pressure_kpa) "
         "VALUES (3, 'pre', 'XX', 85)"),
        ("unknown measurement phase",
         "INSERT INTO tyre_measurement (run_id, phase, corner, pressure_kpa) "
         "VALUES (3, 'during', 'FL', 85)"),
        ("duplicate tyre measurement",
         "INSERT INTO tyre_measurement (run_id, phase, corner, pressure_kpa) "
         "VALUES (1, 'pre', 'FL', 85)"),
        ("impossible camber",
         "INSERT INTO alignment_measurement (run_id, phase, corner, camber_deg, toe_deg) "
         "VALUES (3, 'pre', 'FL', 50, 0)"),
        ("cancelled plan without a reason",
         "INSERT INTO planned_run (test_id, plan_number, driver_id, track_layout_id, "
         "expected_laps, cancelled) VALUES (1, 4, 1, 1, 3, 1)"),
        ("duplicate plan number in a test",
         "INSERT INTO planned_run (test_id, plan_number, driver_id, track_layout_id, "
         "expected_laps) VALUES (1, 1, 1, 1, 3)"),
        ("negative target lap time",
         "INSERT INTO planned_run (test_id, plan_number, driver_id, track_layout_id, "
         "expected_laps, target_lap_time_s) VALUES (1, 4, 1, 1, 3, -5)"),
        ("run claiming a plan that is already used",
         "UPDATE run SET planned_run_id = 1 WHERE id = 3"),
        ("duplicate run number in a test",
         "INSERT INTO run (test_id, run_number, driver_id, track_layout_id) "
         "VALUES (1, 1, 1, 1)"),
        ("duplicate setup value",
         "INSERT INTO setup_value (setup_id, parameter_id, corner, value) "
         "VALUES (1, 1, 'FL', 99)"),
        ("duplicate file location",
         "INSERT INTO data_file (test_id, file_name, file_type, storage_location) "
         "VALUES (1, 'copy.csv', 'telemetry', 'storage/2026-10-12/run1_telemetry.csv')"),
        ("unknown file type",
         "INSERT INTO data_file (test_id, file_name, file_type, storage_location) "
         "VALUES (1, 'x.csv', 'banana', 'storage/x.csv')"),
        ("checksum of the wrong length",
         "INSERT INTO data_file (test_id, file_name, file_type, storage_location, "
         "checksum_sha256) VALUES (1, 'x.csv', 'log', 'storage/x.csv', 'abc')"),
        ("person assigned twice to the same station on a test",
         "INSERT INTO station_assignment (test_id, station_id, team_member_id, staff_role_id) "
         "VALUES (1, 1, 1, 1)"),
    ]

    def test_invalid_data_is_rejected(self):
        for description, sql in self.BAD_STATEMENTS:
            with self.subTest(description):
                self.assertRejected(sql)


class TestTriggers(DatabaseTestCase):
    def test_vehicle_parameter_cannot_be_set_on_a_corner(self):
        # parameter 11 = torque vectoring gain (whole vehicle)
        self.assertRejected(
            "INSERT INTO setup_value (setup_id, parameter_id, corner, value) "
            "VALUES (1, 11, 'FL', 0.5)")

    def test_corner_parameter_cannot_be_set_on_the_vehicle(self):
        # parameter 8 = corner weight (per corner)
        self.assertRejected(
            "INSERT INTO setup_value (setup_id, parameter_id, corner, value) "
            "VALUES (1, 8, 'VEH', 200)")

    def test_valid_scopes_are_accepted(self):
        self.conn.execute(
            "INSERT INTO setup_value (setup_id, parameter_id, corner, value) "
            "VALUES (1, 11, 'VEH', 0.5)")
        self.conn.execute(
            "INSERT INTO setup_value (setup_id, parameter_id, corner, value) "
            "VALUES (1, 8, 'FL', 70)")

    def test_file_cannot_link_a_run_from_another_test(self):
        self.conn.execute(
            "INSERT INTO test (season_id, vehicle_id, track_location_id, test_date, status) "
            "VALUES (1, 1, 1, '2026-10-20', 'planned')")          # becomes test 2
        self.assertRejected(
            "INSERT INTO data_file (test_id, run_id, file_name, file_type, storage_location) "
            "VALUES (2, 1, 'y.csv', 'telemetry', 'storage/y.csv')")

    def test_station_must_be_at_the_test_location(self):
        self.conn.execute(
            "INSERT INTO track_location (name, country) VALUES ('Other Track', 'Italy')")
        self.conn.execute(
            "INSERT INTO station (track_location_id, name) VALUES (2, 'Pit wall')")  # id 3
        self.assertRejected(
            "INSERT INTO station_assignment (test_id, station_id, team_member_id, "
            "staff_role_id) VALUES (1, 3, 1, 1)")


if __name__ == "__main__":
    unittest.main()