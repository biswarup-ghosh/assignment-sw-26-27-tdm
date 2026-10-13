import os
import sqlite3

if os.path.exists("tdm.db"):
    os.remove("tdm.db")

conn = sqlite3.connect("tdm.db")
conn.execute("PRAGMA foreign_keys = ON")

for path in ["db/schema.sql", "db/seed.sql"]:
    with open(path) as f:
        conn.executescript(f.read())

conn.commit()
conn.close()