#!/usr/bin/env python3
"""Compare stable numeric results of the complex variant benchmark.

The complete output is intentionally not compared: equivalent solver solutions
may change the order and detail of the remedial actions.
"""

import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


def rows(path, prefix):
    return [line.split(';')[2:-1] for line in path.read_text().splitlines()
            if line.startswith(prefix + ' ;;')]


def number(value):
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Invalid number: ' + value) from error


def compare_values(actual, expected, tolerance, context):
    if len(actual) != len(expected):
        raise AssertionError(f'{context}: {len(actual)} fields, expected {len(expected)}')
    for index, (a, e) in enumerate(zip(actual, expected), 1):
        actual_number, expected_number = number(a), number(e)
        if actual_number is None or expected_number is None:
            if a != e:
                raise AssertionError(f'{context}, field {index}: {a!r} != {e!r}')
        elif abs(actual_number - expected_number) > tolerance:
            raise AssertionError(f'{context}, field {index}: {a} != {e} (tolerance {tolerance})')


def constraints(path):
    result = defaultdict(list)
    for row in rows(path, 'C2'):
        if len(row) != 4:
            raise AssertionError(f'{path}: unexpected C2 row {row}')
        result[row[0]].append(row[1:])
    return result


def check(reference, actual, tolerance):
    expected_files = {p.name: p for p in reference.glob('out_s*') if p.is_file()}
    actual_files = {p.name: p for p in actual.glob('out_s*') if p.is_file()}
    if expected_files.keys() != actual_files.keys() or not expected_files:
        raise AssertionError(f'Variant files differ: expected {sorted(expected_files)}, got {sorted(actual_files)}')
    for name, expected_path in sorted(expected_files.items()):
        actual_path = actual_files[name]
        for prefix in ('C1', 'R9'):
            expected_rows, actual_rows = rows(expected_path, prefix), rows(actual_path, prefix)
            if len(expected_rows) != 1 or len(actual_rows) != 1:
                raise AssertionError(f'{name}: expected one {prefix} status/objective row')
            compare_values(actual_rows[0], expected_rows[0], tolerance, f'{name} {prefix}')
        expected_constraints = constraints(expected_path)
        actual_constraints = constraints(actual_path)
        if expected_constraints.keys() != actual_constraints.keys():
            raise AssertionError(f'{name}: C2 incident names differ')
        for incident, expected_rows in expected_constraints.items():
            actual_rows = actual_constraints[incident]
            if len(expected_rows) != len(actual_rows):
                raise AssertionError(f'{name}: C2 count differs for {incident}')
            for index, (a, e) in enumerate(zip(sorted(actual_rows), sorted(expected_rows)), 1):
                compare_values(a, e, tolerance, f'{name} C2 {incident} #{index}')
    print(f'{len(expected_files)} variants: C1 status, R9 objective and C2 constraints match')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('actual', type=Path, help='directory containing out_s* files')
    parser.add_argument('--reference', type=Path, default=Path(__file__).resolve().parents[1] /
                        'tests_reference/variantes_regroupees/variantes_regroupees_complexe')
    parser.add_argument('--tolerance', type=Decimal, default=Decimal('0.05'),
                        help='absolute tolerance on values printed to one decimal place (default: 0.05)')
    args = parser.parse_args()
    check(args.reference, args.actual, args.tolerance)


if __name__ == '__main__':
    main()
