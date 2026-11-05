#!/usr/bin/env python3
"""Bounded local lifecycle and point-in-time checks; not a telemetry backend."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import ProxyHandler, HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:19090'
MAX_AGE = 45
HTTP_TIMEOUT = 2


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect rejected')


def request_deadline(signum, frame):
    raise TimeoutError('HTTP observation deadline exceeded')


def fetch(path):
    # CLI is Linux/main-thread only: bound the whole exchange, including slow reads.
    # Only loopback, no ambient proxy, no redirects to external destinations.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    previous = signal.signal(signal.SIGALRM, request_deadline)
    signal.setitimer(signal.ITIMER_REAL, HTTP_TIMEOUT)
    try:
        with opener.open(BASE + path, timeout=HTTP_TIMEOUT) as response:
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError('response exceeds limit')
            return data
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def assess(get=fetch, now=None):
    now = time.time() if now is None else now
    result = {'component': 'prometheus', 'status': 'unavailable',
              'observed_at': datetime.fromtimestamp(now, timezone.utc).isoformat(),
              'max_age_seconds': MAX_AGE, 'scope': 'local baseline self-scrape only'}
    try:
        if get('/-/ready').strip() != b'Prometheus Server is Ready.':
            raise ValueError('unexpected readiness response')
    except Exception as exc:
        result['reason'] = 'readiness unavailable: ' + type(exc).__name__
        return result
    result['status'] = 'unknown'
    try:
        targets = json.loads(get('/api/v1/targets'))
        if targets['status'] != 'success':
            raise ValueError('targets API failed')
        active = targets['data']['activeTargets']
        if len(active) != 1 or active[0]['labels'] != {'job': 'baseline', 'instance': 'localhost:9090'}:
            raise ValueError('expected exactly the baseline self-scrape')
        target = active[0]
        age = now - datetime.fromisoformat(target['lastScrape'].replace('Z', '+00:00')).timestamp()
        if not math.isfinite(age) or age < -5:
            raise ValueError('invalid scrape clock')
        result['scrape_age_seconds'] = round(age, 3)
        if age > MAX_AGE:
            result.update(status='stale', reason='last scrape exceeds freshness window')
            return result
        if target['health'] != 'up':
            result.update(status='partial', reason='ready backend but self-scrape is not up')
            return result
        sample = json.loads(get('/api/v1/query?query=timestamp%28up%7Bjob%3D%22baseline%22%7D%29'))
        if sample['status'] != 'success' or sample.get('warnings'):
            raise ValueError('query unsuccessful or incomplete')
        if sample['data']['resultType'] != 'vector' or len(sample['data']['result']) != 1:
            raise ValueError('missing or ambiguous self-scrape sample')
        value = sample['data']['result'][0]
        if value['metric'] != {'job': 'baseline', 'instance': 'localhost:9090'}:
            raise ValueError('unexpected sample source')
        age = now - float(value['value'][1])
        if not math.isfinite(age) or age < -5:
            raise ValueError('invalid sample clock')
        result['sample_age_seconds'] = round(age, 3)
        if age > MAX_AGE:
            result.update(status='stale', reason='stored sample exceeds freshness window')
        else:
            result.update(status='healthy', reason='ready, self-scrape up, query sample fresh')
    except Exception as exc:
        result['reason'] = 'incomplete verification: ' + type(exc).__name__
    return result


def compose(*args, timeout=60):
    # Explicit local daemon, no inherited remote Docker context.
    env = {key: value for key, value in os.environ.items()
           if key not in {'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS',
                          'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'}}
    return subprocess.run(['docker', '--host=unix:///var/run/docker.sock', 'compose',
                           '--project-name', 'rrdplat34-local', '-f', str(ROOT / 'compose.yaml'),
                           *args], cwd=ROOT, check=True, timeout=timeout, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'status', 'stop', 'validate'])
    args = parser.parse_args()
    try:
        if args.action == 'stop':
            compose('down', '--timeout', '10')  # Keep data/evidence; no volume deletion.
            return 0
        if args.action == 'validate':
            compose('config', '--quiet')
            compose('run', '--rm', '--no-deps', '--entrypoint', '/bin/promtool',
                    'prometheus', 'check', 'config', '/etc/prometheus/prometheus.yml')
            return 0
        if args.action == 'start':
            compose('config', '--quiet')
            compose('pull', timeout=180)
            compose('up', '-d', '--wait', '--wait-timeout', '45')
            deadline = time.monotonic() + 45
            while True:
                result = assess()
                if result['status'] == 'healthy' or time.monotonic() >= deadline:
                    break
                time.sleep(1)
        else:
            result = assess()
        print(json.dumps(result, indent=2))
        return 0 if result['status'] == 'healthy' else 1
    except (subprocess.SubprocessError, OSError) as exc:
        print(json.dumps({'status': 'unavailable', 'reason': type(exc).__name__,
                          'detail': 'Local Docker operation failed; inspect command output. Data retained.'}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
