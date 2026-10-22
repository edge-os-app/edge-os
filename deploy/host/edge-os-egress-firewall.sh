#!/bin/sh
# Edge OS host firewall for the two Compose bridges in compose.coolify.yml (iptables backend, IPv4).
#
#   edgeos-egress  the execution worker's only route out: DNS to the host's upstream resolvers and TCP to the
#                  resolved addresses of EDGE_OS_EGRESS_HOSTS on EDGE_OS_EGRESS_PORTS. Everything else is dropped.
#   edgeos-hostdb  PostgreSQL's loopback publish: nothing is forwarded out and nothing reaches the host except replies.
#
# Docker cannot restrict by host name; this script resolves the names on the host into an ipset. `apply` builds the
# rules in the idle one of two chains and switches the jump to it, so a re-run never leaves an empty chain hooked. `refresh` only
# adds addresses with a timeout; an empty answer never clears the set (it fails closed when entries expire).
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

resolvers() {
  # The file Docker reads when the host runs systemd-resolved; otherwise /etc/resolv.conf. Loopback stubs excluded.
  file=/etc/resolv.conf
  [ -f /run/systemd/resolve/resolv.conf ] && file=/run/systemd/resolve/resolv.conf
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

apply() {
  servers=$(resolvers)
  [ -n "$servers" ] || { echo "no upstream resolver found" >&2; exit 1; }
  refresh
  iptables -nL DOCKER-USER >/dev/null 2>&1 || iptables -N DOCKER-USER

  # Forwarded traffic (DOCKER-USER is consulted first by Docker's FORWARD rules).
  fwd=$(build DOCKER-USER EDGE_OS_FWD)
  iptables -A "$fwd" -i edgeos-hostdb -j DROP
  iptables -A "$fwd" ! -i edgeos-egress -j RETURN
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

  # Traffic to the host itself (SSH, Coolify, the loopback database) from either bridge: replies only.
  in_egress=$(build INPUT EDGE_OS_IN)
  iptables -A "$in_egress" ! -i edgeos-egress -j RETURN
  iptables -A "$in_egress" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  iptables -A "$in_egress" -j DROP
  hook INPUT EDGE_OS_IN "$in_egress"
  in_db=$(build INPUT EDGE_OS_IN_DB)
  iptables -A "$in_db" ! -i edgeos-hostdb -j RETURN
  iptables -A "$in_db" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  iptables -A "$in_db" -j DROP
  hook INPUT EDGE_OS_IN_DB "$in_db"

  # Connections opened before the rules existed must not survive on the ESTABLISHED allowance.
  if command -v conntrack >/dev/null 2>&1; then conntrack -D -s "$EGRESS_SUBNET" >/dev/null 2>&1 || true; fi
}

case "${1:-}" in
  apply) apply ;;
  refresh) refresh ;;
  *) echo "usage: $0 apply|refresh" >&2; exit 2 ;;
esac
