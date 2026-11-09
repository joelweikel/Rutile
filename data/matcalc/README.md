# Bundled MatCalc open databases

These are unmodified copies of the MatCalc basic open databases by Erwin
Povoden-Karadeniz (TU Wien), with additional authors and literature credited in
the original files. They are included so a repository download can run the
Al, Fe, and Ni family workflows without a separate database download.

| Family | Thermodynamic assessment | Automatically attached mobility |
|---|---|---|
| Al | `al/mc_al_v2037.tdb` (2.037) | `al/mc_al_v2008.ddb` (2.008) |
| Fe | `fe/mc_fe_v2062.tdb` (2.062) | `fe/mc_fe_v2016.ddb` (2.016) |
| Ni | `ni/mc_ni_v2036.tdb` (2.036) | `ni/mc_ni_v2012.ddb` (2.012) |

`physical/physical_data.pdb` (1.03) provides the optional local density parameters.
Its collection description is preserved beside it. The database files retain
their original bytes, encodings, line endings, notices, and references.
[manifest.json](manifest.json) records the original collection paths, roles,
versions, byte sizes, SHA-256 checksums, and absence of transformations. Some
upstream license comments retain older version numbers; those comments have
been preserved.

Source and compatibility information:
[MatCalc open databases](https://www.matcalc.at/index.php/databases/open-databases).
The publisher lists Fe mobility 2.016 for Fe thermodynamics 2.062 or newer,
Ni mobility 2.012 for Ni thermodynamics 2.036 or newer, and Al mobility 2.008
for Al thermodynamics 2.032 or newer. These named pairs are selected explicitly;
assessments are not concatenated. Arbitrary manually imported TDBs do not receive
a mobility companion automatically.

## Attribution and redistribution

The databases are made available under the
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Individual contents are licensed under the
[Database Contents License (DbCL) 1.0](https://opendatacommons.org/licenses/dbcl/1-0/).
These terms apply to the databases in this directory, including the physical
database as stated on the publisher's source page. Preserve the attribution,
license links, and original notices when redistributing these files. The
application's code and other datasets retain their own terms.

Original sources remain unchanged. Rutile converts supported MatCalc syntax
only in saved calculation runs, preserving source snapshots and recording
transformations and checksums. No scientific parameters are intentionally changed
in this distribution. Availability and named pairing do not establish assessed
interaction coverage, validity over arbitrary compositions or temperatures, or
experimental accuracy. Unsupported models and missing properties remain explicit.

## Source selection

This directory is the default `RUTILE_DATABASE_ROOT`. An explicit environment
override replaces it; it is not combined with a different source collection.
`RUTILE_PHYSICAL_DATABASE` can override the density file separately. Local
datasets outside this curated bundle remain ignored by version control.
