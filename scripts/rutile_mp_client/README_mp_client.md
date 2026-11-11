# Rutile MP lookup client

Put `mp_client.py` and `mp_properties.py` together in `Y:\Rutile3\scripts\`.
If your translation script currently imports from `mp_lookup.py`, update those imports to `mp_client` or adapt the old CLI. This package does **not** overwrite your existing `mp_lookup.py`, which was not attached.

Install: `python -m pip install -U mp-api`

Examples in PowerShell:

```powershell
python Y:\Rutile3\scripts\mp_properties.py --env-file Y:\Rutile3\.env --formula Re2Zr --spacegroup 194
python Y:\Rutile3\scripts\mp_properties.py --env-file Y:\Rutile3\.env --formula Re24Zr5 --spacegroup 217
python Y:\Rutile3\scripts\mp_properties.py --env-file Y:\Rutile3\.env --formula Re25Zr21 --spacegroup 167
python Y:\Rutile3\scripts\mp_properties.py --env-file Y:\Rutile3\.env --chemsys Re-Zr
python Y:\Rutile3\scripts\mp_properties.py --env-file Y:\Rutile3\.env mp-1374 mp-12109
```

Python API:

```python
from mp_client import MPClient, safe_search
client = MPClient(cache_dir=r'Y:\Rutile3\.cache\mp', retries=3)
result = safe_search(client.find_formula, 'Re2Zr', spacegroup=194)
if result['search_status'] == 'complete':
    candidates = result['records']
elif result['search_status'] == 'no_match':
    # Search completed successfully; no exact matches.
    pass
else:
    # An outage, auth problem, or other error. Do not record data_pending.
    raise RuntimeError(result)
```

- `retries=3` means 1 initial attempt + 3 retries, exponential backoff with jitter.
- Successful results and successful empty results are cached by full query, fields, schema version, and **currently served REST database version**. Failures are never cached.
- Offline cache use is deliberately disabled because the API version cannot be checked; this avoids silent stale results.
- Results are fully paged by `mp-api` with `num_chunks=None`.
- `formula` lookup performs a server query and an exact *reduced-composition* comparison locally. Polymorphs are retained; space-group filtering does not imply matching Wyckoff positions, prototype, ordering, or Pearson symbol. Validate those separately.
- Null hardness means not provided; *no automatic hardness estimates* are fabricated.
- `bulk_modulus_GPa` / `shear_modulus_GPa` preserve API dictionaries (Voigt, Reuss, VRH); use `bulk_modulus_vrh_GPa` and `shear_modulus_vrh_GPa` for numbers.
- `youngs_modulus_vrh_derived_GPa` is an isotropic aggregate estimate, not a direct MP field.
- Do not commit `.env` or cache containing proprietary query details.
- Test suite uses mocks and does not contact MP: `python -m unittest -v test_mp_client.py`.

A real MP API test is still needed in the user's environment because that API key and the `mp-api` package are not available here.
