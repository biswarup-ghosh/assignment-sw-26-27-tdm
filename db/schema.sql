-- =====================================================================
-- TDM schema. Units are metric/SI and are written in column names:
--   _m metres, _s seconds, _c degrees Celsius, _kpa kilopascals,
--   _kg kilograms, _deg degrees, _mm millimetres, _kw kilowatts
-- Corner codes: FL front-left, FR front-right, RL rear-left, RR rear-right
-- =====================================================================

CREATE TABLE vehicle (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    generation  TEXT NOT NULL
);

CREATE TABLE driver (
    id         INTEGER PRIMARY KEY,
    full_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE track_location (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    country  TEXT
);

CREATE TABLE track_layout (
    id                 INTEGER PRIMARY KEY,
    track_location_id  INTEGER NOT NULL REFERENCES track_location(id),
    name               TEXT NOT NULL,
    activity_type      TEXT NOT NULL CHECK (activity_type IN
                           ('skidpad','acceleration','autocross','endurance','other')),
    length_m           REAL NOT NULL CHECK (length_m > 0),
    UNIQUE (track_location_id, name)
);

CREATE TABLE tyre_compound (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    supplier  TEXT NOT NULL
);

CREATE TABLE tyre_set (
    id           INTEGER PRIMARY KEY,
    compound_id  INTEGER NOT NULL REFERENCES tyre_compound(id),
    code         TEXT NOT NULL UNIQUE
);

CREATE TABLE season (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    CHECK (end_date > start_date)
);

CREATE TABLE test (
    id                 INTEGER PRIMARY KEY,
    season_id          INTEGER NOT NULL REFERENCES season(id),
    vehicle_id         INTEGER NOT NULL REFERENCES vehicle(id),
    track_location_id  INTEGER NOT NULL REFERENCES track_location(id),
    test_date          DATE NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('planned','done','cancelled')),
    problems           TEXT,
    conclusions        TEXT
);

-- ---------------------------------------------------------------------
-- SETUPS
-- ---------------------------------------------------------------------

-- Catalogue of everything that can be set on the car
CREATE TABLE setup_parameter (
    id        INTEGER PRIMARY KEY,
    code      TEXT NOT NULL UNIQUE,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL CHECK (category IN
                  ('suspension','alignment','weight','control')),
    scope     TEXT NOT NULL CHECK (scope IN ('vehicle','corner')),
    unit      TEXT NOT NULL
);

-- A setup snapshot: reusable, and optionally derived from an earlier setup
CREATE TABLE setup (
    id                 INTEGER PRIMARY KEY,
    vehicle_id         INTEGER NOT NULL REFERENCES vehicle(id),
    name               TEXT NOT NULL,
    based_on_setup_id  INTEGER REFERENCES setup(id),
    change_reason      TEXT,
    created_at         DATETIME NOT NULL,
    UNIQUE (vehicle_id, name)
);

-- The values of a setup. corner is 'VEH' for whole-car parameters.
CREATE TABLE setup_value (
    id            INTEGER PRIMARY KEY,
    setup_id      INTEGER NOT NULL REFERENCES setup(id),
    parameter_id  INTEGER NOT NULL REFERENCES setup_parameter(id),
    corner        TEXT NOT NULL CHECK (corner IN ('VEH','FL','FR','RL','RR')),
    value         REAL NOT NULL,
    UNIQUE (setup_id, parameter_id, corner)
);

-- Refuse a whole-car parameter on a corner, or a corner parameter on 'VEH'
CREATE TRIGGER setup_value_scope_check
BEFORE INSERT ON setup_value
FOR EACH ROW
WHEN ((SELECT scope FROM setup_parameter WHERE id = NEW.parameter_id) = 'vehicle'
        AND NEW.corner <> 'VEH')
  OR ((SELECT scope FROM setup_parameter WHERE id = NEW.parameter_id) = 'corner'
        AND NEW.corner = 'VEH')
BEGIN
    SELECT RAISE(ABORT, 'parameter scope does not match corner');
END;

-- ---------------------------------------------------------------------
-- PLANNING
-- ---------------------------------------------------------------------

-- A planned run: what the team intended to do, decided before the test
CREATE TABLE planned_run (
    id                        INTEGER PRIMARY KEY,
    test_id                   INTEGER NOT NULL REFERENCES test(id),
    plan_number               INTEGER NOT NULL CHECK (plan_number >= 1),
    driver_id                 INTEGER NOT NULL REFERENCES driver(id),
    track_layout_id           INTEGER NOT NULL REFERENCES track_layout(id),
    setup_id                  INTEGER REFERENCES setup(id),
    expected_laps             INTEGER NOT NULL CHECK (expected_laps >= 0),
    target_lap_time_s         REAL CHECK (target_lap_time_s > 0),
    battery_charge_limit_pct  REAL CHECK (battery_charge_limit_pct BETWEEN 0 AND 100),
    cancelled                 INTEGER NOT NULL DEFAULT 0 CHECK (cancelled IN (0, 1)),
    cancel_reason             TEXT,
    CHECK (cancelled = 0 OR cancel_reason IS NOT NULL),
    UNIQUE (test_id, plan_number)
);

-- ---------------------------------------------------------------------
-- RUNS AND LAPS
-- ---------------------------------------------------------------------

CREATE TABLE run (
    id               INTEGER PRIMARY KEY,
    test_id          INTEGER NOT NULL REFERENCES test(id),
    run_number       INTEGER NOT NULL CHECK (run_number >= 1),
    planned_run_id   INTEGER UNIQUE REFERENCES planned_run(id),
    driver_id        INTEGER NOT NULL REFERENCES driver(id),
    track_layout_id  INTEGER NOT NULL REFERENCES track_layout(id),
    tyre_set_id      INTEGER REFERENCES tyre_set(id),
    setup_id         INTEGER REFERENCES setup(id),
    ambient_temp_c   REAL,
    asphalt_temp_c   REAL,
    expected_laps    INTEGER CHECK (expected_laps >= 0),
    completed_laps   INTEGER CHECK (completed_laps >= 0),
    UNIQUE (test_id, run_number)
);

CREATE TABLE lap (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES run(id),
    lap_number  INTEGER NOT NULL CHECK (lap_number >= 1),
    lap_time_s  REAL NOT NULL CHECK (lap_time_s > 0),
    penalty_s   REAL NOT NULL DEFAULT 0 CHECK (penalty_s >= 0),
    UNIQUE (run_id, lap_number)
);

-- ---------------------------------------------------------------------
-- MEASUREMENTS
-- ---------------------------------------------------------------------

CREATE TABLE tyre_measurement (
    id             INTEGER PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES run(id),
    phase          TEXT NOT NULL CHECK (phase IN ('pre','post')),
    corner         TEXT NOT NULL CHECK (corner IN ('FL','FR','RL','RR')),
    pressure_kpa   REAL NOT NULL CHECK (pressure_kpa > 0 AND pressure_kpa < 500),
    temp_outer_c   REAL CHECK (temp_outer_c  BETWEEN -40 AND 200),
    temp_center_c  REAL CHECK (temp_center_c BETWEEN -40 AND 200),
    temp_inner_c   REAL CHECK (temp_inner_c  BETWEEN -40 AND 200),
    UNIQUE (run_id, phase, corner)
);

-- Physically measured alignment. Convention: toe positive = toe-in.
CREATE TABLE alignment_measurement (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES run(id),
    phase       TEXT NOT NULL CHECK (phase IN ('pre','post')),
    corner      TEXT NOT NULL CHECK (corner IN ('FL','FR','RL','RR')),
    camber_deg  REAL NOT NULL CHECK (camber_deg BETWEEN -10 AND 10),
    toe_deg     REAL NOT NULL CHECK (toe_deg BETWEEN -5 AND 5),
    UNIQUE (run_id, phase, corner)
);

-- ---------------------------------------------------------------------
-- VIEWS (always calculated from the real data, never stored)
-- ---------------------------------------------------------------------

-- Distance driven per run = laps x layout length
CREATE VIEW run_distance AS
SELECT run.id                                AS run_id,
       run.test_id                           AS test_id,
       run.driver_id                         AS driver_id,
       test.vehicle_id                       AS vehicle_id,
       test.season_id                        AS season_id,
       COUNT(lap.id)                         AS laps,
       COUNT(lap.id) * track_layout.length_m AS distance_m
FROM run
JOIN test         ON test.id = run.test_id
JOIN track_layout ON track_layout.id = run.track_layout_id
LEFT JOIN lap     ON lap.run_id = run.id
GROUP BY run.id;

-- What changed in the setup between each run and the previous run of the same test
CREATE VIEW setup_change AS
SELECT cur.test_id       AS test_id,
       prev.id           AS previous_run_id,
       cur.id            AS run_id,
       sp.name           AS parameter,
       a.corner          AS corner,
       a.value           AS old_value,
       b.value           AS new_value,
       sp.unit           AS unit,
       s.created_at      AS changed_at,
       s.change_reason   AS reason
FROM run AS cur
JOIN run AS prev
     ON prev.test_id = cur.test_id AND prev.run_number = cur.run_number - 1
JOIN setup_value AS a
     ON a.setup_id = prev.setup_id
JOIN setup_value AS b
     ON b.setup_id = cur.setup_id
    AND b.parameter_id = a.parameter_id
    AND b.corner = a.corner
JOIN setup_parameter AS sp ON sp.id = a.parameter_id
JOIN setup AS s            ON s.id = cur.setup_id
WHERE a.value <> b.value;

-- Plan versus reality, one row per planned run plus one row per unplanned run
CREATE VIEW planned_vs_actual AS
SELECT p.test_id          AS test_id,
       p.plan_number      AS plan_number,
       r.run_number       AS run_number,
       CASE
           WHEN r.id IS NULL AND p.cancelled = 1 THEN 'cancelled'
           WHEN r.id IS NULL                     THEN 'not executed'
           WHEN r.driver_id       <> p.driver_id
             OR r.track_layout_id <> p.track_layout_id
             OR r.setup_id        IS NOT p.setup_id
             OR r.completed_laps  IS NOT p.expected_laps THEN 'modified'
           ELSE 'as planned'
       END                AS outcome,
       pd.full_name       AS planned_driver,
       ad.full_name       AS actual_driver,
       ps.name            AS planned_setup,
       aset.name          AS actual_setup,
       p.expected_laps    AS planned_laps,
       r.completed_laps   AS actual_laps,
       p.cancel_reason    AS cancel_reason
FROM planned_run AS p
LEFT JOIN run     AS r    ON r.planned_run_id = p.id
JOIN driver       AS pd   ON pd.id = p.driver_id
LEFT JOIN driver  AS ad   ON ad.id = r.driver_id
LEFT JOIN setup   AS ps   ON ps.id = p.setup_id
LEFT JOIN setup   AS aset ON aset.id = r.setup_id

UNION ALL

SELECT r.test_id, NULL, r.run_number, 'added',
       NULL, d.full_name,
       NULL, s.name,
       NULL, r.completed_laps,
       NULL
FROM run AS r
JOIN driver      AS d ON d.id = r.driver_id
LEFT JOIN setup  AS s ON s.id = r.setup_id
WHERE r.planned_run_id IS NULL;