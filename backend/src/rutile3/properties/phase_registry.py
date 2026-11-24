"""Initial property-model registry, not a universal phase-identity translator."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DensityRule:
    canonical_id: str
    parameter_phase: str
    vacancy_ratio: float | None


DENSITY_RULES = {
    "FCC_A1": DensityRule("fcc.substitutional.v1", "FCC_A1", 1),
    "BCC_A2": DensityRule("bcc.substitutional.v1", "BCC_A2", 3),
    "HCP_A3": DensityRule("hcp.substitutional.v1", "HCP_A3", .5),
    "DIAMOND_A4": DensityRule("diamond.substitutional.v1", "DIAMOND_A4", None),
    "SI_DIAMOND_A4": DensityRule("diamond.substitutional.v1", "DIAMOND_A4", None),
    "HCP_ZN": DensityRule("hcp.substitutional.v1", "HCP_A3", .5),
    "LIQUID": DensityRule("liquid.substitutional.v1", "LIQUID", None),
}
MATCALC_AL_SHA256 = "87ec595f2caae189227ed11d5598c899b436b866ccfefea91304ca57188817c4"
REGISTRY_VERSION = "density-registry-3"


def resolved_disordered_parent(phase):
    parent = phase.get("linked_disordered_phase")
    evidence = phase.get("substitutional_disorder") or {}
    spread = evidence.get("max_site_fraction_difference", float("inf"))
    if (parent and evidence.get("state") == "disordered" and evidence.get("parent") == parent
            and isinstance(spread, (int, float)) and 0 <= spread <= 1e-5):
        return parent
    return None


def density_rule(phase, *, allow_parent=False, assessment_sha256=None):
    name = phase["phase"]
    if assessment_sha256 == MATCALC_AL_SHA256 and name == "FCCAL":
        return DENSITY_RULES["FCC_A1"], {"phase": name, "mapping": "MatCalc Al pure-FCC structural alias",
                                        "assessment_sha256": assessment_sha256, "registry_version": REGISTRY_VERSION}
    if name in DENSITY_RULES:
        return DENSITY_RULES[name], {"phase": name, "mapping": "explicit rule",
                                    "registry_version": REGISTRY_VERSION}
    parent = phase.get("linked_disordered_phase")
    if parent in DENSITY_RULES and resolved_disordered_parent(phase) == parent:
        return DENSITY_RULES[parent], {"phase": name, "mapping": "solved disordered parent",
            "linked_parent": parent, "registry_version": REGISTRY_VERSION,
            "ordering_evidence": phase["substitutional_disorder"]}
    if allow_parent and parent in DENSITY_RULES:
        return DENSITY_RULES[parent], {"phase": name, "mapping": "parent-phase approximation",
            "linked_parent": parent, "registry_version": REGISTRY_VERSION,
            "assumption": "Use linked disordered-parent density at the actual phase composition; ordering-dependent density is not modeled."}
    return None, {"phase": name, "reason": "No supported density-registry rule for this phase or its ordering state."}
