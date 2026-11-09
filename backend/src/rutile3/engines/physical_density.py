"""Bounded MatCalc DP density adapter for substitutional solution models.

DP values are mass densities in kg/m³, interpolated as a CALPHAD-type density
expansion. This does not import physical parameters as Gibbs energies/volumes.
"""
from collections import Counter
import math
import re

from pycalphad import Database, Model, variables as v

from rutile3.data.catalog import checksum
from rutile3.engines.matcalc import text
from rutile3.properties.phase_registry import density_rule


class DensityUnavailable(ValueError):
    pass


class PhysicalDensity:
    def __init__(self, raw):
        self.sha256 = checksum(raw)
        content = "\n".join(line.split("$")[0] for line in text(raw).splitlines())
        self.changes = Counter()
        if "120,331" in content:
            self.changes["Decimal comma 120,331 -> 120.331 in DTMNBCC"] = content.count("120,331")
            content = content.replace("120,331", "120.331")
        self.functions, self.parameters = {}, []
        generated, identities = [], {}
        for command in content.split("!"):
            command = command.strip()
            if not command:
                continue
            if command.upper().startswith("DEFINE_PARAMETER"):
                if not re.fullmatch(r"DEFINE_PARAMETER\s+DP\s+density", command, re.I):
                    raise DensityUnavailable("Unsupported physical parameter declaration.")
                continue
            match = re.fullmatch(r"FUNCTION\s+(\w+)\s+(.+)", command, re.I | re.S)
            if match:
                name, body = match.groups()
                name = name.upper()
                record = self._record(body, name)
                if name in self.functions:
                    raise DensityUnavailable(f"Duplicate physical function {name}.")
                self.functions[name] = record
                generated.append(f"FUNCTION {name} {record['lower']} {record['expression']}; {record['upper']} N !")
                continue
            match = re.fullmatch(r"PARAMETER\s+DP\(([^,]+),([^)]*)\)\s+(.+)", command, re.I | re.S)
            if not match:
                raise DensityUnavailable("Unsupported physical-data syntax; no automatic fallback was applied.")
            phase, constitution, body = match.groups()
            array, separator, order = constitution.partition(";")
            constituents = tuple(tuple(x.strip().upper() for x in sl.split(',')) for sl in array.split(':'))
            degree = int(order) if separator else 0
            record = self._record(body, f"DP({phase},{constitution})")
            identity = (phase.upper(), constituents, degree)
            values = (record["lower"], record["upper"], record["expression"])
            if identity in identities:
                if identities[identity] != values:
                    raise DensityUnavailable("Conflicting duplicate density parameters.")
                self.changes["Identical duplicate DP records removed"] += 1
                continue
            identities[identity] = values
            name = f"RUTILE_DP_{len(self.parameters)}"
            generated.append(f"FUNCTION {name} {record['lower']} {record['expression']}; {record['upper']} N !")
            self.parameters.append({**record, "phase": phase.upper(), "constituents": constituents,
                                    "order": degree, "symbol": name,
                                    "wildcard": any('*' in sl for sl in constituents)})
        # pycalphad's expression whitelist parses the arithmetic; never eval
        # arbitrary expressions from a source file.
        self.parsed = Database("\n".join(generated))

    @staticmethod
    def _record(body, label):
        match = re.fullmatch(r"\s*([\d.Ee+\-]+)\s+(.+?);\s*([\d.Ee+\-]+)\s+N\b(.*)", body, re.I | re.S)
        if not match:
            raise DensityUnavailable(f"Unsupported piecewise density expression in {label}.")
        low, expression, high, annotation = match.groups()
        lower, upper = float(low), float(high)
        if not lower < upper or not math.isfinite(lower + upper):
            raise DensityUnavailable("Invalid physical parameter temperature range.")
        return {"lower": lower, "upper": upper, "expression": expression.upper().strip(),
                "annotation": annotation.strip(), "label": label}

    def evaluate(self, record, temperature):
        if not record["lower"] <= temperature < record["upper"]:
            raise DensityUnavailable(f"{record['label']} is outside its declared temperature range.")
        expression = self.parsed.symbols[record["symbol"]]
        used = set()
        for _ in range(len(self.functions) + 1):
            replacements = {}
            for symbol in expression.free_symbols:
                name = str(symbol).upper()
                if name in self.functions:
                    definition = self.functions[name]
                    if not definition["lower"] <= temperature < definition["upper"]:
                        raise DensityUnavailable(f"Function {name} is outside its declared temperature range.")
                    replacements[symbol] = self.parsed.symbols[name]
                    used.add(name)
            if not replacements:
                break
            expression = expression.xreplace(replacements)
        remaining = {str(symbol) for symbol in expression.free_symbols} - {"T"}
        if remaining:
            raise DensityUnavailable("Unresolved physical function or unsupported state variable.")
        value = float(expression.subs({v.T: temperature}))
        if not math.isfinite(value):
            raise DensityUnavailable("Density expression returned a nonfinite value.")
        return value, sorted(used)

    def phase_density(self, phase, db, temperature, *, allow_parent=False):
        rule, mapping = density_rule(phase, allow_parent=allow_parent)
        if not rule:
            raise DensityUnavailable(mapping["reason"])
        physical_phase = rule.parameter_phase
        model_phase = mapping.get("linked_parent", phase["phase"])
        composition = phase["composition"]
        components = sorted(composition) + (["VA"] if "VA" in db.elements else [])
        model = Model(db, components, model_phase)
        if abs(float(model.site_ratios[0]) - 1) > 1e-8:
            raise DensityUnavailable("Non-unit substitutional site ratio is not supported by this density adapter.")
        if len(model.constituents) > 2:
            raise DensityUnavailable("Multisublattice density requires a site-occupancy model not implemented here.")
        if len(model.constituents) == 2:
            if rule.vacancy_ratio is None or {str(s) for s in model.constituents[1]} != {"VA"}:
                raise DensityUnavailable("Interstitial or non-vacancy secondary sublattice density is unsupported.")
            if abs(float(model.site_ratios[1]) - rule.vacancy_ratio) > 1e-8:
                raise DensityUnavailable("Thermodynamic and density-registry site ratios do not match.")
        if any(str(s) not in composition for s in model.constituents[0]):
            raise DensityUnavailable("Compound species or substitutional vacancies need an explicit density model.")
        if abs(sum(composition.values()) - 1) > 1e-6:
            raise DensityUnavailable("Phase atomic fractions do not sum to one.")
        records = [p for p in self.parameters if p["phase"] == physical_phase and not p["wildcard"]]

        def active_sublattice(record):
            array = record["constituents"]
            if len(array) > 1 and array[1:] != (("VA",),):
                return False
            return all(e in composition for e in array[0])

        records = [p for p in records if active_sublattice(p)]
        density, terms = 0., []
        for element, fraction in composition.items():
            if fraction <= 0:
                continue
            choices = [p for p in records if p["constituents"][0] == (element,) and p["order"] == 0]
            if len(choices) != 1:
                raise DensityUnavailable(f"Missing or ambiguous explicit {element} DP endmember in {physical_phase}; generic defaults are excluded.")
            record = choices[0]
            value, functions = self.evaluate(record, temperature)
            if value <= 0:
                raise DensityUnavailable("Nonpositive density endmember; no extrapolated value is used.")
            density += fraction * value
            terms.append({"parameter": record["label"], "weight": fraction, "value_kg_m3": value,
                          "functions": functions, "annotation": record["annotation"]})
        for record in records:
            species = record["constituents"][0]
            if len(species) == 1:
                continue
            if len(species) != 2:
                raise DensityUnavailable("Higher-order multicomponent density interactions are unsupported.")
            a, b = species
            weight = composition[a] * composition[b] * (composition[a] - composition[b]) ** record["order"]
            if weight == 0:
                continue
            value, functions = self.evaluate(record, temperature)
            density += weight * value
            terms.append({"parameter": record["label"], "weight": weight, "value_kg_m3": value,
                          "functions": functions, "annotation": record["annotation"]})
        if not math.isfinite(density) or density <= 0:
            raise DensityUnavailable("Density expansion is nonphysical at the selected conditions.")
        return {"state": "estimated", "value_g_cm3": density / 1000, "temperature_k": temperature,
                "method": "MatCalc DP endmember density expansion with binary Redlich–Kister terms",
                "mapping": {**mapping, "canonical_id": rule.canonical_id, "parameter_phase": physical_phase},
                "terms": terms, "source_sha256": self.sha256,
                "classification": "computed from source parameters; not a measurement or validated alloy prediction"}
