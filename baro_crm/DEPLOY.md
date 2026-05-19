# Deploying baro_crm to the Florida ERPNext server

This walks through deploying the `baro_crm` Frappe app from your Windows workstation to the self-hosted ERPNext on `100.127.172.110` (Tailscale).

> **Before you start — rotate your API credentials.** They were exposed in chat earlier; treat them as compromised. Generate new API key/secret in ERPNext → User → Settings, then update your local `.env` via `scripts/set_api_token_from_clipboard.ps1`. The cockpit doesn't use API tokens (uses session cookie auth), but other tools in this project do.

---

## Prereqs

- Tailscale up and connected to the Florida server (verify: `ping 100.127.172.110`).
- SSH access as `admin1`: `ssh admin1@100.127.172.110`.
- `frappe_docker` is the deployment compose (per `Self Hosting Florida Plan.md`).
- The current site name in `pwd.yml` is `frontend` (the default).

---

## Step 1 — Copy `baro_crm` to the server

From PowerShell on your workstation:

```powershell
$src = "C:\Users\epmek\Documents\Erpnext Baro\baro_crm"
# scp the folder via Tailscale
scp -r $src admin1@100.127.172.110:/home/admin1/
```

Or, if you prefer rsync (works from WSL/Git Bash):

```bash
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  "/c/Users/epmek/Documents/Erpnext Baro/baro_crm/" \
  admin1@100.127.172.110:/home/admin1/baro_crm/
```

---

## Step 2 — Run the install script on the server

SSH in:

```bash
ssh admin1@100.127.172.110
cd ~/baro_crm
chmod +x install.sh
./install.sh
```

The script is idempotent — safe to re-run. It will:

1. Copy `baro_crm/` into the `backend` container's `apps/` directory.
2. Pip-install the app in editable mode.
3. Run `bench install-app baro_crm` on site `frontend`.
4. Run `bench migrate` — this fires `patches/v0_0_1/backfill_state.py` and creates the `service_state` Custom Field on Repair Job.
5. Build frontend assets and clear caches.

Total time: ~60–90 seconds on the i5-4570.

---

## Step 3 — Verify

Open in a browser (must be on Tailscale):

```
http://100.127.172.110:8080/repair-jobs
```

You should land on the cockpit, signed in as whoever you logged into ERPNext as. The state tabs at the top should show counts per state (TX/FL/NY/NJ). Rows should be your real Repair Jobs.

To verify the new field via API on the server:

```bash
docker compose -f ~/frappe_docker/pwd.yml exec backend bash -lc \
  "cd /home/frappe/frappe-bench && bench --site frontend execute \
   \"frappe.get_doc('Custom Field','Repair Job-service_state').as_json()\""
```

---

## Step 4 — First quick smoke test (do this once, manually)

1. Open the cockpit. Confirm the table loads with your existing 9-ish Repair Jobs.
2. Click any state tab → list filters server-side.
3. Click a row → inspector opens.
4. Click a field value (e.g., **Symptom**) → it becomes an input. Type, blur. Watch for the green "Saved" flash.
5. Switch to the **Timeline** tab → you should see the field change as a "k-change" entry, freshly logged.
6. Type a comment in the composer → "Add comment" → comment appears immediately.
7. Click the status pill → pick a workflow action → status updates. Timeline shows it.
8. Open the same job in a second browser tab → edit there → watch the first tab update via realtime within ~600 ms.

If any of those fail, see "Troubleshooting" below.

---

## Updating (after code changes)

```powershell
# From workstation
rsync -av --delete --exclude='.git' --exclude='__pycache__' \
  "/c/Users/epmek/Documents/Erpnext Baro/baro_crm/" \
  admin1@100.127.172.110:/home/admin1/baro_crm/
```

Then on the server:
```bash
cd ~/baro_crm
./install.sh   # re-running is safe
```

If you only changed CSS/JS, you can skip `migrate` and just:
```bash
docker compose -f ~/frappe_docker/pwd.yml exec backend bash -lc \
  "cd /home/frappe/frappe-bench && bench build --app baro_crm && bench --site frontend clear-cache"
```

---

## Rollback

Uninstall (data preserved):

```bash
docker compose -f ~/frappe_docker/pwd.yml exec backend bash -lc \
  "cd /home/frappe/frappe-bench && bench --site frontend uninstall-app baro_crm"
```

This removes the cockpit page, the workspace shortcut, and the `service_state` Custom Field. **Repair Job data is untouched.**

To also remove the API code from the bench:
```bash
docker compose -f ~/frappe_docker/pwd.yml exec backend bash -lc \
  "rm -rf /home/frappe/frappe-bench/apps/baro_crm && \
   cd /home/frappe/frappe-bench && sed -i '/^baro_crm$/d' sites/apps.txt"
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/repair-jobs` returns 404 | `bench build` and `clear-cache` didn't run | Re-run `./install.sh` (re-runs all steps) |
| Page loads but stays on "Loading repair workspace…" | JS error or API method missing | Browser devtools console; check `apps/baro_crm` exists in container |
| Status pill change does nothing | User lacks role for that workflow transition | Check Workflow → Repair Job Workflow transitions; assign user a Baro role profile |
| Inline edit "Save failed: Not permitted" | User has read but not write on Repair Job | Assign a Baro role profile with write |
| Timeline shows nothing | `track_changes` not enabled on Repair Job | Open DocType `Repair Job` → enable Track Changes (already on in our config but worth confirming) |
| Field changes don't show in Timeline tab | Version log records lag a moment | Refresh — Frappe writes to `Version` after `doc.save()` returns |
| `service_state` counts show 0 for all states | Backfill patch didn't run | `bench --site frontend migrate` again, watch for `backfill_state:` log line |
| 504 / connection refused | Tailscale link down, or container restarting | `docker compose -f ~/frappe_docker/pwd.yml ps`, restart `backend` if needed |

---

## Third-party dependencies

| Package | Version | License | Source |
|---|---|---|---|
| SortableJS | 1.15.6 | MIT | https://github.com/SortableJS/Sortable/releases/tag/1.15.6 — vendored in `baro_crm/baro_crm/public/vendor/Sortable.min.js`. Upstream license copied to `LICENSE-Sortable.txt` in the same folder. SHA-256: `6d0a831fc19b4bae851797ad3393157e861afb7862459c11226359b27e2c4337` |

We deliberately do **not** depend on npm or any build step. `bench build` requires Node.js, which is not installed in the backend container of this `pwd.yml` setup.

To upgrade SortableJS:

1. Replace `Sortable.min.js` and `LICENSE-Sortable.txt` from the new release.
2. Update the version and SHA-256 in this table.
3. Re-run `./install.sh` on the server.
4. Re-run all 14 manual browser tests from the design spec.

## Asset verification

`install.sh` step 5/6 materializes baro_crm assets as **real files** under `sites/assets/baro_crm/` (not a symlink) and verifies them three ways:

1. Real-file presence at the expected paths.
2. Each file ≥100 bytes (catches empty/broken downloads).
3. HTTP 200 via the Docker-internal DNS name `frontend:8080` — the actual nginx the browser hits, not gunicorn on `localhost:8080`.

If step 5/6 fails:

| Failure | Likely cause | Fix |
|---|---|---|
| `FAIL source assets missing at apps/baro_crm/baro_crm/public` | docker cp didn't put source in the right place | Re-run install.sh from start; step 1 wipes and re-copies |
| `FAIL <file> is a symlink` | Something restored the old symlink between step 5 and step 5/6 (unlikely) | Re-run install.sh from step 5 |
| `FAIL <file> is N bytes` for N < 100 | File was empty in source | Check the source file on your laptop; re-sync the project folder |
| `FAIL <path> → HTTP 404 (via http://frontend:8080...)` | nginx isn't serving the dir OR FRONTEND_SVC is wrong | Run `docker compose -f ~/frappe_docker/pwd.yml ps` — confirm nginx-serving service is named `frontend`. If different, run with `BARO_FRONTEND_SVC=nginx ./install.sh` |
| `FAIL <path> → HTTP 502` | nginx is up but upstream is down | `docker compose -f ~/frappe_docker/pwd.yml restart backend` and retry |

---

## Files modified on the server

After install, only these locations are touched:

- `/home/frappe/frappe-bench/apps/baro_crm/` — the app source
- `/home/frappe/frappe-bench/sites/apps.txt` — app registered
- Site DB → `tabCustom Field` → 1 new row (`Repair Job-service_state`)
- Site DB → `tabRepair Job` → `service_state` column added, backfilled where possible
- Site DB → `tabPatch Log` → 1 new entry (`baro_crm.patches.v0_0_1.backfill_state`)

Everything else in your ERPNext site is unchanged.
