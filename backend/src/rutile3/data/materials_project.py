"""Server-only Materials Project reference acquisition; credentials never cached."""
from datetime import datetime, timezone
import hashlib
import json
from time import time

import requests

from rutile3.jobs.storage import read_json, write_json


class ReferenceUnavailable(ValueError):
    pass


_SUMMARY_FIELDS = "material_id,formula_pretty,composition,density,symmetry,energy_above_hull,deprecated"


def material_id_key(identifier):
    """Compare documented numeric and base-26 MP identifiers without changing the saved ID."""
    if not isinstance(identifier, str) or not identifier.startswith("mp-"):
        return identifier
    suffix = identifier[3:]
    if suffix.isascii() and suffix.isdecimal():
        return f"mp-{int(suffix)}"
    if not (suffix.isascii() and suffix.isalpha() and suffix.islower()):
        return identifier
    number = 0
    for letter in suffix:
        number = number * 26 + ord(letter) - ord("a")
    return f"mp-{number}"


def records_by_requested_id(documents, identifiers):
    requested = {identifier: material_id_key(identifier) for identifier in identifiers}
    matches = {}
    for document in documents:
        key = material_id_key(document.get("material_id"))
        matches[key] = None if key in matches else document
    return {identifier: matches[key] for identifier, key in requested.items() if key in matches}


def elasticity_records(client, identifiers, payloads):
    """Read bounded batches and reject ambiguous records independently of API order."""
    records = {}
    identifiers = sorted(set(identifiers))
    for start in range(0, len(identifiers), 100):
        batch = identifiers[start:start + 100]
        payload = client.elasticity(batch)
        payloads.append(payload)
        if payload.get("api_meta", {}).get("total_doc", 0) > len(payload["data"]):
            raise ReferenceUnavailable("Materials Project elasticity response was truncated.")
        records.update(records_by_requested_id(payload["data"], batch))
    return records


class MaterialsProject:
    def __init__(self, key, cache):
        self.key = key
        self.cache = cache
        self.session = requests.Session()

    def get(self, endpoint, params):
        identity = hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()
        path = self.cache / f"{identity}.json"
        if path.exists():
            try:
                cached = read_json(path)
                if 0 <= time() - cached["cached_at"] < 7 * 86400:
                    return cached["payload"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        try:
            response = self.session.get(f"https://api.materialsproject.org/materials/{endpoint}/",
                                       headers={"X-API-KEY": self.key}, params=params, timeout=(8, 25))
        except requests.RequestException:
            raise ReferenceUnavailable("Materials Project could not be reached.") from None
        if response.status_code in {401, 403}:
            raise ReferenceUnavailable("Materials Project rejected the configured credential or access permission.")
        if response.status_code == 429:
            raise ReferenceUnavailable("Materials Project rate limit reached. Try again later.")
        if not response.ok:
            raise ReferenceUnavailable(f"Materials Project returned HTTP {response.status_code}.")
        try:
            body = response.json()
            if not isinstance(body.get("data"), list):
                raise ValueError()
        except (ValueError, AttributeError):
            raise ReferenceUnavailable("Materials Project returned an invalid data response.") from None
        payload = {"data": body["data"], "api_meta": body.get("meta", {}),
                   "retrieved_at": datetime.now(timezone.utc).isoformat(), "endpoint": endpoint,
                   "query": params}
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            write_json(path, {"cached_at": time(), "payload": payload})
        except OSError:
            pass  # Read-only caches must not invalidate reference results.
        return payload

    def summary(self, elements):
        return self.get("summary", {"chemsys": "-".join(sorted(e.title() for e in elements)),
            "deprecated": False, "_limit": 1000, "_fields": _SUMMARY_FIELDS})

    def summary_by_ids(self, identifiers):
        return self.get("summary", {"material_ids": ",".join(sorted(identifiers)),
            "_limit": 1000, "_fields": _SUMMARY_FIELDS})

    def elastic_summary(self, systems, space_group):
        return self.get("summary", {
            "chemsys": ",".join(sorted("-".join(sorted(e.title() for e in system)) for system in systems)),
            "has_props": "elasticity", "spacegroup_number": space_group,
            "deprecated": False, "_limit": 1000, "_fields": _SUMMARY_FIELDS,
        })

    def elasticity(self, identifiers):
        return self.get("elasticity", {"material_ids": ",".join(sorted(identifiers)), "_limit": 1000,
            "_fields": "material_id,bulk_modulus,shear_modulus,elastic_tensor,deprecated"})
