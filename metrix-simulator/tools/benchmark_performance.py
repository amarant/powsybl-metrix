#!/usr/bin/env python3
"""Measure the five simulator workloads in isolated copies of their fixtures."""

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {
    'variantes_regroupees_complexe': ('variantes_regroupees', 11, ()),
    'contraintes_sans_action_possible': ('divers', 1, ()),
    'pompage_hr_necessaire': ('groupes', 1, ()),
    'composante_non_connexe': ('connexite', 1, ()),
    'LODF_PTDF_matrices': ('LODF_PTDF', 3, ('--write-PTDF', '--write-LODF')),
}


def run(binary, scenario, spec, runs, tmp_root, check_numeric):
    parent, variants, extra = spec
    workdir = tmp_root / scenario
    shutil.copytree(ROOT / 'tests' / parent / scenario, workdir)
    for pattern in ('out_*', 'metrixOut.txt', 'metrix*.log', 'LODF_matrix.csv', 'PTDF_matrix.csv'):
        for generated in workdir.glob(pattern):
            generated.unlink()
    environment = os.environ.copy()
    environment.update(HADES_DIR='.', METRIX_ETC=str(ROOT / 'etc'))
    environment.pop('METRIX_PERF', None)
    results = []
    for iteration in range(runs + 1):
        metric_file = tmp_root / f'{scenario}.{iteration}.time'
        command = ['/usr/bin/time', '-f', '%U %S %M', '-o', str(metric_file),
                   str(binary), 'metrixOut.txt', 'VariantSet.csv', 'out', '0', str(variants), *extra]
        start = time.perf_counter()
        with (tmp_root / f'{scenario}.{iteration}.log').open('wb') as log:
            completed = subprocess.run(command, cwd=workdir, env=environment,
                                       stdout=log, stderr=subprocess.STDOUT)
        wall = time.perf_counter() - start
        if completed.returncode:
            raise RuntimeError(f'{scenario} run {iteration} failed: {completed.returncode}; '
                               f'log: {tmp_root / f"{scenario}.{iteration}.log"}')
        user, system, rss = metric_file.read_text().split()
        results.append(dict(warmup=(iteration == 0), wall_s=wall, user_s=float(user),
                            system_s=float(system), max_rss_kb=int(rss)))
    if check_numeric and scenario == 'variantes_regroupees_complexe':
        subprocess.run([sys.executable, str(Path(__file__).with_name('check_performance_results.py')),
                        str(workdir)], check=True)
    measured = results[1:]
    summary = dict(wall_median_s=statistics.median(r['wall_s'] for r in measured),
                   wall_min_s=min(r['wall_s'] for r in measured),
                   wall_max_s=max(r['wall_s'] for r in measured),
                   user_median_s=statistics.median(r['user_s'] for r in measured),
                   max_rss_kb=max(r['max_rss_kb'] for r in measured))
    print(f'{scenario}: {summary}', flush=True)
    return dict(runs=results, summary=summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--scenario', choices=SCENARIOS, action='append',
                        help='repeat to select workloads; default: all')
    parser.add_argument('--no-numeric-check', action='store_true')
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be at least 1')
    binary = args.binary.resolve()
    output = args.output.resolve()
    selected = args.scenario or list(SCENARIOS)
    data = dict(binary=str(binary), warmups=1, repetitions=args.runs, scenarios={})
    with tempfile.TemporaryDirectory(prefix='metrix-benchmark-') as temp:
        tmp_root = Path(temp)
        for scenario in selected:
            data['scenarios'][scenario] = run(binary, scenario, SCENARIOS[scenario], args.runs,
                                               tmp_root, not args.no_numeric_check)
            output.write_text(json.dumps(data, indent=2) + '\n')


if __name__ == '__main__':
    main()
