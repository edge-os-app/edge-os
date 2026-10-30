#!/bin/sh
# Public smoke test for an Edge OS Coolify deployment. Read-only: it changes nothing.
#
# Usage:
#   WEB_ORIGIN=https://app.edgeos.fun API_ORIGIN=https://api.edgeos.fun \
#   NEXT_PUBLIC_PRIVY_APP_ID=<public app id> deploy/coolify/smoke_public.sh
#
# Requires curl and python3. It fails closed on the first missing answer.

set -eu

WEB_ORIGIN=${WEB_ORIGIN:?set WEB_ORIGIN to the public web origin}
API_ORIGIN=${API_ORIGIN:?set API_ORIGIN to the public API origin}
PRIVY_APP_ID=${NEXT_PUBLIC_PRIVY_APP_ID:-}

case "$WEB_ORIGIN" in https://*) ;; *) printf 'FAIL WEB_ORIGIN must use https\n' >&2; exit 1 ;; esac
case "$API_ORIGIN" in https://*) ;; *) printf 'FAIL API_ORIGIN must use https\n' >&2; exit 1 ;; esac

fail() {
    printf 'FAIL %s\n' "$1" >&2
    exit 1
}

json_field() {
    # $1: JSON text, $2: field name. Prints the value or an empty string.
    python3 -c 'import json,sys
try:
    value = json.loads(sys.argv[1]).get(sys.argv[2], "")
except Exception:
    value = ""
print(value if isinstance(value, str) else "")' "$1" "$2"
}

health=$(curl -fsS --max-time 10 "$API_ORIGIN/healthz") || fail "GET $API_ORIGIN/healthz"
status=$(json_field "$health" status)
sha=$(json_field "$health" build_sha)
[ "$status" = "ok" ] || fail "healthz status is not ok"
[ -n "$sha" ] || fail "healthz build_sha is empty"
printf 'PASS healthz status=ok build_sha=%s\n' "$sha"

ready=$(curl -fsS --max-time 10 "$API_ORIGIN/readyz") || fail "GET $API_ORIGIN/readyz"
ready_status=$(json_field "$ready" status)
revision=$(json_field "$ready" schema_revision)
[ "$ready_status" = "ready" ] || fail "readyz status is not ready"
[ -n "$revision" ] || fail "readyz schema_revision is empty"
printf 'PASS readyz status=ready schema_revision=%s\n' "$revision"

web=$(curl -fsS --max-time 10 "$WEB_ORIGIN/") || fail "GET $WEB_ORIGIN/"
printf '%s' "$web" | grep -q '_next' || fail "the web origin did not serve a Next.js page"
printf 'PASS web origin serves the application\n'

headers=$(mktemp)
trap 'rm -f "$headers"' EXIT HUP INT TERM
curl -sS --max-time 10 -o /dev/null -D "$headers" -X OPTIONS "$API_ORIGIN/v1/me" \
    -H "Origin: $WEB_ORIGIN" \
    -H "Access-Control-Request-Method: GET" || fail "OPTIONS preflight"
grep -qi "^Access-Control-Allow-Origin: *$WEB_ORIGIN" "$headers" \
    || fail "the CORS preflight did not allow $WEB_ORIGIN"
printf 'PASS CORS preflight allows %s\n' "$WEB_ORIGIN"

if [ -n "$PRIVY_APP_ID" ]; then
    found=0
    for asset in $(printf '%s' "$web" | grep -o '/_next/static/[^"]*\.js' | sort -u); do
        if curl -fsS --max-time 10 "$WEB_ORIGIN$asset" | grep -q "$PRIVY_APP_ID"; then
            found=1
            break
        fi
    done
    [ "$found" = "1" ] || fail "the Privy app id is not in a built JavaScript asset"
    printf 'PASS the web bundle carries the Privy app id\n'
else
    printf 'SKIP Privy bundle check (set NEXT_PUBLIC_PRIVY_APP_ID to enable it)\n'
fi

printf 'MANUAL add %s to the Privy allowed origins, then sign in once\n' "$WEB_ORIGIN"
