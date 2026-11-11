"""CLI and compatibility helpers for Rutile's Materials Project lookups.

Examples:
  python mp_properties.py --env-file "Y:\\Rutile3\\.env" --formula Re2Zr --spacegroup 194
  python mp_properties.py --chemsys Al-Cu --spacegroup 229
  python mp_properties.py mp-1374 mp-12109
  python mp_properties.py --formula Re24Zr5 --no-cache

Exit codes: 0 query completed (including no_match); 2 API/config/query failure.
"""
import argparse
import json
import sys
from pathlib import Path
from mp_client import MPClient, load_env_file, safe_search


def get_ids(ids, **kwargs):
    return MPClient(**kwargs).get_ids(ids).records


def scan_chemsys(chemsys, spacegroup=None, **kwargs):
    return MPClient(**kwargs).scan_chemsys(chemsys, spacegroup).records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('ids', nargs='*', help='MP material IDs')
    search = parser.add_mutually_exclusive_group()
    search.add_argument('--chemsys', help='Chemical system, e.g. Al-Cu')
    search.add_argument('--formula', help='Formula, e.g. Re2Zr, searched then exactly verified')
    parser.add_argument('--spacegroup', type=int, help='International space-group number')
    parser.add_argument('--env-file', type=Path, help='Path to local .env containing MP_API_KEY')
    parser.add_argument('--cache-dir', type=Path, default=Path(__file__).resolve().parent.parent / '.cache' / 'materials_project')
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--retries', type=int, default=3, help='Additional attempts after first failure')
    args = parser.parse_args(argv)
    if args.env_file:
        try:
            load_env_file(args.env_file)
        except OSError as e:
            print(json.dumps({'search_status':'configuration_error', 'error':str(e), 'records':[]}), file=sys.stdout)
            return 2
    if not (args.ids or args.chemsys or args.formula):
        parser.error('Specify IDs, --formula, or --chemsys')
    if args.ids and (args.chemsys or args.formula):
        parser.error('IDs cannot be combined with --formula or --chemsys')
    try:
        client = MPClient(retries=args.retries, cache_dir=args.cache_dir, use_cache=not args.no_cache)
    except Exception as exc:
        from mp_client import classify_error
        mapped = classify_error(exc)
        print(json.dumps({'search_status':mapped.status,'error_type':type(mapped).__name__, 'error':str(mapped),'records':[]},indent=2))
        return 2
    if args.formula:
        result = safe_search(client.find_formula, args.formula, spacegroup=args.spacegroup)
    elif args.chemsys:
        result = safe_search(client.scan_chemsys, args.chemsys, args.spacegroup)
    else:
        result = safe_search(client.get_ids, args.ids)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result['search_status'] in ('complete','no_match') else 2


if __name__ == '__main__':
    sys.exit(main())
