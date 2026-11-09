"""Server-only Materials Project reference acquisition; credentials never cached."""
from datetime import datetime, timezone
import hashlib
import json
from time import time

import requests

from rutile3.jobs.storage import read_json, write_json


class ReferenceUnavailable(ValueError):
    pass


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
            "deprecated": False, "_limit": 1000,
            "_fields": "material_id,formula_pretty,composition,density,symmetry,energy_above_hull,deprecated"})

    def elasticity(self, identifiers):
        return self.get("elasticity", {"material_ids": ",".join(sorted(identifiers)), "_limit": 1000,
            "_fields": "material_id,bulk_modulus,shear_modulus,elastic_tensor,deprecated"})
