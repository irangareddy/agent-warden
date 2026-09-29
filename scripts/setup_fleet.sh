#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FLEET_DIR="$REPO_ROOT/fleet"
KEYS_DIR="$FLEET_DIR/keys"
NODES_FILE="$FLEET_DIR/nodes.txt"
FEDERATION="${FEDERATION:-agent-warden-demo}"

ROLES=(ios backend qa release)
NODE_NAMES=("Beet iOS Agent" "Beet Backend Agent" "Beet QA Agent" "Beet Release Agent")
NODE_LOCATIONS=(
  "37.4275,-122.1697"
  "37.4419,-122.1430"
  "37.3861,-122.0839"
  "37.3382,-121.8863"
)

fail() {
  printf 'setup_fleet.sh: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing prerequisite: $1"
}

node_id_for_role() {
  local role="$1"
  awk -F= -v wanted="$role" '$1 == wanted { print $2; exit }' "$NODES_FILE"
}

strip_ansi() {
  sed $'s/\033\[[0-9;]*m//g'
}

require_command docker
require_command uv
require_command openssl
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"

cd "$REPO_ROOT"

printf 'Checking Flower SuperGrid login...\n'
if ! federations_output="$(uv run flwr federation list supergrid 2>&1)"; then
  printf '%s\n' "$federations_output" >&2
  fail "Flower login check failed; run: uv run flwr login supergrid"
fi
federations_output="$(printf '%s\n' "$federations_output" | strip_ansi)"
account="$(printf '%s\n' "$federations_output" | sed -nE 's#.*@([^/[:space:]│|]+)/personal.*#\1#p' | sed -n '1p')"
[[ -n "$account" ]] || fail "could not derive the account from @<account>/personal"

umask 077
mkdir -p "$KEYS_DIR"
touch "$NODES_FILE"
chmod 600 "$NODES_FILE"

for index in "${!ROLES[@]}"; do
  private_key="$KEYS_DIR/supernode-$index"
  public_key="$private_key.pub"

  if [[ ! -f "$private_key" ]]; then
    printf 'Generating ECDSA-384 key pair for %s...\n' "${ROLES[$index]}"
    openssl ecparam -name secp384r1 -genkey -noout -out "$private_key"
    chmod 600 "$private_key"
  fi

  if [[ ! -f "$public_key" ]]; then
    openssl ec -in "$private_key" -pubout -out "$public_key" 2>/dev/null
    chmod 644 "$public_key"
  fi

  node_id="$(node_id_for_role "${ROLES[$index]}")"
  if [[ -z "$node_id" ]]; then
    printf 'Registering %s...\n' "${NODE_NAMES[$index]}"
    if ! register_output="$(uv run flwr supernode register \
      "$public_key" supergrid \
      --name="${NODE_NAMES[$index]}" \
      --location="${NODE_LOCATIONS[$index]}" 2>&1)"; then
      printf '%s\n' "$register_output" >&2
      fail "could not register ${NODE_NAMES[$index]}"
    fi
    register_output="$(printf '%s\n' "$register_output" | strip_ansi)"
    printf '%s\n' "$register_output"
    node_id="$(printf '%s\n' "$register_output" | sed -nE \
      's/.*SuperNode[[:space:]]+([^[:space:]]+)[[:space:]]+registered.*/\1/p' | sed -n '1p')"
    [[ -n "$node_id" ]] || fail "registration succeeded but no SuperNode ID was found"
    printf '%s=%s\n' "${ROLES[$index]}" "$node_id" >> "$NODES_FILE"
  else
    printf 'Reusing %s node ID %s.\n' "${ROLES[$index]}" "$node_id"
  fi
done

federation_ref="@$account/$FEDERATION"
if ! printf '%s\n' "$federations_output" | grep -Fq "$federation_ref"; then
  printf 'Creating federation %s...\n' "$federation_ref"
  uv run flwr federation create "$FEDERATION" supergrid \
    --description "Wagent four-node demo fleet"
else
  printf 'Reusing federation %s.\n' "$federation_ref"
fi

for index in "${!ROLES[@]}"; do
  node_id="$(node_id_for_role "${ROLES[$index]}")"
  printf 'Adding %s (%s) to %s...\n' "${NODE_NAMES[$index]}" "$node_id" "$federation_ref"
  if ! add_output="$(uv run flwr federation add-supernode \
    "$node_id" "$federation_ref" supergrid 2>&1)"; then
    if [[ "$add_output" == *already* || "$add_output" == *Already* || "$add_output" == *member* ]]; then
      printf 'Already present: %s\n' "${NODE_NAMES[$index]}"
    else
      printf '%s\n' "$add_output" >&2
      fail "could not add ${NODE_NAMES[$index]} to $federation_ref"
    fi
  else
    printf '%s\n' "$add_output"
  fi
done

if ! grep -Eq '^FLWR_MODEL_API_KEY=.+$' "$FLEET_DIR/.env" 2>/dev/null; then
  [[ -t 0 ]] || fail "FLWR_MODEL_API_KEY is missing and a hidden prompt needs a terminal"
  IFS= read -r -s -p 'Flower Model API key (input hidden): ' model_api_key
  printf '\n'
  [[ -n "$model_api_key" ]] || fail "the Flower Model API key cannot be empty"
  printf 'FLWR_MODEL_API_KEY=%s\n' "$model_api_key" > "$FLEET_DIR/.env"
  chmod 600 "$FLEET_DIR/.env"
else
  printf 'Reusing FLWR_MODEL_API_KEY from fleet/.env.\n'
fi

cp "$FLEET_DIR/data/backend/demo.env.fake" "$FLEET_DIR/data/backend/.env"
chmod 600 "$FLEET_DIR/data/backend/.env"

printf 'Building the warmed SuperNode image...\n'
docker compose -f "$FLEET_DIR/compose.yaml" build

printf '\nFleet setup complete. Start it from the repository root with:\n'
printf 'docker compose -f fleet/compose.yaml up\n'
