# Importing the legacy spreadsheets

## Problem

The historical data lives in manually maintained spreadsheets. The same information is written
in different ways (dates, decimal commas, units typed into cells, capitalisation, lap times as
`62.3` or `1:02.3`), cells are empty, and some rows are impossible (31 February, negative times).
The database refuses invalid data by design, so the data has to be cleaned before it is loaded.

## Strategy

1. **Export** each sheet as CSV (UTF-8). The source file is never modified.
2. **Read** the rows. Columns are matched by name, not by position, so extra columns and a
   different order are fine.
3. **Clean** each value into the standard form: ISO dates, numbers with a dot, no units, trimmed
   names, lap times in seconds.
4. **Validate** the row. A row that cannot be understood is rejected, never guessed.
5. **Load** it inside a transaction. Every row has its own savepoint, so a rejected row leaves
   nothing behind and the other rows are not affected.
6. **Report** what was imported, skipped and rejected. Rejected rows are written to
   `import_rejects.csv` with the reason, so they can be fixed in the spreadsheet and imported again.

## Rules

- **Reference data is not invented.** Track locations and layouts need verified lengths, so an
  unknown one rejects the row. Drivers, tyre sets and compounds are created when they are new.
  A tyre set that already exists with a different compound rejects the row.
- **The season comes from the date.** A date outside every season is rejected.
- **Tests are created per date, location and vehicle** (status `done`).
- **Safe to run twice.** A run that already exists (same test and run number) is skipped.
- **Dry run.** `--dry-run` does all the work and saves nothing.
- **Names are matched without regard to capitals**, after removing extra spaces.

## File format (one row per run)

| Column | Required | Example |
|---|---|---|
| Date | yes | `15/09/2026`, `2026-09-15`, `15-09-2026`, `15.09.2026`, `15 Sep 2026` |
| Track | yes | `Test Area Padova` |
| Layout | yes | `Autocross A` |
| Driver | yes | `marco rossi` |
| Run | yes | `1` |
| Tyre set | no | `SET-001` |
| Compound | no (needed for a new set) | `Soft` |
| Ambient temp | no | `22,5` or `22.5 °C` |
| Asphalt temp | no | `30 °C` |
| Lap times | no | `62.3; 1:01,5; 1:02.0` (separated by `;`) |

Dates are read day-first, so `03/04/2026` is 3 April.

## Usage

```
bash tdm.sh import-dry     # check the sample file, save nothing
bash tdm.sh import         # import the sample file
```

Or directly: `python3 tools/import_legacy.py FILE.csv --vehicle RUP-EV-26 [--dry-run]`.
Use `--delimiter ";"` for CSV files exported by Italian versions of Excel. A deliberately messy
sample file is in `data/legacy_sample.csv`, and the importer is covered by `tests/test_import.py`.

## Limitations

- Only runs, laps, drivers, tyre sets and compounds are imported. Setups, measurements and files
  would need their own sheets and mappings.
- One vehicle per import (given with `--vehicle`), because the old sheets do not contain it.
- Names are not matched by similarity: "M. Rossi" would become a new driver, so the report should
  be read before saving. A table of known aliases would be the next improvement.
- Only CSV is supported, not `.xlsx` directly.
- Old plans are not reconstructed, so imported runs have no planned run.