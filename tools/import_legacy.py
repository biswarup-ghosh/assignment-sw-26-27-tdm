"""Import legacy spreadsheet data (exported as CSV) into the TDM database.

Usage, from the project folder:
    python3 tools/import_legacy.py data/legacy_sample.csv --vehicle RUP-EV-26 --dry-run
    python3 tools/import_legacy.py data/legacy_sample.csv --vehicle RUP-EV-26

See docs/IMPORT.md for the strategy and the expected file format.
"""
import argparse
import csv
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "tdm.db"

# Date formats found in the old spreadsheets. Day-first is assumed (15/09/2026 = 15 September).
DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"]

# Column headers that are accepted for each field (compared in lower case)
COLUMN_ALIASES = {
    "date":     ["date", "data"],
    "track":    ["track", "location", "pista"],
    "layout":   ["layout", "track layout", "event"],
    "driver":   ["driver", "pilota"],
    "run":      ["run", "run number", "run no"],
    "tyre_set": ["tyre set", "tire set", "set"],
    "compound": ["compound", "tyre compound", "mescola"],
    "ambient":  ["ambient temp", "ambient", "air temp"],
    "asphalt":  ["asphalt temp", "asphalt", "track temp"],
    "laps":     ["lap times", "laps", "times"],
}
REQUIRED = ["date", "track", "layout", "driver", "run"]


class FatalError(Exception):
    """The whole import cannot continue (wrong file, unknown vehicle...)."""


class RowError(Exception):
    """One row cannot be imported. The message says why."""


class AlreadyImported(Exception):
    """The row's run is already in the database."""


# ---------------------------------------------------------------------
# Cleaning: turn messy text into standard values (no database access)
# ---------------------------------------------------------------------
def clean_text(value):
    """Trim the text and collapse repeated spaces. None becomes an empty string."""
    return re.sub(r"\s+", " ", (value or "").strip())


def parse_date(text):
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            pass
    raise RowError(f"unreadable date '{text}'")


def parse_run_number(text):
    if not re.fullmatch(r"\d+", text) or int(text) < 1:
        raise RowError(f"invalid run number '{text}'")
    return int(text)


def parse_temp(text, name):
    """'22,5' -> 22.5, '30 °C' -> 30.0, '' -> None."""
    if text == "":
        return None
    cleaned = re.sub(r"\s*[°º]?\s*c$", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        raise RowError(f"unreadable {name} '{text}'") from None
    if not -30 <= value <= 90:
        raise RowError(f"{name} {value} is outside the plausible range")
    return value


def parse_lap_time(text):
    """'62.3' -> 62.3, '1:02,3' -> 62.3 (seconds)."""
    match = re.fullmatch(r"(?:(\d+):)?(\d+(?:[.,]\d+)?)", text.strip())
    if not match:
        raise RowError(f"unreadable lap time '{text}'")
    minutes = int(match.group(1) or 0)
    seconds = float(match.group(2).replace(",", "."))
    total = round(minutes * 60 + seconds, 3)
    if total <= 0:
        raise RowError(f"lap time '{text}' must be greater than zero")
    return total


def parse_laps(text):
    """Lap times are separated by semicolons: '62.3; 61.8; 1:02.0'."""
    parts = [part.strip() for part in text.split(";") if part.strip()]
    return [parse_lap_time(part) for part in parts]


def map_columns(header):
    """Find which spreadsheet column holds each field."""
    names = {clean_text(name).lower(): name for name in header if name}
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in names:
                mapping[field] = names[alias]
                break
    missing = [field for field in REQUIRED if field not in mapping]
    if missing:
        raise FatalError(
            f"missing required column(s): {', '.join(missing)}. Found: {', '.join(header)}")
    return mapping


def get_field(row, mapping, field):
    column = mapping.get(field)
    return clean_text(row.get(column)) if column else ""


# ---------------------------------------------------------------------
# Loading: find or create rows in the database
# ---------------------------------------------------------------------
def get_or_create(conn, select_sql, select_params, insert_sql, insert_params, kind, created):
    row = conn.execute(select_sql, select_params).fetchone()
    if row:
        return row[0]
    created.append(kind)
    return conn.execute(insert_sql, insert_params).lastrowid


def import_row(conn, vehicle_id, fields, created):
    # --- 1. clean and check every value (no database access yet) ---
    test_date = parse_date(fields["date"])
    run_number = parse_run_number(fields["run"])
    driver_name = fields["driver"].title()
    if not driver_name:
        raise RowError("driver is missing")
    ambient = parse_temp(fields["ambient"], "ambient temperature")
    asphalt = parse_temp(fields["asphalt"], "asphalt temperature")
    laps = parse_laps(fields["laps"])
    tyre_code = fields["tyre_set"].upper()
    compound_name = fields["compound"].title()

    # --- 2. reference data that must already exist ---
    season = conn.execute(
        "SELECT id FROM season WHERE ? BETWEEN start_date AND end_date", (test_date,)).fetchone()
    if season is None:
        raise RowError(f"no season covers the date {test_date}")

    location = conn.execute(
        "SELECT id FROM track_location WHERE lower(name) = lower(?)",
        (fields["track"],)).fetchone()
    if location is None:
        raise RowError(f"unknown track location '{fields['track']}'")

    layout = conn.execute(
        "SELECT id FROM track_layout WHERE track_location_id = ? AND lower(name) = lower(?)",
        (location[0], fields["layout"])).fetchone()
    if layout is None:
        raise RowError(f"unknown track layout '{fields['layout']}'")

    # --- 3. rows that are created when they are new ---
    driver_id = get_or_create(
        conn,
        "SELECT id FROM driver WHERE lower(full_name) = lower(?)", (driver_name,),
        "INSERT INTO driver (full_name) VALUES (?)", (driver_name,),
        "driver", created)

    tyre_set_id = None
    if tyre_code:
        existing = conn.execute(
            "SELECT tyre_set.id, tyre_compound.name FROM tyre_set "
            "JOIN tyre_compound ON tyre_compound.id = tyre_set.compound_id "
            "WHERE tyre_set.code = ?", (tyre_code,)).fetchone()
        if existing:
            if compound_name and existing[1].lower() != compound_name.lower():
                raise RowError(
                    f"tyre set {tyre_code} is a {existing[1]} set, but the row says {compound_name}")
            tyre_set_id = existing[0]
        else:
            if not compound_name:
                raise RowError(f"new tyre set {tyre_code} needs a compound")
            compound_id = get_or_create(
                conn,
                "SELECT id FROM tyre_compound WHERE lower(name) = lower(?)", (compound_name,),
                "INSERT INTO tyre_compound (name, supplier) VALUES (?, 'unknown')", (compound_name,),
                "tyre compound", created)
            created.append("tyre set")
            tyre_set_id = conn.execute(
                "INSERT INTO tyre_set (compound_id, code) VALUES (?, ?)",
                (compound_id, tyre_code)).lastrowid

    test_id = get_or_create(
        conn,
        "SELECT id FROM test WHERE test_date = ? AND vehicle_id = ? AND track_location_id = ?",
        (test_date, vehicle_id, location[0]),
        "INSERT INTO test (season_id, vehicle_id, track_location_id, test_date, status) "
        "VALUES (?, ?, ?, ?, 'done')",
        (season[0], vehicle_id, location[0], test_date),
        "test", created)

    if conn.execute("SELECT 1 FROM run WHERE test_id = ? AND run_number = ?",
                    (test_id, run_number)).fetchone():
        raise AlreadyImported(f"run {run_number} on {test_date} already exists")

    # --- 4. the run and its laps ---
    run_id = conn.execute(
        "INSERT INTO run (test_id, run_number, driver_id, track_layout_id, tyre_set_id, "
        "ambient_temp_c, asphalt_temp_c, completed_laps) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (test_id, run_number, driver_id, layout[0], tyre_set_id,
         ambient, asphalt, len(laps))).lastrowid
    conn.executemany(
        "INSERT INTO lap (run_id, lap_number, lap_time_s) VALUES (?, ?, ?)",
        [(run_id, number, seconds) for number, seconds in enumerate(laps, start=1)])
    created.append("run")
    created.extend(["lap"] * len(laps))


def run_import(conn, csv_path, vehicle_name, delimiter=",", dry_run=False):
    """Import a CSV file. The connection must be in autocommit mode (isolation_level = None)."""
    vehicle = conn.execute(
        "SELECT id FROM vehicle WHERE lower(name) = lower(?)", (vehicle_name,)).fetchone()
    if vehicle is None:
        raise FatalError(f"vehicle '{vehicle_name}' does not exist in the database")

    result = {"imported": 0, "skipped": 0, "rejected": [], "created": Counter(), "fieldnames": []}

    with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=delimiter)
        if not reader.fieldnames:
            raise FatalError("the file is empty")
        result["fieldnames"] = list(reader.fieldnames)
        mapping = map_columns(reader.fieldnames)

        conn.execute("BEGIN")
        try:
            for row in reader:
                line = reader.line_num
                fields = {name: get_field(row, mapping, name) for name in COLUMN_ALIASES}
                if not any(fields.values()):
                    continue                      # completely empty row
                created = []
                conn.execute("SAVEPOINT one_row")
                try:
                    import_row(conn, vehicle[0], fields, created)
                except AlreadyImported:
                    conn.execute("ROLLBACK TO one_row")
                    result["skipped"] += 1
                except (RowError, sqlite3.IntegrityError) as error:
                    conn.execute("ROLLBACK TO one_row")
                    result["rejected"].append((line, row, str(error)))
                else:
                    result["imported"] += 1
                    result["created"].update(created)
                finally:
                    conn.execute("RELEASE one_row")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("ROLLBACK" if dry_run else "COMMIT")
    return result


def main():
    parser = argparse.ArgumentParser(description="Import legacy CSV spreadsheets into the TDM database.")
    parser.add_argument("csv_file", help="the CSV file to import")
    parser.add_argument("--vehicle", required=True, help="vehicle name, e.g. RUP-EV-26")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="database file (default: tdm.db)")
    parser.add_argument("--delimiter", default=",", help="CSV separator (use ';' for Italian Excel)")
    parser.add_argument("--dry-run", action="store_true", help="check everything but save nothing")
    parser.add_argument("--rejects", default="import_rejects.csv", help="where to write rejected rows")
    args = parser.parse_args()

    if not Path(args.db).exists():
        sys.exit("Database not found. Run: python3 create_db.py")

    conn = sqlite3.connect(args.db)
    conn.isolation_level = None            # we control the transaction ourselves
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        result = run_import(conn, args.csv_file, args.vehicle, args.delimiter, args.dry_run)
    except (FatalError, OSError) as error:
        sys.exit(f"Import stopped: {error}")
    finally:
        conn.close()

    print("DRY RUN: nothing was saved." if args.dry_run else "Import finished and saved.")
    print(f"  imported rows                 : {result['imported']}")
    print(f"  already in database (skipped) : {result['skipped']}")
    print(f"  rejected rows                 : {len(result['rejected'])}")
    if result["created"]:
        parts = [f"{count} {kind}" for kind, count in sorted(result["created"].items())]
        print(("  would create: " if args.dry_run else "  created: ") + ", ".join(parts))

    if result["rejected"]:
        print("Rejected rows:")
        for line, _, reason in result["rejected"]:
            print(f"  line {line}: {reason}")
        with open(args.rejects, "w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=result["fieldnames"] + ["reject_reason"],
                                    extrasaction="ignore")
            writer.writeheader()
            for line, row, reason in result["rejected"]:
                writer.writerow({**row, "reject_reason": reason})
        print(f"Rejected rows were written to {args.rejects}")


if __name__ == "__main__":
    main()