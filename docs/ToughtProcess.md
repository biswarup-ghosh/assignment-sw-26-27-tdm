# Thought Process

I started from the README and listed the real-world things in it before writing any SQL:
seasons, tests, runs, laps, drivers, vehicles, tyres, setups, tracks, files and stations.
I first built the core chain Season -> Test -> Run -> Lap, checked it by inserting good and
bad data by hand, and then added one area at a time (tracks and mileage, tyres, setups,
planning, files and stations). After each step I rebuilt the database from scratch and re-ran
my checks, so the database always matched the schema file.

## Main decisions and why

**1. A strict hierarchy that does not depend on one car or year.**
Every test belongs to a season and a vehicle, so several seasons and vehicle generations work
without changing the schema. A test is the hub that links the date, vehicle, track, status,
problems and conclusions.

**2. Setups are a catalogue, snapshots and values, not one wide table.**
The README warns against a flat, wide table. Springs, dampers, camber, toe, corner weights,
shims and control maps for four corners would be dozens of columns, and every new parameter
would need a schema change. Instead, `setup_parameter` lists what can be set (with unit,
category and whether it is per vehicle or per corner), `setup` is a reusable snapshot with a
reason and a link to the setup it was derived from, and `setup_value` holds one number per
parameter and corner. Adding a new parameter is just adding a row. The cost is that every
value is a number and the database cannot apply a different rule to each parameter.

**3. `VEH` instead of an empty value for whole-vehicle parameters.**
In SQLite an empty value (`NULL`) is never equal to another one, so a `UNIQUE` rule would not
stop duplicate whole-vehicle rows. Using a fixed code (`VEH`) makes the uniqueness rule work.
A trigger also refuses a whole-vehicle parameter on a corner, and a corner parameter on `VEH`.

**4. The plan and the real run are separate tables.**
The README wants both kept. `planned_run` stores the intention, `run` stores what happened, and
`run.planned_run_id` is an optional, unique link. A run with no plan is an added run, and a
plan with no run is cancelled or not executed. Cancelling requires a reason (a `CHECK`).
The outcome label is calculated by a view, so it is always consistent.

**5. Tyre compound and physical tyre set are different things.**
A compound is a type of rubber and a set is a physical object. Separating them lets me query
by compound while also tracking each real set. `tyre_set.code` is unique, which prevents
duplicate tyre IDs.

**6. Measurements are rows, not columns.**
Pressure and temperatures at four corners, before and after a run, would be many columns.
Instead there is one row per run, phase (pre or post) and corner. The alignment measurements
(camber and toe) work the same way. Setup values are the targets and measurements are what was
physically measured, and I kept them apart, linked through the run.

**7. Anything that can be calculated is a view.**
Mileage, best lap, setup changes and plan-versus-actual are calculated from the real data.
Storing them would need manual updating, which is exactly what the team wants to remove.

**8. Data integrity is enforced by the database itself.**
Foreign keys, `NOT NULL`, `UNIQUE`, and `CHECK` rules (positive lap times, valid corners and
phases, sensible pressure, temperature, camber and toe ranges) stop impossible data from
being saved, whichever program writes to it. Triggers cover rules that need another table
(parameter scope, file/run consistency, station location).

**9. The file index stores the location, not the file.**
The TDM is not a telemetry analyser, so `data_file` stores the path, type, size and an optional
checksum for each file, linked to a test and optionally to a run. A path can only be registered
once.

**10. Stations are reusable.**
A station belongs to a location and is defined once. Staff are assigned per test with a role,
so the same station can be reused on every test day.

**11. SQLite.**
I chose it because the database is one file and needs no installation, so anyone can rebuild
and test it in seconds. The trade-off is limited concurrent writing, and the schema is standard
enough to move to PostgreSQL later.

## How the database answers the main question

The README's example query (a driver, a tyre compound and an asphalt temperature range in the
current season) is a set of joins from `run` to `driver`, `tyre_set`, `tyre_compound`, `test`
and `season`, with one `WHERE` filter for each condition. Every condition is an ordinary
column, so adding another filter just means adding another condition.

## How I checked it

I wrote seed data that includes a modified, a cancelled and an added run, then ran queries by
hand for mileage, setup changes, plan versus actual and the example query above. I also tried
to insert invalid data (negative lap time, missing parent rows, duplicates, invalid corner,
wrong parameter scope) and checked that each was refused.

## What I would do next

Automated tests, a backend API with filtering, a simple frontend, a tool to import the old
spreadsheets, and a containerised setup. The limitations I already know about are listed in
`DESIGN.md`.

## How I worked

I used an AI assistant (Claude) as a tutor while learning SQL for this assignment. I went
through each design step with it, ran and checked all of the code myself, and I can explain
the decisions above.