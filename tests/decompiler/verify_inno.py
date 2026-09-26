#!/usr/bin/env python3
"""Compare bounded IEX1 streams across decoder builds; never execute an installer.

The optional baseline is unmodified upstream: --test checks its payload checksums without
creating extracted files. The optional reference is the previous streaming build.
"""
import argparse
import hashlib
import json
import pathlib
import resource
import subprocess
import tempfile
import time

LIMIT = 1 << 30


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMIT, LIMIT))


def stream(tool, source):
    with tempfile.TemporaryDirectory(prefix='inno-stream-check-') as directory:
        work = pathlib.Path(directory)
        output = work / 'stream'
        error = work / 'stderr'
        with output.open('wb') as out, error.open('wb') as err:
            started = time.monotonic()
            result = subprocess.run([tool, '--decompiler-stream', '--silent', '--no-extract-unknown',
                                     '--no-gog-galaxy', '--collisions', 'error', '--', str(source)],
                                    cwd=work, stdout=out, stderr=err, timeout=300, preexec_fn=limits)
        assert sorted(p.name for p in work.iterdir()) == ['stderr', 'stream'], 'Native filesystem output'
        files = {}
        parse_error = None
        try:
            with output.open('rb') as f:
                assert f.read(5) == b'IEX1\n', 'No IEX1 header'
                while True:
                    line = f.readline(32)
                    if not line:
                        break
                    count, size = int(line), int(f.readline(32))
                    assert 0 < count <= 25000 and 0 <= size <= 256 << 20, 'Frame bounds'
                    names = []
                    for _ in range(count):
                        length = int(f.readline(32))
                        assert 0 < length <= 4096, 'Name bounds'
                        name = f.read(length).decode('utf-8')
                        assert len(name.encode('utf-8')) == length, 'Short name'
                        assert name not in files and name not in names, 'Duplicate stream name'
                        names.append(name)
                    digest = hashlib.sha256()
                    left = size
                    while left:
                        data = f.read(min(left, 65536))
                        assert data, 'Truncated member'
                        digest.update(data)
                        left -= len(data)
                    assert f.read(4) == b'OK!\n', 'Missing checksum-success trailer'
                    for name in names:
                        files[name] = (size, digest.hexdigest())
                    assert len(files) <= 25000, 'Entry limit'
        except (AssertionError, ValueError, UnicodeError) as e:
            parse_error = str(e)
        return dict(exit_code=result.returncode, parse_error=parse_error,
                    confirmed_files=len(files), confirmed_bytes=sum(v[0] for v in files.values()),
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    manifest_sha256=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
                    stderr=error.read_text(errors='replace')[-4000:]), files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tool', required=True)
    p.add_argument('--reference', help='Previous IEX1 streaming build')
    p.add_argument('--baseline', help='Unmodified PR build, used only with --test')
    p.add_argument('--output', type=pathlib.Path, required=True)
    p.add_argument('--allow-failure', action='append', default=[], help='Expected-failure filename')
    p.add_argument('--baseline-known-failure', action='append', default=[],
                   help='Record a known upstream baseline failure without failing the candidate')
    p.add_argument('samples', nargs='+', type=pathlib.Path)
    a = p.parse_args()
    rows = []
    for source in a.samples:
        source = source.resolve()
        current, files = stream(a.tool, source)
        row = dict(fixture=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest(), current=current)
        version = subprocess.run([a.tool, '--silent', '--data-version', '--', str(source)],
                                 capture_output=True, text=True, timeout=30)
        row['setup_data_version'] = version.stdout.strip()
        success = current['exit_code'] == 0 and current['parse_error'] is None and bool(files)
        row['expected_failure'] = source.name in a.allow_failure
        row['passed'] = success != row['expected_failure']
        if a.reference:
            previous, old_files = stream(a.reference, source)
            row['previous'] = previous
            if previous['exit_code'] == 0 and previous['parse_error'] is None:
                row['identical_to_previous'] = files == old_files
                row['passed'] &= row['identical_to_previous']
        if a.baseline:
            with tempfile.TemporaryDirectory(prefix='inno-baseline-check-') as directory:
                work = pathlib.Path(directory)
                with (work / 'stdout').open('wb') as out, (work / 'stderr').open('wb') as err:
                    result = subprocess.run([a.baseline, '--test', '--silent', '--no-extract-unknown',
                                             '--no-gog-galaxy', '--collisions', 'error', '--', str(source)],
                                            cwd=work, stdout=out, stderr=err, timeout=300, preexec_fn=limits)
                assert sorted(p.name for p in work.iterdir()) == ['stderr', 'stdout']
                row['baseline_exit_code'] = result.returncode
                row['baseline_stderr'] = (work / 'stderr').read_text(errors='replace')[-4000:]
                if not row['expected_failure'] and source.name not in a.baseline_known_failure:
                    row['passed'] &= result.returncode == 0
                row['baseline_known_failure'] = source.name in a.baseline_known_failure
        rows.append(row)
        a.output.write_text(json.dumps(rows, indent=2) + '\n')
        print(json.dumps({k: row[k] for k in ('fixture', 'setup_data_version', 'passed')}),
              'files=' + str(current['confirmed_files']), flush=True)
    assert all(r['passed'] for r in rows), 'See failed rows in ' + str(a.output)


if __name__ == '__main__':
    main()
