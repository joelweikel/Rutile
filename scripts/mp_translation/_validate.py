import sys, re
sys.path.insert(0, r"Y:\Rutile3\scripts\mp_translation")
from parse_tdb import parse_all
from pathlib import Path

files = [
    Path("data/matcalc/al/mc_al_v2037.tdb"),
    Path("data/matcalc/fe/mc_fe_v2062.tdb"),
    Path("data/matcalc/ni/mc_ni_v2036.tdb"),
]
recs = parse_all(files)
print(f"total: {len(recs)}")

# 1. Every record has a non-empty nominal formula
no_formula = [r for r in recs if not r.nominal_formula]
print(f"records with empty formula: {len(no_formula)}")

# 2. Element symbols are valid title-case (1-2 letters)
def formula_ok(f):
    # formula is a sequence of <Symbol><number?> where Symbol is 1-2 letters
    # and the number is optional (implied 1), integer or decimal.
    return bool(re.fullmatch(r"([A-Z][a-z]?\d*\.?\d*)+", f))
bad = [r for r in recs if not formula_ok(r.nominal_formula)]
print(f"records with malformed formula: {len(bad)}")
if bad[:5]:
    for r in bad[:5]:
        print(f"   BAD: {r.label} -> {r.nominal_formula}")

# 3. Space group coverage
with_sg = [r for r in recs if r.space_group_number is not None]
no_sg = [r for r in recs if r.space_group_number is None]
print(f"with space group number: {len(with_sg)}, without: {len(no_sg)}")

# 4. Distribution of space group numbers
from collections import Counter
print("space group number counts:", dict(Counter(r.space_group_number for r in with_sg)))

# 5. Ordering character distribution
print("ordering:", dict(Counter(r.ordering_character for r in recs)))

# 6. Solid vs not
print("solid:", dict(Counter(r.is_solid for r in recs))
      )
non_solid = [r.label for r in recs if not r.is_solid]
print(f"non-solid labels: {non_solid}")

# 7. Spot-check known phases
for label in ("BCC_A2", "FCC_A1", "HCP_A3", "MNB4", "NI3SIL", "LIQUID"):
    m = [r for r in recs if r.label == label]
    if m:
        r = m[0]
        print(f"  {label:10s} formula={r.nominal_formula:12s} sg={r.space_group_symbol} #{r.space_group_number} order={r.ordering_character} solid={r.is_solid}")
