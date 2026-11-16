"""Adapters for the pinned public aluminum and steel property tables."""
import csv
from io import BytesIO, StringIO
import re
from xml.etree import ElementTree
from zipfile import ZipFile

SOURCES = {
    "AL": {
        "path": ("mendeley-b6br4yk6r3", "al_data.csv"),
        "sha256": "a3dd4f5091e485cf4db90308babcad38831174ddafbb6ae03df4ca3d4a647906",
        "url": "https://doi.org/10.17632/b6br4yk6r3.1",
        "conditions": {
            "peak-aged": "Solutionized and artificially peak aged",
            "overaged": "Solutionized and artificially overaged",
            "natural-aged": "Solutionized and naturally aged",
            "cold-worked-aged": "Solutionized, cold worked and naturally aged",
            "strain-hardened": "Strain hardened",
            "strain-hardened-hard": "Strain hardened (hard)",
        },
    },
    "FE": {
        "path": ("mendeley-jmwb9ddd43", "Steel database with labelled clusters.xlsx"),
        "sha256": "eaa89971150cff2bd97d8a1fe20b21e908731fcf755b37155608b1200235b484",
        "url": "https://doi.org/10.17632/jmwb9ddd43.1",
        "conditions": {"hot-rolled": "Hot rolled", "normalized": "Normalized", "annealed": "Annealed"},
    },
}

AL_ELEMENTS = "AG AL B BE BI CD CO CR CU ER EU FE GA LI MG MN NI PB SC SI SN TI V ZN ZR".split()
FE_COLUMNS = "G H I J K L M N O P Q R S T U V W X".split()
FE_ELEMENTS = "AL CU MN N NI TI S FE ZR P SI V MO CO C NB B CR".split()
ELEMENTS = {"AL": AL_ELEMENTS, "FE": FE_ELEMENTS}

AL_CONDITIONS = {
    "peak-aged": "Solutionised + Artificially peak aged",
    "overaged": "Solutionised + Artificially over aged",
    "natural-aged": "Solutionised + Naturally aged",
    "cold-worked-aged": "Solutionised + Cold Worked + Naturally aged",
    "strain-hardened": "Strain hardened",
    "strain-hardened-hard": "Strain Harderned (Hard)",
}
FE_EXCLUDED = re.compile(r"quench|carbur|temper|cold|forg|extrud|spher|stress.rel|harden|weld|cast|case|nitrid|normaliz.*anneal", re.I)


def _steel_rows(raw):
    with ZipFile(BytesIO(raw)) as book:
        strings = ["".join(node.text or "" for node in item.findall(".//{*}t"))
                   for item in ElementTree.fromstring(book.read("xl/sharedStrings.xml"))]
        sheet = ElementTree.fromstring(book.read("xl/worksheets/sheet1.xml"))
    for row in sheet.findall(".//{*}row")[1:]:
        cells = {}
        for cell in row:
            value = cell.findtext("{*}v")
            if value is not None:
                cells[cell.get("r").rstrip("0123456789")] = strings[int(value)] if cell.get("t") == "s" else value
        yield cells


def strength_rows(raw, family, condition):
    if family == "AL":
        rows = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
        for number, row in enumerate(rows, 2):
            if " ".join(row["Processing"].split()) != AL_CONDITIONS[condition]:
                continue
            yield ([row[element.title()] for element in AL_ELEMENTS], 100,
                   row["Yield Strength (MPa)"], row["Tensile Strength (MPa)"], str(number))
        return
    prefix = SOURCES["FE"]["conditions"][condition].lower()
    for row in _steel_rows(raw):
        description = row.get("C", "")
        if re.match(rf"^{prefix}\b", description, re.I) and not FE_EXCLUDED.search(description):
            yield ([row.get(column) for column in FE_COLUMNS], 1, row.get("AA"), row.get("Z"), row.get("A"))
