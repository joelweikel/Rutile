# MatCalc Physical Data (Density) PDB

## Quality: LOW — Physical Property Parameter File, Not a Full TDB

## Summary

MatCalc physical data file, version 1.03 (2009-06-19), edited by Erwin Povoden-Karadeniz (TU Wien). Contains thermo-physical property parameters — primarily mass density (DP) — for pure elements and selected intermetallic compounds, with crystal structure data (FCC, BCC, HCP, TETR, RHOH, ORHO, DIAM, MONO, CUB). Densities at reference T 298 K are given as FUNCTION definitions (D0FCC_AG, D0FCC_AL, etc.) and PARAMETER DP entries. Updated 2001-01-08, 2008-07-07 (volumetric misfit for bcc-Cu), 2008-12-18 (Al-Si-Mg data). Version 1.02 (2009-06-18): new DTALFCC, DTFEBCC, DTFEFCC polynomials and PARAMETER DP(BCC_A2, AL:VA). Version 1.03 (2009-06-19): new polynomials for Al, Co, Cr, Cu, Fe, Mg, Mo, Nb, Ni, Sc, Si, Ti, V, W, Zn, Zr, and C; assess AlN; include DIAMOND_A4.

## Key Features

- **DEFINE_PARAMETER DP**: Density parameter definition
- **FUNCTION D0***: Density functions for pure elements at 298 K (137 entries)
- **PARAMETER DP**: Density parameters for phases/compounds (137 entries)
- **Crystal structure data**: FCC, BCC, HCP, TETR, RHOH, ORHO, DIAM, MONO, CUB
- **Elements covered**: Al, Ag, Au, B, Ba, Be, Bi, C, Ca, Cd, Co, Cr, Cu, Fe, Mg, Mo, Nb, Ni, Sc, Si, Ti, V, W, Zn, Zr, etc.
- **References**: 14+ literature citations (refs 3, 4/17, 13, 14, 15, 16, 19)
- **Open Database License**: ODBL 1.0 + DBCL 1.0

## Notes

- Not a TDB — physical property parameters only (density), no thermodynamic model parameters
- Used in conjunction with MatCalc TDBs (mc_fe, mc_ni, mc_al) for density/property calculations
- Raw MatCalc file (ASCII, CRLF line endings)
- Last updated 2008-12-18 (database version 1.03, 2009-06-19)
- 137 PARAMETER entries (density + crystal structure data)
