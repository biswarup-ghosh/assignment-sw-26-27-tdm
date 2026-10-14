"""Test Data Manager: backend API (FastAPI + SQLite).

Start it from the project folder with:
    uvicorn backend.app:app --reload
Interactive documentation: http://127.0.0.1:8000/docs
"""
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

DB_PATH = Path(os.environ.get("TDM_DB", Path(__file__).resolve().parent.parent / "tdm.db"))

app = FastAPI(title="Test Data Manager API", version="1.0")
FRONTEND_FILE = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


@app.get("/", include_in_schema=False)
def home():
    """Serve the web page."""
    return FileResponse(FRONTEND_FILE)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def get_db():
    """Open one database connection per request, and always close it."""
    if not DB_PATH.exists():
        raise HTTPException(500, "Database not found. Run: python3 create_db.py")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def fetch(conn, sql, params=()):
    """Run a query and return the rows as a list of dictionaries."""
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def where_clause(filters):
    """Build ' WHERE a AND b' from (condition, value) pairs, skipping empty values.

    The conditions are fixed text written in this file; the values are passed
    separately as ? parameters, so user input is never part of the SQL text.
    """
    used = [(condition, value) for condition, value in filters if value is not None]
    if not used:
        return "", []
    return " WHERE " + " AND ".join(c for c, _ in used), [v for _, v in used]


def insert(conn, table, data):
    """Insert one row (table and column names come from the code, never from users)."""
    columns = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cursor = conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({marks})", list(data.values()))
    conn.commit()
    return {"id": cursor.lastrowid}


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error_handler(request, exc):
    """A database rule (CHECK, UNIQUE, foreign key, trigger) refused the data."""
    return JSONResponse(status_code=409, content={"error": str(exc)})


# ---------------------------------------------------------------------
# Lookup lists (used to fill filter menus in the frontend)
# ---------------------------------------------------------------------
LOOKUPS = {
    "seasons": "SELECT id, name, start_date, end_date FROM season ORDER BY start_date",
    "vehicles": "SELECT id, name, generation FROM vehicle ORDER BY name",
    "drivers": "SELECT id, full_name FROM driver ORDER BY full_name",
    "tyre-compounds": "SELECT id, name, supplier FROM tyre_compound ORDER BY name",
    "tyre-sets": """SELECT tyre_set.id, tyre_set.code, tyre_compound.name AS compound
                    FROM tyre_set JOIN tyre_compound ON tyre_compound.id = tyre_set.compound_id
                    ORDER BY tyre_set.code""",
    "track-layouts": """SELECT track_layout.id, track_layout.name, track_layout.activity_type,
                               track_layout.length_m, track_location.name AS location
                        FROM track_layout
                        JOIN track_location ON track_location.id = track_layout.track_location_id
                        ORDER BY track_location.name, track_layout.name""",
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/lookup/{name}")
def lookup(name: str, conn=Depends(get_db)):
    if name not in LOOKUPS:
        raise HTTPException(404, f"Unknown list. Choose one of: {', '.join(LOOKUPS)}")
    return fetch(conn, LOOKUPS[name])


# ---------------------------------------------------------------------
# Tests (test days)
# ---------------------------------------------------------------------
@app.get("/tests")
def list_tests(season: str | None = None, vehicle_id: int | None = None,
               status: str | None = None, conn=Depends(get_db)):
    where, params = where_clause([
        ("season.name = ?", season),
        ("test.vehicle_id = ?", vehicle_id),
        ("test.status = ?", status),
    ])
    sql = """
        SELECT test.id, test.test_date, test.status, season.name AS season,
               vehicle.name AS vehicle, track_location.name AS location,
               test.problems, test.conclusions,
               (SELECT COALESCE(SUM(distance_m), 0) / 1000.0
                FROM run_distance WHERE run_distance.test_id = test.id) AS km
        FROM test
        JOIN season         ON season.id = test.season_id
        JOIN vehicle        ON vehicle.id = test.vehicle_id
        JOIN track_location ON track_location.id = test.track_location_id
    """ + where + " ORDER BY test.test_date"
    return fetch(conn, sql, params)


@app.get("/tests/{test_id}/plan-vs-actual")
def plan_vs_actual(test_id: int, conn=Depends(get_db)):
    return fetch(
        conn,
        "SELECT * FROM planned_vs_actual WHERE test_id = ? "
        "ORDER BY COALESCE(plan_number, 999), run_number",
        [test_id])


# ---------------------------------------------------------------------
# Runs: the main historical query
# ---------------------------------------------------------------------
RUN_SELECT = """
    SELECT run.id, run.run_number, run.test_id, test.test_date,
           season.name AS season, vehicle.name AS vehicle, driver.full_name AS driver,
           track_layout.name AS layout, track_layout.activity_type,
           tyre_set.code AS tyre_set, tyre_compound.name AS compound,
           setup.name AS setup, run.ambient_temp_c, run.asphalt_temp_c,
           run.expected_laps, run.completed_laps,
           rd.laps AS lap_count, rd.distance_m,
           (SELECT MIN(lap_time_s + penalty_s) FROM lap WHERE lap.run_id = run.id) AS best_lap_s
    FROM run
    JOIN test             ON test.id = run.test_id
    JOIN season           ON season.id = test.season_id
    JOIN vehicle          ON vehicle.id = test.vehicle_id
    JOIN driver           ON driver.id = run.driver_id
    JOIN track_layout     ON track_layout.id = run.track_layout_id
    LEFT JOIN tyre_set      ON tyre_set.id = run.tyre_set_id
    LEFT JOIN tyre_compound ON tyre_compound.id = tyre_set.compound_id
    LEFT JOIN setup         ON setup.id = run.setup_id
    LEFT JOIN run_distance AS rd ON rd.run_id = run.id
"""


@app.get("/runs")
def list_runs(
    season: str | None = None,
    driver: str | None = None,
    vehicle_id: int | None = None,
    compound: str | None = None,
    tyre_set: str | None = None,
    activity_type: str | None = None,
    test_id: int | None = None,
    setup_id: int | None = None,
    asphalt_min: float | None = None,
    asphalt_max: float | None = None,
    ambient_min: float | None = None,
    ambient_max: float | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn=Depends(get_db),
):
    """Search runs with any combination of filters (all optional)."""
    where, params = where_clause([
        ("season.name = ?", season),
        ("driver.full_name = ?", driver),
        ("test.vehicle_id = ?", vehicle_id),
        ("tyre_compound.name = ?", compound),
        ("tyre_set.code = ?", tyre_set),
        ("track_layout.activity_type = ?", activity_type),
        ("run.test_id = ?", test_id),
        ("run.setup_id = ?", setup_id),
        ("run.asphalt_temp_c >= ?", asphalt_min),
        ("run.asphalt_temp_c <= ?", asphalt_max),
        ("run.ambient_temp_c >= ?", ambient_min),
        ("run.ambient_temp_c <= ?", ambient_max),
        ("test.test_date >= ?", date_from.isoformat() if date_from else None),
        ("test.test_date <= ?", date_to.isoformat() if date_to else None),
    ])
    sql = RUN_SELECT + where + " ORDER BY test.test_date, run.run_number LIMIT ? OFFSET ?"
    return fetch(conn, sql, params + [limit, offset])


@app.get("/runs/{run_id}")
def get_run(run_id: int, conn=Depends(get_db)):
    """Everything known about one run."""
    runs = fetch(conn, RUN_SELECT + " WHERE run.id = ?", [run_id])
    if not runs:
        raise HTTPException(404, "Run not found")
    run = runs[0]
    run["laps"] = fetch(
        conn,
        "SELECT lap_number, lap_time_s, penalty_s, lap_time_s + penalty_s AS effective_time_s "
        "FROM lap WHERE run_id = ? ORDER BY lap_number", [run_id])
    run["tyre_measurements"] = fetch(
        conn,
        "SELECT phase, corner, pressure_kpa, temp_outer_c, temp_center_c, temp_inner_c "
        "FROM tyre_measurement WHERE run_id = ? ORDER BY phase DESC, corner", [run_id])
    run["alignment"] = fetch(
        conn,
        "SELECT phase, corner, camber_deg, toe_deg "
        "FROM alignment_measurement WHERE run_id = ? ORDER BY phase DESC, corner", [run_id])
    run["setup_values"] = fetch(
        conn,
        """SELECT sp.name AS parameter, sv.corner, sv.value, sp.unit
           FROM setup_value AS sv
           JOIN setup_parameter AS sp ON sp.id = sv.parameter_id
           WHERE sv.setup_id = (SELECT setup_id FROM run WHERE id = ?)
           ORDER BY sp.category, sp.name, sv.corner""", [run_id])
    run["setup_changes"] = fetch(
        conn,
        "SELECT parameter, corner, old_value, new_value, unit, changed_at, reason "
        "FROM setup_change WHERE run_id = ?", [run_id])
    run["files"] = fetch(
        conn,
        "SELECT file_name, file_type, storage_location, size_bytes "
        "FROM data_file WHERE run_id = ?", [run_id])
    return run


# ---------------------------------------------------------------------
# Mileage
# ---------------------------------------------------------------------
# group name -> (table to join, expression used as label, join condition)
MILEAGE_GROUPS = {
    "run":     ("run",     "'Run ' || run.id", "run.id = rd.run_id"),
    "test":    ("test",    "test.test_date",   "test.id = rd.test_id"),
    "season":  ("season",  "season.name",      "season.id = rd.season_id"),
    "driver":  ("driver",  "driver.full_name", "driver.id = rd.driver_id"),
    "vehicle": ("vehicle", "vehicle.name",     "vehicle.id = rd.vehicle_id"),
}


@app.get("/mileage")
def mileage(group_by: Literal["run", "test", "season", "driver", "vehicle"],
            conn=Depends(get_db)):
    """Cumulative distance in km per run, test, season, driver or vehicle."""
    table, label, join_on = MILEAGE_GROUPS[group_by]
    sql = (f"SELECT {table}.id AS id, {label} AS name, "
           f"ROUND(SUM(rd.distance_m) / 1000.0, 3) AS km "
           f"FROM run_distance AS rd JOIN {table} ON {join_on} "
           f"GROUP BY {table}.id ORDER BY {table}.id")
    return fetch(conn, sql)


# ---------------------------------------------------------------------
# Creating data
# ---------------------------------------------------------------------
class DriverIn(BaseModel):
    full_name: str = Field(min_length=1)


class TestDayIn(BaseModel):
    season_id: int
    vehicle_id: int
    track_location_id: int
    test_date: date
    status: Literal["planned", "done", "cancelled"] = "planned"
    problems: str | None = None
    conclusions: str | None = None


class RunIn(BaseModel):
    test_id: int
    run_number: int = Field(ge=1)
    driver_id: int
    track_layout_id: int
    planned_run_id: int | None = None
    tyre_set_id: int | None = None
    setup_id: int | None = None
    ambient_temp_c: float | None = None
    asphalt_temp_c: float | None = None
    expected_laps: int | None = Field(default=None, ge=0)
    completed_laps: int | None = Field(default=None, ge=0)


class LapIn(BaseModel):
    lap_number: int = Field(ge=1)
    lap_time_s: float = Field(gt=0)
    penalty_s: float = Field(default=0, ge=0)


@app.post("/drivers", status_code=201)
def create_driver(body: DriverIn, conn=Depends(get_db)):
    return insert(conn, "driver", body.model_dump())


@app.post("/tests", status_code=201)
def create_test(body: TestDayIn, conn=Depends(get_db)):
    data = body.model_dump()
    data["test_date"] = data["test_date"].isoformat()
    return insert(conn, "test", data)


@app.post("/runs", status_code=201)
def create_run(body: RunIn, conn=Depends(get_db)):
    return insert(conn, "run", body.model_dump())


@app.post("/runs/{run_id}/laps", status_code=201)
def create_lap(run_id: int, body: LapIn, conn=Depends(get_db)):
    if not conn.execute("SELECT 1 FROM run WHERE id = ?", (run_id,)).fetchone():
        raise HTTPException(404, "Run not found")
    return insert(conn, "lap", {"run_id": run_id, **body.model_dump()})