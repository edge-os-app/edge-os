#!/bin/sh
# Edge OS host firewall for the two Compose bridges in compose.coolify.yml (iptables backend, IPv4).
#
#   edgeos-egress  the execution worker's only route out: DNS to the host's upstream resolvers and TCP to the
#                  resolved addresses of EDGE_OS_EGRESS_HOSTS on EDGE_OS_EGRESS_PORTS. Everything else is dropped.
#   edgeos-hostdb  PostgreSQL's loopback publish: nothing is forwarded in or out, and only replies reach the host.
#   edgeos-private the internal service network: only replies reach the host (its gateway must not expose SSH or
#                  Coolify to the containers).
#
# Every rule matches the bridge name or its fixed subnet, so a bridge renamed by a later edit is still filtered.
#
# Docker cannot restrict by host name; this script resolves the names on the host into an ipset. `apply` builds the
# rules in the idle one of two chains and switches the jump to it, so a re-run never leaves an empty chain hooked.
# `refresh` only adds addresses with a timeout; an empty answer never clears the set (it fails closed when entries
# expire).
#
# Configuration: /etc/edge-os/egress.env (root:root 0600), for example
#   EDGE_OS_EGRESS_HOSTS="api.privy.io <Monad RPC host from the approved execution release>"
#   EDGE_OS_EGRESS_PORTS="443"
# See docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md §4.
set -eu

CONFIG=${EDGE_OS_EGRESS_CONFIG:-/etc/edge-os/egress.env}
# shellcheck disable=SC1090
. "$CONFIG"
: "${EDGE_OS_EGRESS_HOSTS:?set EDGE_OS_EGRESS_HOSTS in $CONFIG}"
EDGE_OS_EGRESS_PORTS=${EDGE_OS_EGRESS_PORTS:-443}
SET=edgeos-egress-allow
TTL=900
EGRESS_SUBNET=10.203.0.0/28
HOSTDB_SUBNET=10.203.0.16/28
PRIVATE_SUBNET=10.203.0.64/26
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

refresh() {
  ipset create "$SET" hash:ip family inet timeout "$TTL" -exist
  for host in $EDGE_OS_EGRESS_HOSTS; do
    getent ahostsv4 "$host" | awk '{print $1}' | sort -u | while read -r ip; do
      ipset -exist add "$SET" "$ip" timeout "$TTL"
    done
  done
}

# Each rule set alternates between two chains, <name>_A and <name>_B. `build` returns the chain not hooked now, empty;
# `hook` jumps to it first and only then removes the old jump and chain, so the hook is never left without rules.
build() {
  hook=$1; name=$2
  next=${name}_A
  if iptables -C "$hook" -j "${name}_A" 2>/dev/null; then next=${name}_B; fi
  iptables -N "$next" 2>/dev/null || iptables -F "$next"
  echo "$next"
}

hook() {
  hook=$1; name=$2; next=$3
  iptables -I "$hook" 1 -j "$next"
  for old in "${name}_A" "${name}_B"; do
    [ "$old" = "$next" ] && continue
    while iptables -D "$hook" -j "$old" 2>/dev/null; do :; done
    if iptables -nL "$old" >/dev/null 2>&1; then iptables -F "$old"; iptables -X "$old"; fi
  done
}

replies_only() {
  # replies_only <chain name> <bridge> <subnet>: INPUT from that bridge or subnet accepts replies and drops the rest.
  chain=$(build INPUT "$1")
  iptables -A "$chain" ! -i "$2" ! -s "$3" -j RETURN
  iptables -A "$chain" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  iptables -A "$chain" -j DROP
  hook INPUT "$1" "$chain"
}

apply() {
  command -v conntrack >/dev/null 2>&1 || { echo "conntrack is required" >&2; exit 1; }
  servers=$(resolvers)
  [ -n "$servers" ] || { echo "no upstream resolver found" >&2; exit 1; }
  refresh
  iptables -nL DOCKER-USER >/dev/null 2>&1 || iptables -N DOCKER-USER

  # Forwarded traffic (DOCKER-USER is consulted first by Docker's FORWARD rules).
  fwd=$(build DOCKER-USER EDGE_OS_FWD)
  iptables -A "$fwd" -i edgeos-hostdb -j DROP
  iptables -A "$fwd" -o edgeos-hostdb -j DROP
  iptables -A "$fwd" -s "$HOSTDB_SUBNET" -j DROP
  iptables -A "$fwd" -d "$HOSTDB_SUBNET" -j DROP
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
  replies_only EDGE_OS_IN edgeos-egress "$EGRESS_SUBNET"
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
  refresh) refresh ;;
  *) echo "usage: $0 apply|refresh" >&2; exit 2 ;;
esac
