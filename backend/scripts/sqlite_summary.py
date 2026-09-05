#!/usr/bin/env python3
"""
sqlite_summary.py 🗄️

Give it a SQLite DB path and it will print:
- All tables
- Column details (name, type, nullability, default, PK) for each table
- Row count per table
- First 5 rows of each table

Usage:
    python sqlite_summary.py /path/to/database.db
"""

import sqlite3
import sys
from pathlib import Path


def summarize_db(db_path: str, preview_rows: int = 5):
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"❌ File not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"\n📂 Database: {db_path}")
    print(f"📏 Size: {db_path.stat().st_size / 1024:.2f} KB")
    print("=" * 70)

    # Get all tables
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
    """)
    tables = [row["name"] for row in cursor.fetchall()]

    if not tables:
        print("⚠️ No tables found in this database.")
        conn.close()
        return

    print(f"📋 Found {len(tables)} table(s): {', '.join(tables)}\n")

    for table in tables:
        print("=" * 70)
        print(f"📊 TABLE: {table}")
        print("=" * 70)

        # Column details
        cursor.execute(f"PRAGMA table_info('{table}');")
        columns = cursor.fetchall()

        print("\n🧩 Columns:")
        print(f"  {'Name':<20} {'Type':<12} {'NotNull':<8} {'Default':<12} {'PK'}")
        print(f"  {'-'*20} {'-'*12} {'-'*8} {'-'*12} {'--'}")
        col_names = []
        for col in columns:
            col_names.append(col["name"])
            print(f"  {col['name']:<20} {col['type']:<12} "
                  f"{'YES' if col['notnull'] else 'NO':<8} "
                  f"{str(col['dflt_value']) if col['dflt_value'] is not None else '-':<12} "
                  f"{'✅' if col['pk'] else ''}")

        # Foreign keys (if any)
        cursor.execute(f"PRAGMA foreign_key_list('{table}');")
        fks = cursor.fetchall()
        if fks:
            print("\n🔗 Foreign Keys:")
            for fk in fks:
                print(f"  {fk['from']} → {fk['table']}({fk['to']})")

        # Row count
        cursor.execute(f"SELECT COUNT(*) as cnt FROM '{table}';")
        row_count = cursor.fetchone()["cnt"]
        print(f"\n🔢 Row count: {row_count}")

        # Latest N rows (by rowid, falls back to unordered for WITHOUT ROWID tables)
        print(f"\n👀 Latest {preview_rows} row(s):")
        try:
            cursor.execute(f"SELECT * FROM '{table}' ORDER BY rowid DESC LIMIT {preview_rows};")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # WITHOUT ROWID table — no rowid to sort by
            print("  ⚠️ Table has no rowid (WITHOUT ROWID) — showing unordered rows:")
            cursor.execute(f"SELECT * FROM '{table}' LIMIT {preview_rows};")
            rows = cursor.fetchall()

        if not rows:
            print("  (empty table)")
        else:
            for i, row in enumerate(rows, start=1):
                row_dict = {col: row[col] for col in col_names}
                print(f"  [{i}] {row_dict}")
        print()

    conn.close()
    print("=" * 70)
    print("✅ Done! Summary complete.\n")


if __name__ == "__main__":
    db_path_arg = "../src/data/inboxiq.db"
    preview_n = 5
    summarize_db(db_path_arg, preview_n)