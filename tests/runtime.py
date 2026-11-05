"""Opt-in integration test. Owns only the documented rrdplat34-local project."""
import importlib.util
import json
import subprocess
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('baseline', Path(__file__).resolve().parents[1] / 'scripts/baseline.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def expect(status):
    deadline = time.monotonic() + 45
    while True:
        result = baseline.assess()
        if result['status'] == status:
            print(json.dumps({'expected': status, 'actual': result}), flush=True)
            return
        if time.monotonic() >= deadline:
            raise AssertionError(result)
        time.sleep(1)


try:
    baseline.compose('up', '-d', '--wait', '--wait-timeout', '30')
    expect('healthy')
    config = json.loads(subprocess.check_output([
        'docker', '--host=unix:///var/run/docker.sock', 'inspect',
        'rrdplat34-local-prometheus-1'], timeout=10))[0]
    ports = config['NetworkSettings']['Ports']
    assert ports == {'9090/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '19090'}]}, ports
    print(json.dumps({'published_ports': ports}), flush=True)
    baseline.compose('-f', str(baseline.ROOT / 'tests/partial.compose.yaml'),
                     'up', '-d', '--force-recreate', '--wait', '--wait-timeout', '30')
    expect('partial')
    baseline.compose('up', '-d', '--force-recreate', '--wait', '--wait-timeout', '30')
    expect('healthy')
finally:
    baseline.compose('down', '--timeout', '10')
expect('unavailable')
