"""Opt-in synthetic adapter verification, never a live TDM health command."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture_http', ROOT / 'scripts/baseline.py')
http = importlib.util.module_from_spec(spec)
spec.loader.exec_module(http)
http.BASE = 'http://127.0.0.1:19091'
LABELS = {'job': 'tdm-listener-fixture', 'instance': 'tdm-fixture',
          'service': 'tdm', 'source': 'synthetic-fixture'}
SELECTOR = '{job="tdm-listener-fixture",instance="tdm-fixture",service="tdm",source="synthetic-fixture"}'
SUCCESS = 'probe_success' + SELECTOR
DURATION = 'probe_duration_seconds' + SELECTOR
UP = 'up' + SELECTOR
# Filtering retains zero-valued observed failures; no `or vector(0)` fallback.
KNOWN = SUCCESS
for metric in (SUCCESS, DURATION, UP):
    KNOWN += f' and (time() - timestamp({metric}) <= 45)'
    KNOWN += f' and (time() - timestamp({metric}) >= -5)'
KNOWN += f' and ({UP} == 1) and ({DURATION} >= 0)'
CASES = ('available', 'denied', 'redirect', 'malformed', 'extra-field', 'timeout', 'oversized')


def compose(*args, case='available', profile=True, timeout=60):
    if case not in CASES:
        raise ValueError('Unknown synthetic case')
    env = {k: v for k, v in os.environ.items()
           if k not in {'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS',
                        'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH', 'COMPOSE_PROFILES'}}
    env['FIXTURE_CASE'] = case
    command = ['docker', '--host=unix:///var/run/docker.sock', 'compose',
               '-p', 'rrdplat35-fixture', '-f', str(ROOT / 'compose.probes.fixture.yaml')]
    if profile:
        command += ['--profile', 'fixture-only']
    return subprocess.run(command + list(args), cwd=ROOT, env=env, check=True,
                          timeout=timeout, capture_output=True, text=True).stdout


def query(expression, at=None):
    params = {'query': expression}
    if at is not None:
        params['time'] = str(at)
    return json.loads(http.fetch('/api/v1/query?' + urlencode(params)))


def decode(payload):
    """Strict test/CLI interpretation of the freshness-filtered PromQL result."""
    try:
        if payload['status'] != 'success' or payload.get('warnings') or payload.get('infos'):
            return 'unknown'
        if payload['data']['resultType'] != 'vector':
            return 'unknown'
        samples = payload['data']['result']
        if len(samples) != 1:
            return 'unknown'
        sample = samples[0]
        if sample['metric'] != dict(LABELS, __name__='probe_success'):
            return 'unknown'
        pair = sample['value']
        if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[1], str):
            return 'unknown'
        if type(pair[0]) not in (int, float) or not math.isfinite(pair[0]):
            return 'unknown'
        value = float(pair[1])
        if not math.isfinite(value) or value not in (0, 1):
            return 'unknown'
        return 'available' if value == 1 else 'probe-failed'
    except (KeyError, TypeError, ValueError, IndexError):
        return 'unknown'


def observation(at=None):
    try:
        return decode(query(KNOWN, at))
    except (OSError, ValueError):
        return 'unknown'


def wait_for(expected, after=0, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = observation()
        try:
            stamps = query('timestamp(' + SUCCESS + ')')['data']['result']
            fresh = len(stamps) == 1 and float(stamps[0]['value'][1]) >= after
        except (OSError, ValueError, KeyError, IndexError):
            fresh = False
        if state == expected and (expected == 'unknown' or fresh):
            return state
        time.sleep(0.5)
    raise AssertionError(f'Expected {expected}, last state {state}')


def validate():
    assert compose('config', '--services', profile=False).strip() == '', 'profile must default off'
    compose('config', '--quiet')
    compose('run', '--rm', '--no-deps', '--entrypoint', '/bin/promtool',
            'prometheus-fixture', 'check', 'config', '/etc/prometheus/prometheus.yml')
    compose('run', '--rm', '--no-deps', 'blackbox-fixture',
            '--config.file=/config/tdm-listener.yml', '--config.check')
    print('default-off profile, promtool and blackbox config validation passed', flush=True)


def runtime():
    try:
        compose('up', '-d', '--wait', '--wait-timeout', '30')
        wait_for('available')
        config = json.loads(compose('config', '--format', 'json'))
        for name, service in config['services'].items():
            assert '@sha256:' in service['image'], name
            if name != 'prometheus-fixture':
                assert not service.get('ports'), name
        inspected = json.loads(subprocess.check_output([
            'docker', '--host=unix:///var/run/docker.sock', 'inspect',
            'rrdplat35-fixture-prometheus-fixture-1'], timeout=10))[0]
        assert inspected['NetworkSettings']['Ports'] == {
            '9090/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '19091'}]}
        for case in CASES:
            compose('up', '-d', '--force-recreate', 'tdm-health-fixture', case=case)
            changed_at = time.time()
            expected = 'available' if case == 'available' else 'probe-failed'
            wait_for(expected, after=changed_at)
            if case == 'timeout':
                duration = float(query(DURATION)['data']['result'][0]['value'][1])
                assert 1.5 <= duration <= 3, duration
            print(json.dumps({'fixture_case': case, 'observed': expected,
                              'source': 'synthetic-fixture'}), flush=True)
        compose('up', '-d', '--force-recreate', 'tdm-health-fixture')
        wait_for('available', after=time.time())
        samples = query('{job="tdm-listener-fixture"}')['data']['result']
        names = {s['metric']['__name__'] for s in samples}
        assert {'probe_success', 'probe_duration_seconds', 'up'} <= names
        # Prometheus generates a fixed set of scrape bookkeeping metrics itself.
        assert all(n in {'probe_success', 'probe_duration_seconds', 'up'} or n.startswith('scrape_')
                   for n in names), names
        assert all({k: v for k, v in s['metric'].items() if k != '__name__'} == LABELS
                   for s in samples), samples
        assert not query(SUCCESS.replace('tdm-listener-fixture', 'absent-fixture'))['data']['result']
        assert decode(query(KNOWN.replace('tdm-listener-fixture', 'absent-fixture'))) == 'unknown'
        # Simulated evaluation instant against real stored fixture samples, not a live stale source.
        assert observation(at=time.time() + 46) == 'unknown'
        print('fixed labels, metric allowlist, absent-source and simulated stale-time checks passed', flush=True)
        compose('stop', '--timeout', '5', 'blackbox-fixture')
        wait_for('unknown')
        print('exporter stopped => unknown (not healthy zero)', flush=True)
    finally:
        compose('down', '--timeout', '5')
    assert observation() == 'unknown'
    print('query backend stopped => unknown; task containers/networks removed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate', 'test', 'start', 'status', 'stop'])
    args = parser.parse_args()
    if args.action == 'validate':
        validate()
    elif args.action == 'test':
        runtime()
    elif args.action == 'start':
        compose('up', '-d', '--wait', '--wait-timeout', '30')
        wait_for('available')
        print('synthetic-fixture available; no live TDM source')
    elif args.action == 'stop':
        compose('down', '--timeout', '5')
    else:
        state = observation()
        print(json.dumps({'source': 'synthetic-fixture', 'state': state}))
        return 0 if state == 'available' else 1
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(exc.stderr, file=sys.stderr)
        raise SystemExit(1)
