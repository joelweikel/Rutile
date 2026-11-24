"""Convert the pinned Rahm et al. archive to Rutile's visible-spectrum library."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np


HC_EV_NM = 1239.841984
SOURCE = "https://doi.org/10.5281/zenodo.3822037"
REFERENCE = "https://doi.org/10.1002/adfm.202002122"


def composition(formula):
    counts = {element.upper(): int(amount or 1) for element, amount in re.findall(r"([A-Z][a-z]*)(\d*)", formula)}
    total = sum(counts.values())
    return {element: amount / total for element, amount in counts.items()}


def convert(raw):
    rows = []
    with ZipFile(BytesIO(raw)) as archive:
        for name in sorted(archive.namelist()):
            ordered = re.fullmatch(r"raw_df/(L1_\d)-([A-Za-z0-9]+)\.data", name)
            random = re.fullmatch(r"interpolated_df/([A-Z][a-z]?\d+-[A-Z][a-z]?\d+)\.data", name)
            if not (ordered or random):
                continue
            structure, formula = ordered.groups() if ordered else ("FCC", random[1].replace("-", ""))
            original = archive.read(name)
            spectrum = np.loadtxt(BytesIO(original))
            spectrum = spectrum[spectrum[:, 0] > 0]
            wavelength = HC_EV_NM / spectrum[::-1, 0]
            first = np.searchsorted(wavelength, 380, side="right") - 1
            last = np.searchsorted(wavelength, 780, side="left") + 1
            visible = np.column_stack((wavelength, spectrum[::-1, 1:]))[first:last]
            if len(visible) < 2 or visible[0, 0] > 380 or visible[-1, 0] < 780:
                raise ValueError(f"Incomplete visible spectrum for {name}")
            rows.append({"id": Path(name).stem, "formula": formula, "structure": structure,
                         "ordering": "ordered" if ordered else "disordered",
                         "composition_mole_fraction": composition(formula),
                         "representation": "dielectric", "member": name, "source_sha256": sha256(original).hexdigest(),
                         "samples": visible.tolist()})
    return {"schema_version": 1, "origin": "computed", "method": "Rahm et al. LR-TDDFT, with intraband term",
            "source": SOURCE, "reference": REFERENCE, "license": "CC BY 4.0",
            "archive_sha256": sha256(raw).hexdigest(), "spectra": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = convert(args.archive.read_bytes())
    args.output.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
