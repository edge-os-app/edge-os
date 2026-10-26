#!/bin/sh
# Edge OS host firewall for the two Compose bridges in compose.coolify.yml (iptables backend, IPv4).
#
#   edgeos-egress  the execution worker's only route out: DNS to the host's upstream resolvers, TCP to the
#                  resolved addresses of EDGE_OS_EGRESS_HOSTS on EDGE_OS_EGRESS_PORTS, and TCP 443 to the resolved
#                  addresses of EDGE_OS_EGRESS_RELAY_HOSTS (the keyless /rpc relay names served by this host's
#                  Traefik) only when it is delivered to Traefik on this host (docker-proxy or DNAT). Everything
#                  else is dropped.
#   edgeos-hostdb  PostgreSQL's loopback publish: nothing is forwarded in or out, and only replies reach the host.
#   edgeos-private the internal service network: only replies reach the host (its gateway must not expose SSH or
#                  Coolify to the containers).
#
# Every rule matches the bridge name or its fixed subnet, so a bridge renamed by a later edit is still filtered.
#
# Coolify also attaches its own resource network (named the resource UUID) to every container. `apply` runs before
# Docker, so only `refresh` can inspect the two containers. `refresh` derives the Compose project from the fixed
# `edgeos-hostdb` bridge label (Coolify starts a Service with `--project-name <service uuid>`, so the file name is not
# the project name), finds execution-worker and postgres by that project and their service labels, and reads the
# addresses they hold on any network they do not declare. It drops forwarding to and from exactly those addresses and
# keeps host-bound traffic replies-only. The idle no-op happens only when none of the fixed bridges exists. A fixed
# bridge without a project label, a missing or duplicate container, a missing declared network, an unreachable daemon
# or an IPv6 address fails the refresh; it never passes silently.
#
# Docker cannot restrict by host name; this script resolves the names on the host into an ipset. `apply` builds the
# rules in the idle one of two chains and switches the jump to it, so a re-run never leaves an empty chain hooked.
# `refresh_allowlist` only adds addresses with a timeout; an empty answer never clears the set (it fails closed when
# entries expire). `refresh` runs it and then enforces the Coolify resource-network addresses.
#
# The relay names resolve to this host's own public address, where Traefik's port 443 is published. Docker delivers a
# worker connection there one of two ways, and both are admitted for TCP 443 to a relay address only:
#   docker-proxy (Docker's default, `userland-proxy: true`): not DNATed; it reaches the host through INPUT, where the
#     EDGE_OS_IN chain accepts it before its drop.
#   DNAT (`userland-proxy: false`): rewritten to Traefik on Coolify's bridge, so it never matches the address set.
#     `apply` marks it in mangle PREROUTING while its destination is still a relay address and accepts exactly the
#     marked, DNATed flow (both directions) in DOCKER-USER, ahead of Docker's inter-bridge isolation.
# The relay names never enter the general set.
#
# Configuration: /etc/edge-os/egress.env (root:root 0600), for example
#   EDGE_OS_EGRESS_HOSTS="api.privy.io"
#   EDGE_OS_EGRESS_RELAY_HOSTS="rpc-a.edgeos.fun rpc-b.edgeos.fun"
#   EDGE_OS_EGRESS_PORTS="443"
# See docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md §4 and docs/qualification/inapp-trade/RPC_RELAY.md.
set -eu

CONFIG=${EDGE_OS_EGRESS_CONFIG:-/etc/edge-os/egress.env}
# shellcheck disable=SC1090
. "$CONFIG"
: "${EDGE_OS_EGRESS_HOSTS:?set EDGE_OS_EGRESS_HOSTS in $CONFIG}"
EDGE_OS_EGRESS_PORTS=${EDGE_OS_EGRESS_PORTS:-443}
EDGE_OS_EGRESS_RELAY_HOSTS=${EDGE_OS_EGRESS_RELAY_HOSTS:-}
SET=edgeos-egress-allow
RELAY_SET=edgeos-egress-relay
RELAY_MARK=0x2031
TTL=900
EGRESS_SUBNET=10.203.0.0/28
HOSTDB_SUBNET=10.203.0.16/28
PRIVATE_SUBNET=10.203.0.64/26
PROJECT=
LOCK=${EDGE_OS_EGRESS_LOCK:-/run/edge-os-egress-firewall.lock}

resolvers() {
  # Docker's rule: it reads the systemd-resolved upstream file only when /etc/resolv.conf names loopback stubs only.
  file=/etc/resolv.conf
  if [ -f /run/systemd/resolve/resolv.conf ] \
      && ! awk '$1 == "nameserver" && $2 !~ /^127\./ {found = 1} END {exit !found}' /etc/resolv.conf; then
    file=/run/systemd/resolve/resolv.conf
  fi
  awk '$1 == "nameserver" && $2 ~ /^[0-9.]+$/ && $2 !~ /^127\./ {print $2}' "$file" | sort -u
}

fill() {
  # fill <set> <names>: add each name's current IPv4 addresses with a timeout; never remove one.
  target=$1
  ipset create "$target" hash:ip family inet timeout "$TTL" -exist
  for host in $2; do
    getent ahostsv4 "$host" | awk '{print $1}' | sort -u | while read -r ip; do
      ipset -exist add "$target" "$ip" timeout "$TTL"
    done
  done
}

refresh_allowlist() {
  fill "$SET" "$EDGE_OS_EGRESS_HOSTS"
  fill "$RELAY_SET" "$EDGE_OS_EGRESS_RELAY_HOSTS"
}

stack_project() {
  # Print "<project> <bridge-present>" from the fixed bridge labels. The bridge label is authoritative; the optional
  # EDGE_OS_COMPOSE_PROJECT is only a cross-check. Coolify starts a Service with `--project-name <service uuid>`, so
  # the Compose file's top-level name is not the project name.
  ids=$(docker network ls --quiet --filter driver=bridge) || return 1
  if [ -z "$ids" ]; then printf 'none 0\n'; return 0; fi
  lines=$(printf '%s\n' "$ids" | xargs docker network inspect \
    --format '{{index .Options "com.docker.network.bridge.name"}} {{index .Labels "com.docker.compose.project"}}') \
    || return 1
  present=$(printf '%s\n' "$lines" | awk '$1 == "edgeos-hostdb" || $1 == "edgeos-egress" || $1 == "edgeos-private" {found = 1} END {print found + 0}')
  project=$(printf '%s\n' "$lines" | awk '$1 == "edgeos-hostdb" {print $2; exit}')
  printf '%s %s\n' "${project:-none}" "$present"
}

container_id() {
  # container_id <compose service>: the single running container id, or a loud failure.
  ids=$(docker ps --quiet --no-trunc \
    --filter "label=com.docker.compose.project=$PROJECT" \
    --filter "label=com.docker.compose.service=$1") \
    || { echo "cannot list the $1 containers in compose project $PROJECT" >&2; return 1; }
  count=$(printf '%s\n' "$ids" | awk 'NF {found++} END {print found + 0}')
  [ "$count" -eq 1 ] \
    || { echo "expected one running $1 container in compose project $PROJECT, found $count" >&2; return 1; }
  printf '%s\n' "$ids"
}

declared_networks() {
  # The Docker network names this project declares for each protected service.
  case "$1" in
    execution-worker) echo "$PROJECT"_private "$PROJECT"_egress ;;
    postgres) echo "$PROJECT"_private "$PROJECT"_hostdb ;;
    *) echo "unknown protected service: $1" >&2; return 1 ;;
  esac
}

container_networks() {
  # One endpoint per line, split by `|`: a network name cannot contain it and an address value can contain a
  # space (Docker 29 prints an unset address as "invalid IP"), so no field can shift into another.
  docker inspect --type container \
    --format '{{range $name, $endpoint := .NetworkSettings.Networks}}{{$name}}|{{$endpoint.IPAddress}}|{{$endpoint.GlobalIPv6Address}}{{"\n"}}{{end}}' \
    "$1"
}

service_addresses() {
  # The IPv4 addresses one protected service holds on networks it does not declare. Fails closed.
  service=$1
  id=$(container_id "$service") || return 1
  networks=$(container_networks "$id") || { echo "cannot inspect the $service container $id" >&2; return 1; }
  declared=$(declared_networks "$service") || return 1
  for required in $declared; do
    printf '%s\n' "$networks" | awk -F'|' -v want="$required" 'NF && $1 == want {found = 1} END {exit !found}' \
      || { echo "$service is not on its declared network $required" >&2; return 1; }
  done
  printf '%s\n' "$networks" | awk -F'|' -v service="$service" -v declared=" $declared " '
    function quad(ip,   part, n, i) {
      n = split(ip, part, ".")
      if (n != 4) return 0
      for (i = 1; i <= 4; i++) {
        if (part[i] !~ /^[0-9][0-9]?[0-9]?$/) return 0
        if (length(part[i]) > 1 && substr(part[i], 1, 1) == "0") return 0
        if ((part[i] + 0) > 255) return 0
      }
      return 1
    }
    function refuse(text) { printf "%s\n", text > "/dev/stderr"; failed = 1 }
    NF == 0 { next }
    NF < 2 || NF > 3 {
      refuse(service " has a malformed network endpoint line: " $0)
      next
    }
    {
      name = $1
      v4 = $2
      v6 = (NF == 3 ? $3 : "")
      if (v4 == "invalid IP") v4 = ""
      if (v6 == "invalid IP") v6 = ""
      if (v6 != "") {
        if (index(declared, " " name " "))
          refuse(service " has an IPv6 address on its declared network " name "; refusing because declared networks disable IPv6")
        else
          refuse(service " has an IPv6 address on an extra network; refusing to leave it unfiltered")
        next
      }
      if (v4 == "") next
      if (!quad(v4)) {
        refuse(service " has an IPv4 address that is not a dotted quad on network " name ": " v4)
        next
      }
      if (index(declared, " " name " ")) next
      print v4
    }
    END { exit failed }
  '
}

injected_addresses() {
  # Every address the worker and PostgreSQL hold outside their declared networks. Fails loudly on any gap.
  docker info >/dev/null 2>&1 \
    || { echo "docker daemon is unreachable; cannot enforce the Coolify resource network" >&2; return 1; }
  derived=$(stack_project) || { echo "cannot inspect the fixed bridge labels" >&2; return 1; }
  set -- $derived
  project=$1
  present=$2
  if [ "$present" = 0 ]; then
    for service in execution-worker postgres; do
      if [ -n "$(docker ps --all --quiet --filter "label=com.docker.compose.service=$service")" ]; then
        echo "fixed bridges are absent but a $service container exists; refusing to guess the stack" >&2
        return 1
      fi
    done
    echo "no fixed bridges; nothing to enforce" >&2
    return 0
  fi
  [ "$project" != none ] \
    || { echo "a fixed bridge exists but has no compose project label" >&2; return 1; }
  if [ -n "${EDGE_OS_COMPOSE_PROJECT:-}" ] && [ "$EDGE_OS_COMPOSE_PROJECT" != "$project" ]; then
    echo "EDGE_OS_COMPOSE_PROJECT=$EDGE_OS_COMPOSE_PROJECT does not match the fixed bridge project $project" >&2
    return 1
  fi
  PROJECT=$project
  service_addresses execution-worker || return 1
  service_addresses postgres || return 1
}

flush_flows() {
  if ! out=$(conntrack -D -s "$1" 2>&1); then
    case "$out" in *"0 flow entries"*) ;; *) echo "conntrack flush failed: $out" >&2; return 1 ;; esac
  fi
}

enforce_injected_addresses() {
  # Drop forwarding to and from each injected address; keep host-bound traffic to established replies only.
  addresses=$(injected_addresses) || return 1
  fwd=$(build DOCKER-USER EDGE_OS_BYPASS)
  inbound=$(build INPUT EDGE_OS_BYPASS_IN)
  for ip in $addresses; do
    iptables -A "$fwd" -s "$ip" -j DROP
    iptables -A "$fwd" -d "$ip" -j DROP
    iptables -A "$inbound" -s "$ip" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    iptables -A "$inbound" -s "$ip" -j DROP
    flush_flows "$ip" || return 1
  done
  hook DOCKER-USER EDGE_OS_BYPASS "$fwd"
  hook INPUT EDGE_OS_BYPASS_IN "$inbound"
}

# Each rule set alternates between two chains, <name>_A and <name>_B. `build` returns the chain not hooked now, empty;
# `hook` jumps to it first and only then removes the old jump and chain, so the hook is never left without rules.
# An optional last argument names the table (default `filter`).
build() {
  hook=$1; name=$2; table=${3:-filter}
  next=${name}_A
  if iptables -t "$table" -C "$hook" -j "${name}_A" 2>/dev/null; then next=${name}_B; fi
  iptables -t "$table" -N "$next" 2>/dev/null || iptables -t "$table" -F "$next"
  echo "$next"
}

hook() {
  hook=$1; name=$2; next=$3; table=${4:-filter}
  iptables -t "$table" -I "$hook" 1 -j "$next"
  for old in "${name}_A" "${name}_B"; do
    [ "$old" = "$next" ] && continue
    while iptables -t "$table" -D "$hook" -j "$old" 2>/dev/null; do :; done
    if iptables -t "$table" -nL "$old" >/dev/null 2>&1; then
      iptables -t "$table" -F "$old"; iptables -t "$table" -X "$old"
    fi
  done
}

replies_only() {
  # replies_only <chain name> <bridge> <subnet> [relay]: INPUT from that bridge or subnet accepts replies and drops the
  # rest. With `relay`, it also accepts new TCP 443 to a relay address of this host: with Docker's default
  # `userland-proxy: true` a container's connection to a published port is not DNATed (Docker's per-bridge "skip DNAT"
  # rule) and reaches docker-proxy, which forwards it to Traefik.
  chain=$(build INPUT "$1")
  iptables -A "$chain" ! -i "$2" ! -s "$3" -j RETURN
  iptables -A "$chain" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  if [ "${4:-}" = relay ]; then
    iptables -A "$chain" -i "$2" -s "$3" -p tcp --dport 443 -m set --match-set "$RELAY_SET" dst -m addrtype --dst-type LOCAL -m conntrack --ctstate NEW -j ACCEPT
  fi
  iptables -A "$chain" -j DROP
  hook INPUT "$1" "$chain"
}

apply() {
  command -v conntrack >/dev/null 2>&1 || { echo "conntrack is required" >&2; exit 1; }
  servers=$(resolvers)
  [ -n "$servers" ] || { echo "no upstream resolver found" >&2; exit 1; }
  refresh_allowlist
  iptables -nL DOCKER-USER >/dev/null 2>&1 || iptables -N DOCKER-USER

  # The worker's new TCP 443 connections to a relay address, marked before Docker's DNAT rewrites the destination.
  mark=$(build PREROUTING EDGE_OS_RELAY_MARK mangle)
  iptables -t mangle -A "$mark" -i edgeos-egress -s "$EGRESS_SUBNET" -p tcp --dport 443 -m set --match-set "$RELAY_SET" dst -m conntrack --ctstate NEW -j CONNMARK --set-mark "$RELAY_MARK"
  hook PREROUTING EDGE_OS_RELAY_MARK "$mark" mangle

  # Forwarded traffic (DOCKER-USER is consulted first by Docker's FORWARD rules).
  fwd=$(build DOCKER-USER EDGE_OS_FWD)
  iptables -A "$fwd" -i edgeos-hostdb -j DROP
  iptables -A "$fwd" -o edgeos-hostdb -j DROP
  iptables -A "$fwd" -s "$HOSTDB_SUBNET" -j DROP
  iptables -A "$fwd" -d "$HOSTDB_SUBNET" -j DROP
  # The marked relay flow only: its replies, its later packets and its first packet once DNATed from port 443.
  # ACCEPT (not RETURN), so Docker's isolation between the egress and Coolify bridges does not drop it.
  iptables -A "$fwd" -o edgeos-egress -d "$EGRESS_SUBNET" -m connmark --mark "$RELAY_MARK" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  iptables -A "$fwd" -i edgeos-egress -s "$EGRESS_SUBNET" -m connmark --mark "$RELAY_MARK" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  iptables -A "$fwd" -i edgeos-egress -s "$EGRESS_SUBNET" -p tcp -m connmark --mark "$RELAY_MARK" -m conntrack --ctstate DNAT --ctorigdstport 443 -j ACCEPT
  iptables -A "$fwd" ! -i edgeos-egress ! -s "$EGRESS_SUBNET" -j RETURN
  iptables -A "$fwd" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  for server in $servers; do
    iptables -A "$fwd" -p udp -d "$server" --dport 53 -j RETURN
    iptables -A "$fwd" -p tcp -d "$server" --dport 53 -j RETURN
  done
  for port in $EDGE_OS_EGRESS_PORTS; do
    iptables -A "$fwd" -p tcp --dport "$port" -m set --match-set "$SET" dst -j RETURN
  done
  iptables -A "$fwd" -j DROP
  hook DOCKER-USER EDGE_OS_FWD "$fwd"

  # Traffic to the host itself (SSH, Coolify, the loopback database) from each bridge: replies only.
  replies_only EDGE_OS_IN edgeos-egress "$EGRESS_SUBNET" relay
  replies_only EDGE_OS_IN_DB edgeos-hostdb "$HOSTDB_SUBNET"
  replies_only EDGE_OS_IN_PRIVATE edgeos-private "$PRIVATE_SUBNET"

  # Connections opened before the rules existed must not survive on the ESTABLISHED allowance. "0 flow entries" is
  # not an error; any other conntrack failure is.
  for subnet in "${EGRESS_SUBNET%/*}" "${HOSTDB_SUBNET%/*}"; do
    if ! out=$(conntrack -D -s "$subnet" --mask-src 255.255.255.240 2>&1); then
      case "$out" in *"0 flow entries"*) ;; *) echo "conntrack flush failed: $out" >&2; exit 1 ;; esac
    fi
  done
}

# One run at a time, so two applies never build and flush the same idle chain.
exec 9>"$LOCK"
flock 9

case "${1:-}" in
  apply) apply ;;
  # `refresh` runs after Docker exists, so only it inspects containers. It never runs before Docker.
  refresh) refresh_allowlist; enforce_injected_addresses ;;
  *) echo "usage: $0 apply|refresh" >&2; exit 2 ;;
esac
