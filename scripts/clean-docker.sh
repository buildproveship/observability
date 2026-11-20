#!/bin/sh
# Remove every container, network and volume owned by this repository's two Compose projects, so a runtime test run
# starts from (and leaves behind) nothing. Matches by Compose project label; touches nothing else on the daemon.
set -eu
docker="docker --host=unix:///var/run/docker.sock"
for project in rr-observability-baseline rr-observability-probes; do
  filter="label=com.docker.compose.project=$project"
  # shellcheck disable=SC2046
  $docker rm -f -v $($docker ps -aq --filter "$filter") 2>/dev/null || true
  # shellcheck disable=SC2046
  $docker network rm $($docker network ls -q --filter "$filter") 2>/dev/null || true
  # shellcheck disable=SC2046
  $docker volume rm -f $($docker volume ls -q --filter "$filter") 2>/dev/null || true
done
