"""Reproducible six-alloy density comparison, with unsupported cases retained.

No API, screening proxy, parameter tuning or silent phase omission. Runs the
existing processing worker serially. An explicitly reduced FCC diagnostic is
kept separate from the grade/equilibrium result, never substituted for it.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic, sleep

from rutile3.data.catalog import Catalog, PROJECT_ROOT, WORKSPACE, checksum
from rutile3.data.processing import resolve_sources, physical_source
from rutile3.domain.processing import ProcessingRequest
from rutile3.engines.matcalc import convert
from rutile3.engines.physical_density import PhysicalDensity, DensityUnavailable
from rutile3.engines.processing import nominal_composition
from rutile3.engines.tdb import parse_tdb
from rutile3.jobs.manager import JobManager
from rutile3.jobs.storage import read_json, write_json


def diagnostic(model, db, request, reference, *, omit_interstitials=False):
    composition = nominal_composition(request, db)
    x = composition['mole_fraction']
    omitted = {e: composition['nominal_percent'][e] for e in x
               if omit_interstitials and e in {'C', 'N', 'B', 'H', 'O'}}
    kept = {e: value for e, value in x.items() if e not in omitted}
    total = sum(kept.values())
    phase = {'phase': 'FCC_A1', 'label': 'FCC_A1', 'fraction': 1,
             'composition': {e: value/total for e, value in kept.items()}}
    value = {'basis': 'single FCC at nominal composition; phase fractions not predicted',
             'omitted_mass_percent': omitted, 'composition': phase['composition'],
             'note': 'Diagnostic only, not the alloy/product prediction. Remaining atomic fractions renormalized after any stated omission.'}
    try:
        density = model.phase_density(phase, db, request.final_temperature_k, allow_parent=False)
        value.update({'state': 'computed', 'density_g_cm3': density['value_g_cm3'], 'model': density})
        if not omitted:
            value['relative_difference_percent'] = 100*(density['value_g_cm3']/reference-1)
        else:
            value['comparison_to_grade_not_validated'] = True
    except DensityUnavailable as exc:
        value.update({'state': 'unsupported', 'reason': str(exc)})
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=PROJECT_ROOT/'backend/tests/fixtures/alloy-density-benchmarks.json')
    parser.add_argument('--timeout', type=float, default=240)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    definition = read_json(args.cases)
    output = args.output or WORKSPACE/'density-benchmarks'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/'cases.json', definition)
    catalog, manager = Catalog(), JobManager()
    physical = physical_source(catalog)
    if physical is None:
        raise ValueError('The physical_data.pdb source is required for this benchmark.')
    density_model = PhysicalDensity(physical['raw'])
    summaries = []
    print(f'Output: {output}', flush=True)
    try:
        for case in definition['alloys']:
            started = monotonic()
            # 2×nominal encodes an exact benchmark composition through the
            # existing half-maximum UI contract; these are not grade limits.
            request = ProcessingRequest(family=case['family'],
                additions=[{'element': e, 'maximum': 2*w} for e, w in case['composition_mass_percent_additions'].items()],
                melt_temperature_k={'AL': 1273.15, 'FE': 2173.15, 'NI': 2073.15}[case['family']],
                final_temperature_k=definition['temperature_k'], pressure_pa=definition['pressure_pa'],
                cooling_points=3, include_reference_properties=False, allow_screening_estimates=True,
                notes=f"Density benchmark: {case['name']}; explicit representative chemistry; no MP/proxies.")
            source, raw, mobility = resolve_sources(catalog, request)
            decision = {'selected_id': checksum(raw), 'physical_sha256': checksum(physical['raw']),
                        'mobility_sha256': checksum(mobility['raw']) if mobility else None}
            key = manager.start(source, request.model_dump(mode='json'), decision,
                snapshot=raw, kind='processing', physical=physical, mobility=mobility)
            folder = manager.folder(key)
            summary = {'alloy': case['name'], 'family': case['family'], 'reference_density_g_cm3': case['reference_density_g_cm3'],
                       'case': case, 'run_id': key, 'run_folder': str(folder), 'source_sha256': checksum(raw),
                       'physical_sha256': density_model.sha256}
            print(f"{case['name']}: started {key}", flush=True)
            while True:
                status = manager.status(key)
                if status['state'] != 'running':
                    break
                if monotonic()-started > args.timeout:
                    manager.cancel(key)
                    status = {'state': 'timeout', 'error': f'Exceeded {args.timeout:g} s'}
                    break
                sleep(.5)
            summary['job_status'] = status
            if status['state'] == 'completed':
                result = read_json(folder/'result.json')
                summary['composition_mass_percent'] = result['composition']['nominal_percent']
                summary['phases'] = result['final']['phases']
                properties = result['properties']
                summary['density'] = properties.get('density')
                summary['coverage_mole_fraction'] = properties.get('density_coverage_mole_fraction', 0)
                summary['phase_density_models'] = [{k: p.get(k) for k in ('label', 'fraction', 'density_model')} for p in properties.get('phases', [])]
                if summary['density'] and summary['density']['state'] == 'estimated':
                    value = summary['density']['value_g_cm3']
                    summary['relative_difference_percent'] = 100*(value/case['reference_density_g_cm3']-1)
            db = parse_tdb(convert(raw)[0])
            summary['nominal_fcc_diagnostic'] = diagnostic(density_model, db, request, case['reference_density_g_cm3'])
            summary['reduced_fcc_diagnostic'] = diagnostic(density_model, db, request, case['reference_density_g_cm3'], omit_interstitials=True)
            summary['elapsed_seconds'] = monotonic()-started
            write_json(output/f"{case['name'].replace(' ', '_')}.json", summary)
            summaries.append(summary)
            write_json(output/'summary.json', {'definition': definition, 'results': summaries})
            print(f"{case['name']}: density={summary.get('density')}; coverage={summary.get('coverage_mole_fraction')}; FCC diagnostic={summary['reduced_fcc_diagnostic'].get('density_g_cm3', summary['reduced_fcc_diagnostic'].get('reason'))}", flush=True)
    finally:
        manager.close()
    print(f'Completed {len(summaries)} comparisons: {output}', flush=True)


if __name__ == '__main__':
    main()
