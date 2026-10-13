-- Vehicle: one row per car (supports multiple generations)
CREATE TABLE vehicle (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    generation  TEXT NOT NULL
);

-- Driver: one row per person who drives
CREATE TABLE driver (
    id         INTEGER PRIMARY KEY,
    full_name  TEXT NOT NULL UNIQUE
);

-- Track location: a physical place
CREATE TABLE track_location (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    country  TEXT
);

-- Track layout: a specific course at a location, with a verified length in metres
CREATE TABLE track_layout (
    id                 INTEGER PRIMARY KEY,
    track_location_id  INTEGER NOT NULL REFERENCES track_location(id),
    name               TEXT NOT NULL,
    activity_type      TEXT NOT NULL CHECK (activity_type IN
                           ('skidpad','acceleration','autocross','endurance','other')),
    length_m           REAL NOT NULL CHECK (length_m > 0),
    UNIQUE (track_location_id, name)
);

-- Season: one row per testing season
CREATE TABLE season (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    CHECK (end_date > start_date)
);

-- Test: one row per test day
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

-- Run: one row per run during a test
CREATE TABLE run (
    id               INTEGER PRIMARY KEY,
    test_id          INTEGER NOT NULL REFERENCES test(id),
    driver_id        INTEGER NOT NULL REFERENCES driver(id),
    track_layout_id  INTEGER NOT NULL REFERENCES track_layout(id),
    ambient_temp_c   REAL,
    asphalt_temp_c   REAL,
    expected_laps    INTEGER CHECK (expected_laps >= 0),
    completed_laps   INTEGER CHECK (completed_laps >= 0)
);

-- Lap: one row per lap
CREATE TABLE lap (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES run(id),
    lap_number  INTEGER NOT NULL CHECK (lap_number >= 1),
    lap_time_s  REAL NOT NULL CHECK (lap_time_s > 0),
    penalty_s   REAL NOT NULL DEFAULT 0 CHECK (penalty_s >= 0),
    UNIQUE (run_id, lap_number)
);

-- Distance driven per run, calculated automatically from laps x layout length
CREATE VIEW run_distance AS
SELECT run.id                              AS run_id,
       run.test_id                         AS test_id,
       run.driver_id                       AS driver_id,
       test.vehicle_id                     AS vehicle_id,
       test.season_id                      AS season_id,
       COUNT(lap.id)                       AS laps,
       COUNT(lap.id) * track_layout.length_m AS distance_m
FROM run
JOIN test         ON test.id = run.test_id
JOIN track_layout ON track_layout.id = run.track_layout_id
LEFT JOIN lap     ON lap.run_id = run.id
GROUP BY run.id;