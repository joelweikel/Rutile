"""Read a bounded tensile CSV or a known local reference specimen."""
import csv
from io import BytesIO, StringIO
import re
from xml.etree import ElementTree
from zipfile import ZipFile

MAX_BYTES = 2 * 1024 * 1024
MAX_POINTS = 20_000

REFERENCES = {
    "al-6061": {
        "label": "Al · 6061-T651 bar", "material": "6061-T651", "condition": "Commercial bar · lot A · uniaxial tension",
        "temperature_c": 20, "url": "https://doi.org/10.17632/rd6jm9tyb6.1",
        "folder": "mendeley-rd6jm9tyb6",
        "file": "stress-strain-curves-of-aluminum-6061-t651-from-9-lots-at-6-temperatures-under-uniaxial-and-plain-strain-tension.zip",
        "member": "T_020_A_1_001_022_03.csv",
    },
    "fe-hct590x": {
        "label": "Fe · HCT590X rolled sheet", "material": "HCT590X",
        "condition": "Rolled sheet · 1.5 mm · 0° to rolling direction · TS05 specimen 1",
        "temperature_c": 23, "strain_rate_s": .01, "url": "https://zenodo.org/records/21993433",
        "folder": "zenodo-21993433", "file": "TRR285-processed_data.zip",
        "member_prefix": "HCT590X/base/TS05_EX01-",
    },
    "ni-in625": {
        "label": "Ni · Inconel 625 as built", "material": "Inconel 625",
        "condition": "Laser powder bed fusion · as built · room-temperature test · NIST specimen T3",
        "url": "https://data.nist.gov/od/id/mds2-2760",
        "folder": "nist-mds2-2760", "file": "SpecimenT3_stress_strain.csv",
    },
}


def reference_source(root, key):
    source = REFERENCES.get(key)
    if source is None:
        raise ValueError("Unknown tensile reference.")
    path = root / source["folder"] / source["file"]
    if not path.is_file():
        raise ValueError("This reference is unavailable locally. Choose a CSV file instead.")
    member = source.get("member")
    if member or source.get("member_prefix"):
        with ZipFile(path) as archive:
            if member is None:
                member, = [name for name in archive.namelist() if name.startswith(source["member_prefix"])
                           and name.endswith(".xlsx")]
            if archive.getinfo(member).file_size > MAX_BYTES:
                raise ValueError("The reference file exceeds the upload limit.")
            raw = archive.read(member)
    else:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    return (member or path.name).rsplit("/", 1)[-1], raw, {
        "reference_id": key, "url": source["url"], "archive": path.name if member else None, "member": member,
    }


def _csv_trace(raw, strain_unit):
    try:
        lines = [line for line in raw.decode("utf-8-sig").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        delimiter = "\t" if "\t" in lines[0] else ","
        rows = csv.reader(lines, delimiter=delimiter, strict=True)
        header = [re.sub(r"[^a-z0-9%]", "", cell.lower()) for cell in next(rows)]
    except (UnicodeDecodeError, IndexError, csv.Error) as exc:
        raise ValueError("Use a UTF-8 CSV or tab-separated file with a header.") from exc
    if any("true" in name for name in header):
        raise ValueError("Use engineering stress and strain columns from a uniaxial tensile test.")
    strain_columns = [i for i, name in enumerate(header) if name in {
        "strain", "engineeringstrain", "engineeringstrainmmmm", "engineeringstrainmmpermm",
        "strainfraction", "engineeringstrainfraction", "strain%", "strainpercent", "engineeringstrain%",
        "engineeringstrainpercent",
    }]
    stress_columns = [i for i, name in enumerate(header) if name in {"stressmpa", "engineeringstress", "engineeringstressmpa"}]
    if len(strain_columns) != 1 or len(stress_columns) != 1:
        raise ValueError("Include one engineering_strain and one stress_MPa column.")
    strain_col, stress_col = strain_columns[0], stress_columns[0]
    if len(lines) > MAX_POINTS + 2:
        raise ValueError(f"Choose a trace with at most {MAX_POINTS:,} readings.")
    strain, stress = [], []
    try:
        for number, row in enumerate(rows, 2):
            x, y = row[strain_col].strip(), row[stress_col].strip()
            if number == 2 and y.lower() == "mpa" and x.lower() in {"m/m", "mm/mm", "1", "%"}:
                if (x == "%") != (strain_unit == "percent"):
                    raise ValueError("The strain unit in the file differs from the selected unit.")
                continue
            try:
                strain.append(float(x) / (100 if strain_unit == "percent" else 1))
                stress.append(float(y))
            except ValueError as exc:
                raise ValueError(f"Data row {number} must contain numeric engineering strain and stress.") from exc
    except (IndexError, csv.Error) as exc:
        raise ValueError("Each CSV data row must include both strain and stress.") from exc
    if ("%" in header[strain_col] or "percent" in header[strain_col]) and strain_unit != "percent":
        raise ValueError("Select percent strain for this CSV.")
    if ("mm" in header[strain_col] or "fraction" in header[strain_col]) and strain_unit != "fraction":
        raise ValueError("Select fraction strain for this CSV.")
    return strain, stress


def read_tensile(raw, *, strain_unit, reference_id=None):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Choose a nonempty tensile file no larger than 2 MB.")
    if reference_id != "fe-hct590x":
        return _csv_trace(raw, strain_unit)
    # TS05's first specimen uses columns D (MPa) and E (%) from row 4.
    # This source adapter is restricted to the bundled reference selection.
    with ZipFile(BytesIO(raw)) as workbook:
        info = workbook.getinfo("xl/worksheets/sheet1.xml")
        if info.file_size > 4 * MAX_BYTES:
            raise ValueError("The reference worksheet is too large.")
        sheet = ElementTree.fromstring(workbook.read(info))
    strain, stress = [], []
    for row in sheet.findall(".//{*}row")[3:]:
        cells = {cell.get("r"): cell.findtext("{*}v") for cell in row}
        number = row.get("r")
        x, y = cells.get(f"E{number}"), cells.get(f"D{number}")
        if x is not None and y is not None:
            strain.append(float(x) / 100)
            stress.append(float(y))
        if len(strain) > MAX_POINTS:
            raise ValueError(f"Choose a trace with at most {MAX_POINTS:,} readings.")
    return strain, stress
