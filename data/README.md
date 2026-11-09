# Local reference data

The curated [MatCalc bundle](matcalc/README.md) is included in repository downloads
and is the default source for the Al/Fe/Ni thermodynamic assessments, their
automatically attached mobility companions, and the optional local density data.
Attribution, redistribution terms, and original-file checksums travel with it.

Other contents are ignored by version control. Keep originals and provenance;
do not place API credentials here. `RUTILE_DATABASE_ROOT` selects an alternative
source collection without modifying it. Managed imports and run snapshots remain
under the configured workspace; the live SQLite catalog defaults to local
application data outside the repository.
