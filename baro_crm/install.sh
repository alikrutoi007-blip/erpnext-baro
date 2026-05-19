#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# baro_crm — server-side install script
#
# Run on the Florida ERPNext server after rsync/scp has dropped this folder at:
#     /home/admin1/baro_crm
# (or wherever you place it — set BARO_APP_SRC to override).
#
# What it does (idempotent):
#   1. Copies the app source into the bench's apps/ directory inside the
#      frappe_docker backend container.
#   2. Runs `bench get-app` / `install-app` for the target site.
#   3. Runs `bench migrate` so the service_state Custom Field + patch apply.
#   4. Builds frontend assets and clears cache.
#
# Required env (override if your setup differs):
#   BARO_APP_SRC    — Host path to this folder. Default: $(pwd) of this script.
#   BARO_SITE       — Frappe site name. Default: frontend (frappe_docker pwd.yml).
#   BARO_COMPOSE    — Compose file. Default: ~/frappe_docker/pwd.yml.
#   BARO_BENCH_PATH — In-container bench path. Default: /home/frappe/frappe-bench.
# -----------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BARO_APP_SRC="${BARO_APP_SRC:-$SCRIPT_DIR}"
BARO_SITE="${BARO_SITE:-frontend}"
BARO_COMPOSE="${BARO_COMPOSE:-$HOME/frappe_docker/pwd.yml}"
BARO_BENCH_PATH="${BARO_BENCH_PATH:-/home/frappe/frappe-bench}"

if [[ ! -d "$BARO_APP_SRC/baro_crm" ]]; then
  echo "ERROR: BARO_APP_SRC ($BARO_APP_SRC) does not look like a baro_crm folder." >&2
  echo "       Expected a sibling 'baro_crm/' Python package." >&2
  exit 1
fi
if [[ ! -f "$BARO_COMPOSE" ]]; then
  echo "ERROR: compose file not found at $BARO_COMPOSE." >&2
  echo "       Set BARO_COMPOSE to your frappe_docker compose file." >&2
  exit 1
fi

say() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }

say "1/6 · Copying baro_crm into backend container"
# Wipe any prior copy first.
# `docker cp` into an existing dir nests source INSIDE it, leaving stale files
# at the top level — that bit us on the first re-run. Clean slate every time.
docker compose -f "$BARO_COMPOSE" exec -T backend bash -lc \
  "rm -rf '$BARO_BENCH_PATH/apps/baro_crm'"
docker compose -f "$BARO_COMPOSE" cp \
  "$BARO_APP_SRC" \
  "backend:$BARO_BENCH_PATH/apps/baro_crm"
# Verify what landed (helpful when something is off)
docker compose -f "$BARO_COMPOSE" exec -T backend bash -lc \
  "head -3 '$BARO_BENCH_PATH/apps/baro_crm/pyproject.toml' && echo '---' && ls '$BARO_BENCH_PATH/apps/baro_crm/' | head -20"

say "2/6 · Installing baro_crm into bench's Python environment"
# IMPORTANT: bench has its own Python (often a venv at ./env/). The plain
# `pip` on PATH is the SYSTEM Python — installs there go to user site-
# packages and bench can't see them, causing 'ModuleNotFoundError: baro_crm'
# at install-app time. We must use bench's pip explicitly.
docker compose -f "$BARO_COMPOSE" exec -T backend bash <<'BENCH_INSTALL_EOF'
set -e
cd /home/frappe/frappe-bench

# Pick the right pip
if [ -x ./env/bin/pip ]; then
  PIP_CMD="./env/bin/pip"
  PY_CMD="./env/bin/python"
  echo "▸ Using bench venv: $PIP_CMD"
elif command -v bench >/dev/null 2>&1; then
  PIP_CMD="bench pip"
  PY_CMD="python"
  echo "▸ Using bench pip wrapper"
else
  PIP_CMD="python -m pip"
  PY_CMD="python"
  echo "▸ WARNING: falling back to system pip (likely won't work)"
fi

$PIP_CMD install -e apps/baro_crm

# Register the app with the bench
grep -qxF 'baro_crm' sites/apps.txt || echo 'baro_crm' >> sites/apps.txt

# Verify bench's Python can actually import it (this is what step 3 needs)
echo "▸ Verifying import with $PY_CMD..."
$PY_CMD -c "import baro_crm; print('  baro_crm OK from:', baro_crm.__file__)"
BENCH_INSTALL_EOF

say "3/6 · Installing baro_crm on site '$BARO_SITE'"
docker compose -f "$BARO_COMPOSE" exec -T backend bash -lc "
  cd $BARO_BENCH_PATH
  if bench --site $BARO_SITE list-apps | grep -qxF baro_crm; then
    echo 'baro_crm already installed — skipping install-app'
  else
    bench --site $BARO_SITE install-app baro_crm
  fi
"

say "4/6 · Running migrations (custom field + backfill patch)"
docker compose -f "$BARO_COMPOSE" exec -T backend bash -lc "
  cd $BARO_BENCH_PATH
  bench --site $BARO_SITE migrate
"

say "5/6 · Building frontend assets"
docker compose -f "$BARO_COMPOSE" exec -T backend bash -lc "
  cd $BARO_BENCH_PATH
  bench build --app baro_crm || true   # build can be optional in dev
"

say "6/6 · Clearing cache"
docker compose -f "$BARO_COMPOSE" exec -T backend bash -lc "
  cd $BARO_BENCH_PATH
  bench --site $BARO_SITE clear-cache
  bench --site $BARO_SITE clear-website-cache
"

cat <<EOF

✓ Install complete.

Open the cockpit:
    http://100.127.172.110:8080/repair-jobs

Verify the custom field landed:
    docker compose -f $BARO_COMPOSE exec backend bash -lc \\
      "cd $BARO_BENCH_PATH && bench --site $BARO_SITE execute \\
       \"frappe.get_doc('Custom Field','Repair Job-service_state').as_json()\""

Rollback (uninstall):
    docker compose -f $BARO_COMPOSE exec backend bash -lc \\
      "cd $BARO_BENCH_PATH && bench --site $BARO_SITE uninstall-app baro_crm"

EOF
