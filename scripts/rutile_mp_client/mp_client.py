"""Reliable Materials Project summary client for Rutile translation.

Requires: pip install mp-api (and its pymatgen dependency).
Does not load .env implicitly; use --env-file or load it in your application.
Failures raise typed MPClientError subclasses; an empty list means a successful search.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
import re
import socket
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Callable

FIELDS = [
    'material_id', 'formula_pretty', 'composition', 'symmetry', 'structure',
    'volume', 'density', 'density_atomic', 'bulk_modulus', 'shear_modulus',
    'universal_anisotropy', 'homogeneous_poisson', 'energy_above_hull',
    'energy_per_atom', 'formation_energy_per_atom', 'is_stable', 'efermi',
    'weighted_work_function',
]

class MPClientError(Exception):
    status = 'error'
    retryable = False

class MPAuthError(MPClientError):
    status = 'auth_error'

class MPNetworkError(MPClientError):
    status = 'network_error'
    retryable = True

class MPRateLimitError(MPClientError):
    status = 'rate_limit_error'
    retryable = True

class MPServerError(MPClientError):
    status = 'server_error'
    retryable = True

class MPQueryError(MPClientError):
    status = 'query_error'

class MPConfigurationError(MPClientError):
    status = 'configuration_error'

class MPUnexpectedError(MPClientError):
    status = 'unexpected_error'


def classify_error(exc: Exception) -> MPClientError:
    """Classify API/HTTP errors, including wrapped exceptions and responses."""
    if isinstance(exc, MPClientError):
        return exc
    chain = []
    seen = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        chain.append(cur)
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    for e in chain:
        code = getattr(getattr(e, 'response', None), 'status_code', None)
        code = code or getattr(e, 'status_code', None)
        if code in (401, 403):
            return MPAuthError(str(exc))
        if code == 429:
            return MPRateLimitError(str(exc))
        if isinstance(code, int) and 500 <= code <= 599:
            return MPServerError(str(exc))
        if isinstance(code, int) and 400 <= code <= 499:
            return MPQueryError(str(exc))
    if any(isinstance(e, (socket.timeout, TimeoutError, ConnectionError, socket.gaierror, OSError)) for e in chain):
        # Not every OSError is a network error, but these only arise during API calls.
        return MPNetworkError(str(exc))
    names = ' '.join(type(e).__name__.lower() for e in chain)
    msg = ' '.join(str(e).lower() for e in chain)
    if any(t in names for t in ('timeout', 'connectionerror', 'dns', 'connecterror', 'proxyerror')) or any(t in msg for t in ('name resolution', 'temporary failure in name resolution', 'failed to resolve', 'connection refused', 'timed out')):
        return MPNetworkError(str(exc))
    if '429' in msg or 'rate limit' in msg or 'too many requests' in msg:
        return MPRateLimitError(str(exc))
    if any(t in msg for t in ('401', '403', 'invalid api key', 'api key is invalid', 'unauthorized', 'forbidden')):
        return MPAuthError(str(exc))
    if re.search(r'\b5\d\d\b', msg) or 'internal server error' in msg or 'bad gateway' in msg:
        return MPServerError(str(exc))
    if re.search(r'\b4\d\d\b', msg) or 'invalid field' in msg:
        return MPQueryError(str(exc))
    return MPUnexpectedError(f'{type(exc).__name__}: {exc}')


def load_env_file(path: str | Path) -> None:
    """Load a trusted local .env, without overwriting explicitly configured env vars."""
    p = Path(path)
    for line in p.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', k):
            continue
        v = v.strip()
        if v[:1] in ('"', "'") and v[-1:] == v[:1]:
            v = v[1:-1]
        else:
            v = v.split(' #', 1)[0].strip()
        os.environ.setdefault(k, v)


_FORMULA_TOKEN = re.compile(r'([A-Z][a-z]?)(\d+(?:\.\d+)?)?')


def composition_key(formula: str) -> tuple[tuple[str, int], ...]:
    """Canonical reduced formula, order-insensitive, without parentheses/variables."""
    if not isinstance(formula, str) or not formula.strip():
        raise ValueError('Formula is empty')
    formula = formula.replace(' ', '')
    pos = 0
    composition: dict[str, Fraction] = {}
    while pos < len(formula):
        m = _FORMULA_TOKEN.match(formula, pos)
        if not m:
            raise ValueError(f'Unsupported formula syntax: {formula!r}')
        try:
            n = Fraction(Decimal(m.group(2))) if m.group(2) else Fraction(1)
        except InvalidOperation as e:
            raise ValueError(f'Invalid formula: {formula!r}') from e
        if n <= 0:
            raise ValueError('Nonpositive stoichiometry')
        composition[m.group(1)] = composition.get(m.group(1), Fraction(0)) + n
        pos = m.end()
    from math import gcd, lcm
    denominator = lcm(*(v.denominator for v in composition.values()))
    counts = {k: int(v * denominator) for k, v in composition.items()}
    divisor = 0
    for n in counts.values():
        divisor = gcd(divisor, n)
    return tuple(sorted((k, n // divisor) for k, n in counts.items()))


def _get(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, float, int, bool)):
        return value
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if hasattr(value, 'as_dict'):
        return value.as_dict()
    if isinstance(value, dict):
        return {str(k): _scalar(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scalar(v) for v in value]
    return str(value)


def to_props(doc: Any) -> dict[str, Any]:
    sym = _get(doc, 'symmetry')
    struct = _get(doc, 'structure')
    bulk = _get(doc, 'bulk_modulus')
    shear = _get(doc, 'shear_modulus')
    # MP bulk_modulus and shear_modulus may be {voigt, reuss, vrh} mappings,
    # NOT numeric quantities. Keep them intact; expose VRH separately.
    k = _get(bulk, 'vrh')
    g = _get(shear, 'vrh')
    young = 9*k*g/(3*k+g) if isinstance(k,(int,float)) and isinstance(g,(int,float)) and 3*k+g else None
    return {
        'mp_id': str(_get(doc,'material_id')),
        'formula': _get(doc,'formula_pretty'),
        'composition': str(_get(doc,'composition')) if _get(doc,'composition') is not None else None,
        'spacegroup': _get(sym,'symbol'),
        'spacegroup_number': _get(sym,'number'),
        'sites': len(struct) if struct is not None else None,
        'volume_A3': _get(doc,'volume'),
        'density_g_per_cm3': _get(doc,'density'),
        'density_atomic_g_per_cm3': _get(doc,'density_atomic'),
        'bulk_modulus_GPa': _scalar(bulk),
        'shear_modulus_GPa': _scalar(shear),
        'bulk_modulus_vrh_GPa': k,
        'shear_modulus_vrh_GPa': g,
        'youngs_modulus_vrh_derived_GPa': young,
        'universal_anisotropy': _get(doc,'universal_anisotropy'),
        'homogeneous_poisson': _get(doc,'homogeneous_poisson'),
        'energy_above_hull_eV_per_atom': _get(doc,'energy_above_hull'),
        'energy_per_atom_eV': _get(doc,'energy_per_atom'),
        'formation_energy_per_atom_eV': _get(doc,'formation_energy_per_atom'),
        'is_stable': _get(doc,'is_stable'),
        'efermi_eV': _get(doc,'efermi'),
        'work_function_eV': _get(doc,'weighted_work_function'),
        'elastic_constants_C': None, 'debye_temperature_K': None,
        'strength': None, 'hardness': None,
    }


@dataclass
class SearchResult:
    search_status: str  # complete | no_match; errors always raise
    records: list[dict[str, Any]]
    db_version: str
    from_cache: bool = False
    query: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {'search_status': self.search_status, 'records': self.records,
                'db_version': self.db_version, 'from_cache': self.from_cache,
                'query': self.query}


class MPClient:
    def __init__(self, api_key: str | None = None, *, retries: int = 3,
                 cache_dir: str | Path | None = None, use_cache: bool = True,
                 chunk_size: int = 500, backoff_seconds: float = 1.0,
                 rester_factory: Callable[..., Any] | None = None):
        self.api_key = api_key or os.getenv('MP_API_KEY')
        if not self.api_key:
            raise MPConfigurationError('MP_API_KEY is unset; provide --env-file or set environment variable')
        if retries < 0 or chunk_size < 1:
            raise ValueError('retries must be >= 0 and chunk_size >= 1')
        self.retries = retries  # additional retries after first attempt
        self.cache_dir = Path(cache_dir) if cache_dir is not None else Path.cwd() / '.cache' / 'materials_project'
        self.use_cache = use_cache
        self.chunk_size = chunk_size
        self.backoff_seconds = backoff_seconds
        self._factory = rester_factory

    def _connect(self):
        if self._factory is None:
            try:
                from mp_api.client import MPRester
            except ImportError as exc:
                raise MPConfigurationError('mp-api missing; run pip install mp-api') from exc
            self._factory = MPRester
        return self._factory(self.api_key)

    def _run(self, query: dict[str, Any]) -> SearchResult:
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                with self._connect() as mpr:
                    # REST results reflect current_db_version, not an S3 snapshot version.
                    version = getattr(mpr, 'current_db_version', None) or getattr(mpr, 'db_version', None)
                    if not version:
                        raise MPConfigurationError('MP did not report a database version; refusing unversioned results')
                    cache_key = {'schema': 2, 'query': query, 'db_version': str(version), 'fields': FIELDS}
                    digest = hashlib.sha256(json.dumps(cache_key,sort_keys=True).encode()).hexdigest()
                    target = self.cache_dir / (digest + '.json')
                    if self.use_cache and target.is_file():
                        try:
                            data = json.loads(target.read_text(encoding='utf-8'))
                            if data.get('cache_key') == cache_key and data.get('search_status') in ('complete','no_match'):
                                return SearchResult(data['search_status'], data['records'], str(version), True, query)
                        except (OSError, ValueError, KeyError):
                            pass  # corrupted cache: do live lookup
                    docs = mpr.materials.summary.search(fields=FIELDS, chunk_size=self.chunk_size,
                                                        num_chunks=None, **query)
                    records = [to_props(doc) for doc in docs]
                    records.sort(key=lambda r: r['mp_id'])
                    status = 'complete' if records else 'no_match'
                    result = SearchResult(status, records, str(version), False, query)
                    if self.use_cache:
                        self.cache_dir.mkdir(parents=True, exist_ok=True)
                        tmp = target.with_suffix('.tmp.' + str(os.getpid()))
                        try:
                            tmp.write_text(json.dumps({'cache_key': cache_key, **result.as_dict()}, default=str), encoding='utf-8')
                            os.replace(tmp, target)
                        finally:
                            tmp.unlink(missing_ok=True)
                    return result
            except Exception as exc:
                mapped = classify_error(exc)
                if not mapped.retryable or attempt == self.retries:
                    raise mapped from exc
                last_error = mapped
                time.sleep(self.backoff_seconds * (2 ** attempt) + random.uniform(0, 0.25))
        raise last_error  # pragma: no cover

    def _run_raw(self, query: dict[str, Any]) -> list[Any]:
        """Make the API call and return the raw docs (``structure`` kept as a
        ``pymatgen.core.Structure``), reusing the connection and retry logic.
        """
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                with self._connect() as mpr:
                    version = getattr(mpr, 'current_db_version', None) or getattr(mpr, 'db_version', None)
                    if not version:
                        raise MPConfigurationError('MP did not report a database version; refusing unversioned results')
                    return list(mpr.materials.summary.search(
                        fields=FIELDS, chunk_size=self.chunk_size, num_chunks=None, **query))
            except Exception as exc:
                mapped = classify_error(exc)
                if not mapped.retryable or attempt == self.retries:
                    raise mapped from exc
                last_error = mapped
                time.sleep(self.backoff_seconds * (2 ** attempt) + random.uniform(0, 0.25))
        raise last_error  # pragma: no cover

    def get_ids(self, ids: list[str] | tuple[str,...]) -> SearchResult:
        ids = sorted(set(ids))
        if not ids:
            raise MPQueryError('Specify at least one material ID')
        return self._run({'material_ids': ids})

    def get_structures(self, material_ids: list[str] | tuple[str, ...]) -> list[Any]:
        """Fetch raw docs (``structure`` kept as a ``pymatgen.core.Structure``)
        for the given material IDs. Reuses the connection and retry logic.
        """
        ids = sorted(set(material_ids))
        if not ids:
            raise MPQueryError('Specify at least one material ID')
        return self._run_raw({'material_ids': ids})

    def scan_chemsys(self, chemsys: str, spacegroup: int | None = None) -> SearchResult:
        elements = chemsys.split('-')
        if not elements or any(not re.fullmatch(r'[A-Z][a-z]?', e) for e in elements):
            raise MPQueryError(f'Invalid chemical system {chemsys!r}')
        query: dict[str, Any] = {'chemsys': '-'.join(sorted(set(elements)))}
        if spacegroup is not None:
            if not 1 <= spacegroup <= 230:
                raise MPQueryError('Spacegroup must be 1-230')
            query['spacegroup_number'] = int(spacegroup)
        return self._run(query)

    def find_formula(self, formula: str, *, spacegroup: int | None = None,
                     chemsys: str | None = None) -> SearchResult:
        key = composition_key(formula)
        elements = '-'.join(k for k, _ in key)
        if chemsys is not None and sorted(chemsys.split('-')) != sorted(elements.split('-')):
            raise MPQueryError('Formula and chemsys elements do not agree')
        query = {'chemsys': elements, 'formula': formula}
        # Apply spacegroup locally in addition to API filtering so the returned
        # query result cannot be misread as structural equivalence.
        if spacegroup is not None:
            if not 1 <= int(spacegroup) <= 230:
                raise MPQueryError('Spacegroup must be 1-230')
            query['spacegroup_number'] = int(spacegroup)
        result = self._run(query)
        matches = []
        for r in result.records:
            if not r.get('formula'):
                continue
            try:
                rkey = composition_key(r['formula'])
            except ValueError:
                # MP formula with unsupported syntax (e.g. parentheses); the
                # candidate cannot be compared to the query formula, so skip it.
                continue
            if rkey == key and (spacegroup is None or r.get('spacegroup_number') == int(spacegroup)):
                matches.append(r)
        return SearchResult('complete' if matches else 'no_match', matches,
                            result.db_version, result.from_cache, query)


def safe_search(method: Callable[...,SearchResult], *args, **kwargs) -> dict[str,Any]:
    """Convenience for persistence: NEVER maps an error to data_pending."""
    try:
        return method(*args, **kwargs).as_dict()
    except MPClientError as exc:
        return {'search_status': exc.status, 'records': [], 'error_type': type(exc).__name__,
                'error': str(exc), 'db_version': None, 'from_cache': False}
