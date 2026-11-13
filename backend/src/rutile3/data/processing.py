"""Explicit MatCalc family companions; no ranking or assessment concatenation."""
from pathlib import Path
import os
import re

from rutile3.data.catalog import checksum


FAMILY_SOURCES = {
    "AL": ("mc_al_v2037.tdb", "mc_al_v2008.ddb"),
    "FE": ("mc_fe_v2062.tdb", "mc_fe_v2016.ddb"),
    "NI": ("mc_ni_v2036.tdb", "mc_ni_v2012.ddb"),
}
# Declared element sets for these exact versions, used if external files are
# unavailable. When available, read the ELEMENT declarations from the source.
FAMILY_ELEMENTS = {
    "AL": "AL CR CU FE MG MN NI SC SI TI ZN ZR".split(),
    "FE": "AL B C CO CR CU FE H HF LA MN MO N NB NI O P PD S SI TA TI V W Y".split(),
    "NI": "AL B C CO CR CU FE HF LA MN MO N NB NI O S SI TI V W Y ZR".split(),
}
# The steel phase policy was checked against these exact MatCalc Fe 2.062 bytes.
STEEL_SOURCE_SHA256 = "aa02077eac3f602dd7479cbeafb09b450e282716752b3ae2b1fc3a57d9c64865"


def validate_phase_policy_source(request, source_sha256):
    if request.phase_policy == "fe_cementite" and source_sha256 != STEEL_SOURCE_SHA256:
        raise ValueError("Fe–Fe₃C equilibrium requires the bundled MatCalc Fe 2.062 assessment.")


def declared_elements(raw):
    content = raw.decode("utf-8-sig", errors="replace")
    content = "\n".join(line.split("$")[0] for line in content.splitlines())
    return sorted(set(re.findall(r"(?im)^\s*ELEMENT\s+([A-Z]{1,2})\s", content)) - {"VA"})


def find_companion(root, filename):
    # Restrict to the named companion; never silently use an older assessment.
    matches = sorted(Path(root).rglob(filename)) if Path(root).is_dir() else []
    if not matches:
        return None
    contents = {checksum(path.read_bytes()) for path in matches}
    if len(contents) != 1:
        raise ValueError(f"Multiple different {filename} files exist. Import a specific TDB instead.")
    return matches[0]


def sources(root):
    result = []
    for family, (thermodynamic, mobility) in FAMILY_SOURCES.items():
        path = find_companion(root, thermodynamic)
        diffusion = find_companion(root, mobility)
        raw = path.read_bytes() if path else None
        result.append({"family": family, "thermodynamic": thermodynamic, "mobility": mobility,
                       "available": path is not None, "mobility_available": diffusion is not None,
                       "elements": declared_elements(raw) if raw is not None else FAMILY_ELEMENTS[family],
                       "steel_equilibrium_available": family == "FE" and raw is not None and checksum(raw) == STEEL_SOURCE_SHA256,
                       "element_list_source": "source declarations" if path else "version manifest; source unavailable",
                       "assessment_coverage": "unverified"})
    return result


def resolve_sources(catalog, request):
    if request.database_id:
        metadata = catalog.inspect(request.database_id)
        path, raw = catalog.verified_source(metadata)
        # A manually selected assessment is not automatically compatible with
        # the MatCalc companion, even if phase names happen to match.
        return path, raw, None
    thermodynamic, mobility = FAMILY_SOURCES[request.family]
    path = find_companion(catalog.source_root, thermodynamic)
    if path is None:
        raise ValueError(f"{thermodynamic} is unavailable. Import a thermodynamic TDB or configure RUTILE_DATABASE_ROOT.")
    diffusion = find_companion(catalog.source_root, mobility)
    companion = None if diffusion is None else {"name": diffusion.name, "raw": diffusion.read_bytes()}
    return path, path.read_bytes(), companion


def physical_source(catalog):
    configured = os.environ.get("RUTILE_PHYSICAL_DATABASE")
    path = Path(configured) if configured else find_companion(catalog.source_root, "physical_data.pdb")
    if path is None or not path.is_file():
        return None
    description = path.parent / "DESCRIPTION.md"
    return {"name": path.name, "raw": path.read_bytes(), "path": str(path.resolve()),
            "description": description.read_text(encoding="utf-8") if description.exists() else None}
