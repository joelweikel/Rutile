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
REGISTRY_VERSION = "density-registry-1"


def density_rule(phase, *, allow_parent=False):
    name = phase["phase"]
    if name in DENSITY_RULES:
        return DENSITY_RULES[name], {"phase": name, "mapping": "explicit rule",
                                    "registry_version": REGISTRY_VERSION}
    parent = phase.get("linked_disordered_phase")
    if allow_parent and parent in DENSITY_RULES:
        return DENSITY_RULES[parent], {"phase": name, "mapping": "parent-phase approximation",
            "linked_parent": parent, "registry_version": REGISTRY_VERSION,
            "assumption": "Use linked disordered-parent density at the actual phase composition; ordering-dependent density is not modeled."}
    return None, {"phase": name, "reason": "No supported density-registry rule for this phase or its ordering state."}
