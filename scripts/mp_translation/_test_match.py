"""Test the matching layer against the Re-Zr TDB (known answers)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, r"Y:\Rutile3\scripts\mp_translation")
sys.path.insert(0, r"Y:\Rutile3\scripts\rutile_mp_client")

from parse_tdb import parse_tdb
from mp_client import MPClient, load_env_file
from mp_translation import match_model

# Load the API key.
load_env_file(Path("Y:/Rutile3/.env"))
client = MPClient()

tdb = Path("Y:/ThermodynamicDatabases/Useful/Binary/ReZr/ReZr-23Che.tdb")
records = parse_tdb(tdb)
print(f"Parsed {len(records)} models from Re-Zr TDB\n")
for rec in records:
    print(f"DBG: {rec.label!r} is_solid={rec.is_solid} formula={rec.nominal_formula!r}")
    result = match_model(rec, client)
    cands = ", ".join(c.mp_id for c in result.candidates) or "-"
    print(f"  {rec.label:14s} {rec.nominal_formula:12s} sg={str(rec.space_group_number):>5s} "
          f"-> {result.status:14s} [{cands}]")
    if result.notes:
        print(f"  {'':14s} notes: {result.notes}")
