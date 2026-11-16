# Rutile MP lookup client

`scripts/rutile_mp_client/` contains the lookup client and its CLI.
The [translation generator](../mp_translation/README.md) uses this client.
Install the project in its virtual environment using the [setup guide](../../README.md#setup-and-run).
Run these examples from the repository root with a local `.env` containing
`MP_API_KEY`.

```powershell
.venv/Scripts/python.exe scripts/rutile_mp_client/mp_properties.py --env-file .env --formula Re2Zr --spacegroup 194
.venv/Scripts/python.exe scripts/rutile_mp_client/mp_properties.py --env-file .env --chemsys Re-Zr
.venv/Scripts/python.exe scripts/rutile_mp_client/mp_properties.py --env-file .env mp-1374 mp-12109
```

For direct imports, run Python with `scripts/rutile_mp_client/` on its import path.

```python
from mp_client import MPClient, safe_search
client = MPClient(retries=3)
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
- Run the offline mocked tests from the repository root with
  `.venv/Scripts/python.exe -m unittest discover -s scripts/rutile_mp_client -p test_mp_client.py`.
  The CLI examples above require live API access.
