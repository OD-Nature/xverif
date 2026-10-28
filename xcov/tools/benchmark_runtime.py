"""Compare full native coverage output, latency, CPU and process-tree RSS.

Consumes the published xcov.exclusion and xcov.comprehensive fixtures; never
builds databases. Run outside the sandbox. The selected package root also owns
any child worker implementation; no binary/backend substitution is permitted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import sys
import threading
import time

parser = argparse.ArgumentParser()
parser.add_argument('--package-root', required=True)
parser.add_argument('--fixture-root', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--rounds', type=int, default=None)
parser.add_argument('--include-large', action='store_true',
                    help='also query all code metrics in one wide scope of the 3,001-scope fixture')
options = parser.parse_args()
if options.rounds is not None and options.rounds < 2:
    parser.error('--rounds must be at least 2')
package_root = Path(options.package_root).resolve()
sys.path.insert(0, str(package_root))
from xcov import backend as module
assert Path(module.__file__).resolve().is_relative_to(package_root)
from xcov.backend import NpiCoverageBackend

def rss_tree(pid):
    try:
        status = Path(f'/proc/{pid}/status').read_text()
        rss = next(int(line.split()[1]) for line in status.splitlines() if line.startswith('VmRSS:'))
        children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
        return rss + sum(rss_tree(int(child)) for child in children)
    except (OSError, StopIteration):
        return 0

def normalized(rows):
    return [{key: value for key, value in row.items() if key != 'coverage_ref'} for row in rows]

def cpu():
    own = resource.getrusage(resource.RUSAGE_SELF)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + child.ru_utime + child.ru_stime

def measure(fixture, filename, rounds):
    rounds = options.rounds or rounds
    home = Path(options.fixture_root) / fixture
    version = json.loads((home / 'current.json').read_text())['version']
    vdb = home / 'versions' / version / 'resources' / filename
    assert vdb.is_dir(), vdb
    samples = []
    done = threading.Event()
    def sampler():
        while not done.is_set():
            samples.append(rss_tree(os.getpid()))
            done.wait(0.02)
    thread = threading.Thread(target=sampler)
    thread.start()
    before_cpu = cpu()
    start = time.monotonic()
    backend = None
    try:
        backend = NpiCoverageBackend(str(vdb), exclusion_policy='strict')
        opened = time.monotonic() - start
        times = []
        steady_rss = []
        expected = None
        wide_scope = fixture == 'xcov.large_summary'
        for index in range(rounds):
            begun = time.monotonic()
            if wide_scope:
                rows = backend.exact_scope_items(
                    metrics=['line', 'toggle', 'branch', 'condition', 'fsm', 'assert'],
                    scope='top.u_leaf_0000',
                )
            else:
                rows = backend.items(metrics=['line', 'toggle', 'branch', 'condition', 'fsm', 'assert', 'functional'])
            times.append(time.monotonic() - begun)
            encoded = json.dumps(normalized(rows), sort_keys=True, separators=(',', ':')).encode()
            digest = hashlib.sha256(encoded).hexdigest()
            if expected is None:
                expected = digest
            assert digest == expected, 'repeated reads changed results'
            steady_rss.append(rss_tree(os.getpid()))
        mutation_times = []
        if not wide_scope:
            target = next(row for row in rows if row['metric'] == 'line' and row['type'] == 'npiCovStmtBin' and row['coverable'] == 1 and row['covered'] == 0 and not any('excluded' in flag for flag in row['status']))
            for iteration in range(10):
                begun = time.monotonic()
                for excluded in (True, False):
                    changed = backend.set_exclusion(target['coverage_ref'], excluded)
                    assert changed['status'] == 'changed', changed
                    state = next(row for row in backend.items(metrics=['line']) if row['coverage_ref'] == target['coverage_ref'])
                    assert ('excluded_at_report_time' in state['status']) == excluded
                mutation_times.append(time.monotonic() - begun)
            backend.set_exclusion(target['coverage_ref'], True)
            saved = str(Path(options.output).with_name(fixture + '-' + Path(options.output).stem + '.el'))
            backend.save_exclusions(saved)
            backend.unload_exclusions()
            state = next(row for row in backend.items(metrics=['line']) if row['coverage_ref'] == target['coverage_ref'])
            assert 'excluded_at_report_time' not in state['status']
            backend.load_exclusions([saved])
            state = next(row for row in backend.items(metrics=['line']) if row['coverage_ref'] == target['coverage_ref'])
            assert 'excluded_at_report_time' in state['status']
        before_close = time.monotonic()
        backend.close()
        closed = time.monotonic() - before_close
        elapsed = time.monotonic() - start
        return {
            'fixture': fixture, 'rounds': rounds, 'row_count': len(rows),
            'result_digest': expected, 'open_sec': opened, 'close_sec': closed,
            'scope': 'top.u_leaf_0000' if wide_scope else None,
            'mutation_median_sec': statistics.median(mutation_times) if mutation_times else None,
            'mutation_sec': mutation_times, 'read_sec': times, 'read_median_sec': statistics.median(times[1:]),
            'elapsed_sec': elapsed, 'cpu_sec': cpu() - before_cpu,
            'peak_tree_rss_kib': max(samples + steady_rss), 'steady_tree_rss_kib': steady_rss,
        }
    finally:
        if backend is not None:
            backend.close()
        done.set()
        thread.join()

results = []
cases = [('xcov.exclusion', 'exclusion.vdb', 20), ('xcov.comprehensive', 'comprehensive.vdb', 8)]
if options.include_large:
    cases.append(('xcov.large_summary', 'large_summary.vdb', 5))
for fixture, filename, rounds in cases:
    result = measure(fixture, filename, rounds)
    results.append(result)
    Path(options.output).write_text(json.dumps({'package_root': str(package_root), 'cases': results}, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('fixture', 'row_count', 'elapsed_sec', 'read_median_sec', 'mutation_median_sec', 'cpu_sec', 'peak_tree_rss_kib')}, sort_keys=True), flush=True)
