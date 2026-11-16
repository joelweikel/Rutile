from importlib.metadata import version
from functools import lru_cache
from time import monotonic

from rutile3.data.catalog import checksum
from rutile3.data.tensile import read_tensile
from rutile3.data.strength import ELEMENTS, SOURCES, strength_rows
from rutile3.properties.mechanical import analyze_tension
from rutile3.properties.strength import estimate_strength


def calculate_mechanical(folder, request, progress):
    started = monotonic()
    progress({"stage": "reading", "message": "Reading the tensile trace"})
    source = (folder / "tensile-source").read_bytes()
    selection = request["selection"]
    if checksum(source) != selection["selected_id"]:
        raise ValueError("Pinned tensile source changed before calculation.")
    settings = request["settings"]
    strain, stress = read_tensile(source, strain_unit=settings["strain_unit"],
                                  reference_id=selection.get("reference_id"))
    progress({"stage": "fitting", "message": "Analyzing proof stress and hardening"})
    result = analyze_tension(strain, stress, young_gpa=settings["young_gpa"], shear_gpa=settings["shear_gpa"])
    return {
        **result,
        "kind": "mechanical",
        "settings": settings,
        "units": {"stress": "MPa", "strain": "fraction", "modulus": "GPa", "temperature": "°C", "strain_rate": "1/s"},
        "assumptions": [
            "A single monotonic uniaxial tension test, with stress based on original area.",
            "The uniform-deformation approximation is used through the first measured stress maximum.",
            "The Voce law describes this trace under its recorded conditions. Fit residuals measure agreement with the input trace.",
            "Vickers hardness uses an approximate constraint factor of 3 at 0.08 true plastic strain within the fit range.",
        ],
        "provenance": {"source_name": request["source_name"], "source_sha256": selection["selected_id"],
                       "reference_id": selection.get("reference_id"), "source_url": selection.get("url"),
                       "archive": selection.get("archive"), "archive_member": selection.get("member"),
                       "versions": {"numpy": version("numpy"), "scipy": version("scipy")},
                       "elapsed_seconds": monotonic() - started},
    }


@lru_cache(maxsize=16)
def _screening_rows(raw, family, condition):
    return tuple(strength_rows(raw, family, condition))


def screen_strength(root, request):
    source = SOURCES[request.family]
    path = root.joinpath(*source["path"])
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    digest = checksum(raw)
    if digest != source["sha256"]:
        raise ValueError("The local strength dataset differs from the supported publisher file.")
    composition = {**request.additions_wt_pct, request.family: 100 - sum(request.additions_wt_pct.values())}
    rows = _screening_rows(raw, request.family, request.condition)
    result = estimate_strength(rows, ELEMENTS[request.family], request.family, composition)
    return {
        **result,
        "kind": "strength_screening",
        "family": request.family,
        "condition": source["conditions"][request.condition],
        "composition_wt_pct": composition,
        "provenance": {"model": "condition_matched_local_regression_v1", "source_name": path.name,
                       "source_url": source["url"], "source_sha256": digest,
                       "numpy_version": version("numpy")},
        "assumptions": [
            "Inputs are weight percentages. Omitted additions are treated as absent and the selected base metal makes up the balance.",
            "The selected condition groups records with broadly comparable processing.",
            "The model uses composition and reported condition. Test temperature, product dimensions and microstructure can vary within source groups.",
            "The held-out error describes source-table performance and is not a confidence interval or an independent experimental validation.",
        ],
    }
