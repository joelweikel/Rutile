# Phase registry design and initial density rules

A registry connects a thermodynamic model to a physical structure/state and
compatible property models. It is not a name-renaming table, an additional
thermodynamic database, or a way to invent missing properties.

## Resolution flow

1. Read the pinned source identity and model signature: phase name, active
   constituents, site ratios, ordering links, and (when available) calculated
   sublattice occupancies, composition, temperature and pressure.
2. Find explicit rules whose source/model constraints match. Ambiguous or unknown
   identities remain unresolved; matching composition or space group alone is
   insufficient to establish structural equivalence.
3. Resolve to a canonical phase-state identifier, including whether ordering is
   known, disordered, or unresolved. Retain the original solver label.
4. Select a property model that supports that phase state, composition range,
   temperature and pressure. Density and elasticity have independent coverage.
5. Evaluate the property and retain parameters, source hashes, assumptions,
   applicability checks, approximation status and validation evidence.
6. Combine compatible phase results on the correct basis. Density requires molar
   masses and volumes; elastic averaging uses volume fractions. Missing phases
   are never silently removed.

## Proposed record contents

| Field | Purpose |
| --- | --- |
| Canonical identity | Structure prototype, ordering state and chemical model class |
| Source constraints | Source/version/hash or reviewed model signature, aliases, constituents and site ratios |
| State resolver | Required site occupancies/order parameters; unresolved-state behavior |
| Property providers | Independent density, elastic, thermal and later strengthening models |
| Applicability | Supported composition region, temperature/pressure bounds and required processing state |
| Evidence | Literature/assessment references, parameter checksums and benchmark tolerances |
| Resolution status | Explicit supported mapping, labeled approximation, ambiguous or unsupported |

For an FCC Ni-Mn solution, a reviewed FCC substitutional entry can choose the
local DP model with Ni and Mn endmembers at its actual composition and temperature.
That does not supply a Ni-Mn elastic model: modulus remains independently
uncovered unless a suitable composition-dependent model exists. A pure-Ni modulus
can only remain a separately labeled reference/proxy.

For GP_MAT, the graph compares solved site fractions on the substitutional
ordering sublattices. A maximum spread of 1e-5 or less supports the disordered
FCC parent. Ordered and unresolved states require applicable data or an
explicit parent-density approximation. The equilibrium record retains the
original phase label and the numerical evidence.

## What is implemented now

`properties/phase_registry.py` is a small versioned density-rule seed. It covers
FCC/BCC/HCP/diamond/liquid substitutional shapes, two explicit aliases, and an
optional linked-parent approximation. `engines/physical_density.py` checks active
thermodynamic model constituents and site ratios before evaluating DP data.
Every evaluated phase records the canonical rule ID and registry version.

The bundled MatCalc phase translation is a separate source of nominal crystal
identities. Alloy Studio uses it to screen density and elasticity references
for eligible phase compositions. The local DP registry retains its own
applicability checks. Broader structure resolution, ordering-state inference,
and experimental validation of phase-dependent properties remain open.
[Bundled translation](matcalc-mp-translation-layer.md) · [Property applicability](processing.md#materials-project-density-and-modulus)
