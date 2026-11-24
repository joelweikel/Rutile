"""Install the pinned local optical runtime into the ignored workspace."""
import argparse
from hashlib import file_digest, sha256
import os
from pathlib import Path, PurePosixPath
from shutil import copyfileobj
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZipFile

import requests

from rutile3.data.catalog import WORKSPACE


WINDOWS_ARCHIVE = (
    "https://github.com/QMatSuite/quantum-espresso-windows-exe/releases/download/"
    "qe-7.5-win-oneapi-msmpi/qe-7.5-win-oneapi-msmpi.zip"
)
WINDOWS_SHA256 = "e50ec7368a5b7a964eb5084e0a13464ba2628d4e147c16227e876002ea34fdf7"
PSEUDO_ROOT = "https://raw.githubusercontent.com/pipidog/ONCVPSP/15e29810cb80ae5b814413f73376b379f26d6a3f/sg15/"
PSEUDOS = {
    "Ag_sr": "5024c8972e1178964b2c53555839c663e0ac2ad96b0c3e98d6d24ddc088ed650",
    "Al_sr": "a1ab6de90b82239bc18586bd01a00a45ca471015a41c0a80caf52bac5d499fac",
    "Au_fr": "f401997d1357740ba3dce04cded85c19478157eba1b93ec50b0e952683bf57cf",
    "Cu_sr": "ad982b873efd1e3a94969bef71e0b9bd40004f88feeb87dafa9c95369095fe3e",
    "Ga_sr": "759db5b7f7e62b9c453ba1e5ffe87596108263e861c87a0a30a69026ebbf3d1d",
    "Ni_sr": "a60fb1dc57649b366797fa4d9f60fa5b3bf715ee09e6b5c0125fe84d38091546",
    "Pd_sr": "725a830cc4d0717071a3a342350ae1b7097e6a7ba066a9f8a0726a53203ed98a",
    "Pt_fr": "c50ecc3796eb7b830a00f7f2050629cc1f6ff41b67da22c6a2c401ae471a8a7d",
    "Zn_sr": "e1b338a9cbc581570974ce09dfe699fa11e3a93eb604be39ee870288b087e179",
}


def _hash_file(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def ensure_download(url, path, expected):
    if path.is_file() and _hash_file(path) == expected:
        return
    digest = sha256()
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with requests.get(url, stream=True, timeout=(15, 90)) as response, temporary.open("wb") as stream:
            response.raise_for_status()
            for data in response.iter_content(1024 * 1024):
                digest.update(data)
                stream.write(data)
        if digest.hexdigest() != expected:
            raise ValueError(f"Downloaded checksum differs for {path.name}.")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def install_windows(root):
    archive = root / "qe.zip"
    ensure_download(WINDOWS_ARCHIVE, archive, WINDOWS_SHA256)
    (root / "bin").mkdir(exist_ok=True)
    with ZipFile(archive) as source, TemporaryDirectory(dir=root) as staging:
        for item in source.infolist():
            path = PurePosixPath(item.filename)
            binary = (path.parent == PurePosixPath("bin")
                      and (path.name in {"pw.exe", "epsilon.exe"} or path.suffix == ".dll"))
            if not binary and path.as_posix() not in {"README.txt", "VERSION.txt"}:
                continue
            temporary = Path(staging) / path.name
            with source.open(item) as infile, temporary.open("wb") as outfile:
                copyfileobj(infile, outfile)
            target = root.joinpath(*path.parts)
            if not target.is_file() or _hash_file(target) != _hash_file(temporary):
                temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pseudos-only", action="store_true", help="Use your own Quantum ESPRESSO installation.")
    args = parser.parse_args()
    root = WORKSPACE / "optics-runtime"
    (root / "pseudo").mkdir(parents=True, exist_ok=True)
    if os.name == "nt" and not args.pseudos_only:
        print("Installing Quantum ESPRESSO 7.5 into the local workspace.", flush=True)
        install_windows(root)
    for key, digest in PSEUDOS.items():
        symbol, relativity = key.split("_")
        name = f"{symbol}_ONCV_PBE_{relativity}.upf"
        ensure_download(PSEUDO_ROOT + name, root / "pseudo" / name, digest)
    print(root)


if __name__ == "__main__":
    main()

