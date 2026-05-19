# Kanban drag/drop in baro_crm cockpit — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add drag-and-drop on the cockpit kanban so users can advance Repair Jobs through the workflow by dragging cards between group columns. Every drag routes through `baro_crm.api.repair_job.change_status` (no raw status writes), with confirm-modal protection for destructive transitions and full Esc-cancel support. **Pre-requisite: the cockpit must first gain a Kanban view — the deployed `cockpit.js` only ships the list view.**

**Architecture:** Vendored SortableJS v1.15.6 inside `baro_crm/public/vendor/`. Drag logic stays inline in `cockpit.js` (single-file, no separate `cockpit-drag.js` — removes load-order risk). Optimistic DOM moves for normal single-action drops with rollback on API error. Multi-action and destructive drops revert the optimistic move first, then route through the existing status popover (defensively re-scoped so its delegated click handler doesn't fire twice) and a new confirm dialog (appended **inside** `.baro-cockpit` so the namespaced CSS applies) before any API call.

**Tech Stack:** Vanilla JS (existing cockpit.js style), SortableJS 1.15.6 (MIT, vendored), Frappe v15 REST API via `frappe.call`, existing Frappe workflow engine (`change_status` → `apply_workflow`), Docker Compose deploy via existing `install.sh`.

**Source spec:** `docs/superpowers/specs/2026-05-20-kanban-drag-drop-design.md` (approved 2026-05-20).

---

## File structure

### Files created

| Path | Purpose | Approx size |
|---|---|---|
| `baro_crm/baro_crm/public/vendor/Sortable.min.js` | Vendored UMD build of SortableJS 1.15.6 | ~12 KB |
| `baro_crm/baro_crm/public/vendor/LICENSE-Sortable.txt` | Upstream MIT license text | ~1 KB |

### Files modified

| Path | What changes |
|---|---|
| `baro_crm/baro_crm/www/repair-jobs.html` | Add 1 `<script>` tag for Sortable, BEFORE the existing cockpit.js tag |
| `baro_crm/baro_crm/public/css/cockpit.css` | Add ~220 lines: view-switch, kanban layout, drag visual states, confirm modal, empty-column placeholder |
| `baro_crm/baro_crm/public/js/cockpit.js` | Add ~450 lines: `activeView` state field, view-switch UI in shell, kanban container, `renderKanban()`, view-switch event, then drag-handle markup, drag constants, helpers, SortableJS init, all drop-path handlers, Esc-cancel, defensive scoping of the existing pop-item handler |
| `baro_crm/install.sh` | Replace step 5b with materialize-as-real-files + nginx-via-`frontend:8080` smoke test |
| `baro_crm/DEPLOY.md` | Add "Third-party dependencies" and "Asset verification" sections |

### Outside files touched

- `.git/` — initialized at the project root since the project isn't currently versioned. Protects the work, gives per-task commits.

---

## Phases and checkpoints

5 phases. **At each checkpoint, the implementer pauses and waits for the user to confirm before continuing.**

| Phase | Tasks | Deliverable | Checkpoint |
|---|---|---|---|
| A. Foundation | T1–T6 | Sortable vendored, install.sh updated, deploys cleanly with all asset smoke tests green | T6 |
| B. Kanban view foundation | T7–T11 | Cockpit gains a Kanban view-switcher and renders cards by group column. No drag yet. | T11 |
| C. Drag-ready card markup + CSS scaffolding | T12–T17 | Cards have left grip handle + body; every drag visual state defined in CSS but not wired | T17 |
| D. Drag mechanics + API integration | T18–T27 | Full drag/drop: happy path, multi-action popover, destructive confirm, Esc cancel | T27 |
| E. Tablet acceptance + sign-off | T28–T30 | iPad checks, screenshots, roadmap mark-shipped | none — sign-off |

---

## Phase A — Foundation

### Task 1: Initialize git at project root with baseline commit

**Files:**
- Create: `C:\Users\epmek\Documents\Erpnext Baro\.gitignore`

The project at `C:\Users\epmek\Documents\Erpnext Baro` is not currently a git repository. We initialize one now so every subsequent task can produce a real commit. Existing `.env` and log files must be gitignored before the first commit.

- [ ] **Step 1: Verify project root is not yet a git repo**

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
Test-Path .git -PathType Container
```

Expected: `False`. If `True`, skip to step 4.

- [ ] **Step 2: Create the .gitignore**

Create `C:\Users\epmek\Documents\Erpnext Baro\.gitignore`:

```
# Secrets — must never be committed
.env
*.env.local

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/

# Logs
logs/*.log
logs/*.jsonl

# OS
.DS_Store
Thumbs.db

# Editor
.vscode/
.idea/
*.swp

# Virtualenv (lives outside the project but listed for safety)
.venv/
```

- [ ] **Step 3: Init the repo and stage everything except secrets**

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
git init
git branch -M main
git add .gitignore
git add .
git status --short | Select-String "\.env"
```

The last line must produce no output. If `.env` appears in the status, **stop** and fix the .gitignore first.

- [ ] **Step 4: Baseline commit + tag**

```powershell
git commit -m "chore: initialize repository with .gitignore"
git tag pre-kanban-dnd
git log --oneline -1
```

Expected: one line showing the commit hash, `(HEAD -> main, tag: pre-kanban-dnd)`, and the message.

---

### Task 2: Vendor SortableJS 1.15.6

**Files:**
- Create: `baro_crm/baro_crm/public/vendor/Sortable.min.js`
- Create: `baro_crm/baro_crm/public/vendor/LICENSE-Sortable.txt`

- [ ] **Step 1: Ensure the vendor directory exists**

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
New-Item -ItemType Directory -Force -Path "baro_crm\baro_crm\public\vendor" | Out-Null
```

- [ ] **Step 2: Download Sortable.min.js v1.15.6 from jsdelivr**

```powershell
$dest = "baro_crm\baro_crm\public\vendor\Sortable.min.js"
Invoke-WebRequest -Uri "https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js" -OutFile $dest
```

- [ ] **Step 3: Verify the file is real and reasonable size**

```powershell
$file = Get-Item "baro_crm\baro_crm\public\vendor\Sortable.min.js"
Write-Output "Size: $($file.Length) bytes"
Get-FileHash -Algorithm SHA256 $file.FullName
```

Expected: size between 40000 and 70000 bytes. **Record the SHA256** — you'll paste it into DEPLOY.md in Task 5. If size < 10 KB, the download failed silently — re-run step 2.

- [ ] **Step 4: Download the upstream MIT license**

```powershell
$lic = "baro_crm\baro_crm\public\vendor\LICENSE-Sortable.txt"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/SortableJS/Sortable/master/LICENSE" -OutFile $lic
Get-Content $lic | Select-Object -First 3
```

Expected first 3 lines roughly:
```
The MIT License (MIT)

Copyright (c) 2019-2020 All contributors to Sortable
```

If you get HTML or 404 content, fetch manually from https://github.com/SortableJS/Sortable/blob/master/LICENSE and save the plain-text copy.

- [ ] **Step 5: Commit**

```powershell
git add baro_crm/baro_crm/public/vendor/
git commit -m "chore(baro_crm): vendor SortableJS 1.15.6 with MIT license"
```

---

### Task 3: Add SortableJS script tag to repair-jobs.html

**Files:**
- Modify: `baro_crm/baro_crm/www/repair-jobs.html`

- [ ] **Step 1: Find the existing cockpit.js script tag**

Open `baro_crm/baro_crm/www/repair-jobs.html`. Find:

```html
<script src="/assets/baro_crm/js/cockpit.js" defer></script>
```

- [ ] **Step 2: Add Sortable BEFORE cockpit.js**

Replace that one-line `<script>` with both, in this exact order:

```html
<script src="/assets/baro_crm/vendor/Sortable.min.js" defer></script>
<script src="/assets/baro_crm/js/cockpit.js" defer></script>
```

`defer` on both ensures document-order execution. Sortable's `window.Sortable` global will be defined before cockpit.js's IIFE runs.

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/www/repair-jobs.html
git commit -m "feat(cockpit): load SortableJS before cockpit.js in repair-jobs template"
```

---

### Task 4: Rewrite install.sh step 5 — materialize assets as real files + nginx smoke

**Files:**
- Modify: `baro_crm/install.sh`

Symlinked assets have produced 404s. The new step 5 (a) replaces `sites/assets/baro_crm` with a real directory of copied files, (b) verifies each file is real (not a symlink) and ≥100 bytes, (c) curls through nginx via Docker DNS name `frontend:8080`. **Crucial**: do NOT use `localhost:8080` from inside the backend container — that resolves to gunicorn, not nginx, and gunicorn doesn't serve `/assets/*`.

- [ ] **Step 1: Find the existing `say "5/6 · ..."` block**

Open `baro_crm/install.sh`. Find the line `say "5/6 · Building frontend assets"` and locate the end of that step (the closing `'` of its docker compose invocation).

- [ ] **Step 2: Replace the entire step 5 block with this**

```bash
say "5/6 · Materializing baro_crm assets as real files + verifying via nginx"
# Symlink-only assets have produced 404s here. We replace any prior
# sites/assets/baro_crm with a REAL directory of copied files, then
# smoke-test via the actual nginx the browser hits (Docker DNS: frontend:8080),
# NOT localhost:8080 — inside the backend container that's gunicorn, which
# does not serve /assets/.
docker compose -f "$BARO_COMPOSE" exec -T backend bash <<'ASSET_CHECK_EOF'
set -e
cd /home/frappe/frappe-bench

ASSET_DIR=sites/assets/baro_crm
SRC_DIR=apps/baro_crm/baro_crm/public

if [ ! -d "$SRC_DIR" ]; then
  echo "FAIL source assets missing at $SRC_DIR"
  exit 1
fi

rm -rf "$ASSET_DIR"
mkdir -p "$ASSET_DIR"
cp -R "$SRC_DIR"/* "$ASSET_DIR"/

if [ -L "$ASSET_DIR" ]; then
  echo "FAIL $ASSET_DIR is a symlink after copy"
  exit 1
fi

echo "▸ Real files in $ASSET_DIR:"
for f in css/cockpit.css js/cockpit.js vendor/Sortable.min.js; do
  full="$ASSET_DIR/$f"
  if [ ! -f "$full" ]; then echo "  FAIL $f missing"; exit 1; fi
  if [ -L "$full" ]; then echo "  FAIL $f is a symlink"; exit 1; fi
  size=$(stat -c%s "$full" 2>/dev/null || echo 0)
  if [ "$size" -lt 100 ]; then echo "  FAIL $f is $size bytes"; exit 1; fi
  echo "  OK   $f ($size bytes)"
done

FRONTEND_SVC="${BARO_FRONTEND_SVC:-frontend}"
FRONTEND_PORT="${BARO_FRONTEND_PORT:-8080}"
echo "▸ HTTP smoke via http://${FRONTEND_SVC}:${FRONTEND_PORT}:"
for path in \
  /assets/baro_crm/css/cockpit.css \
  /assets/baro_crm/js/cockpit.js \
  /assets/baro_crm/vendor/Sortable.min.js; do
  url="http://${FRONTEND_SVC}:${FRONTEND_PORT}${path}"
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$url")
  if [ "$code" != "200" ]; then
    echo "  FAIL ${path} → HTTP ${code} (via ${url})"
    exit 1
  fi
  echo "  OK   ${path} → 200"
done
ASSET_CHECK_EOF
```

The existing step 6 (`say "6/6 · Clearing cache"`) stays as-is, after this block.

- [ ] **Step 3: Syntax-check (optional)**

```powershell
& "C:\Program Files\Git\bin\bash.exe" -n "baro_crm\install.sh"
```

Expected: silent (= OK). Skip if git-for-Windows isn't installed; the deploy in Task 6 will surface any error.

- [ ] **Step 4: Commit**

```powershell
git add baro_crm/install.sh
git commit -m "feat(install): materialize assets as real files; smoke via nginx (frontend:8080)"
```

---

### Task 5: Update DEPLOY.md — third-party deps + asset verification sections

**Files:**
- Modify: `baro_crm/DEPLOY.md`

- [ ] **Step 1: Insert these two sections before the existing "Files modified on the server" section**

```markdown
## Third-party dependencies

| Package | Version | License | Source |
|---|---|---|---|
| SortableJS | 1.15.6 | MIT | https://github.com/SortableJS/Sortable/releases/tag/1.15.6 — vendored in `baro_crm/baro_crm/public/vendor/Sortable.min.js`. Upstream license copied to `LICENSE-Sortable.txt` in the same folder. SHA-256: `<paste-hex-from-Task-2-step-3>` |

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
```

- [ ] **Step 2: Replace the SHA-256 placeholder**

Replace the literal text `<paste-hex-from-Task-2-step-3>` with the actual hex digest you recorded in Task 2 step 3.

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/DEPLOY.md
git commit -m "docs(deploy): document SortableJS vendoring and asset verification"
```

---

### Task 6: ★ CHECKPOINT — sync to server, run install.sh, confirm green

- [ ] **Step 1: Sync to Florida server**

```powershell
cd "C:\Users\epmek\Documents"
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
```

- [ ] **Step 2: Run install.sh on the server**

```bash
cd ~/baro_crm
./install.sh
```

- [ ] **Step 3: Verify step 5/6 output**

You must see all of these lines (or very similar):

```
▸ 5/6 · Materializing baro_crm assets as real files + verifying via nginx
▸ Real files in sites/assets/baro_crm:
  OK   css/cockpit.css (NNNNN bytes)
  OK   js/cockpit.js (NNNNN bytes)
  OK   vendor/Sortable.min.js (NNNNN bytes)
▸ HTTP smoke via http://frontend:8080:
  OK   /assets/baro_crm/css/cockpit.css → 200
  OK   /assets/baro_crm/js/cockpit.js → 200
  OK   /assets/baro_crm/vendor/Sortable.min.js → 200
▸ 6/6 · Clearing cache
✓ Install complete.
```

- [ ] **Step 4: Browser sanity**

Open `http://100.127.172.110:8080/repair-jobs` in a signed-in browser. Cockpit loads as before (no visual change yet — Kanban view is added in Phase B). Devtools console: type `typeof Sortable` → expect `"function"`.

- [ ] **Step 5: ★ Wait for user**

Tell the user: *"Phase A complete. Sortable vendored and loading, install smoke green, no behavior change. OK to start Phase B (add Kanban view)?"*

---

## Phase B — Kanban view foundation

The deployed `cockpit.js` ships only the list view. Before we can drag-and-drop kanban cards, we need to actually render kanban cards. Phase B adds a view-switcher to the toolbar, a kanban container to the shell, a `renderKanban()` function, and wires the switch event. Cards are clickable to open the inspector. No drag yet.

### Task 7: Add `activeView` state field + view-switcher UI in renderShell

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Find the `const state = { ... }` object in cockpit.js**

Search for `const state = {`. Add `activeView: 'list',` to the state object. The result should look like:

```javascript
  const state = {
    jobs: [],
    stateCounts: { All: 0, Texas: 0, Florida: 0, 'New York': 0, 'New Jersey': 0 },
    selectedId: null,
    activeState: 'All',
    activeView: 'list',                  // NEW: 'list' or 'kanban'
    activeTab: 'overview',
    search: '',
    canWrite: false,
    user: '',
    timeline: null,
    statusPopoverFor: null,
    timelineRefreshTimer: null,
  };
```

- [ ] **Step 2: Find the `renderShell()` function**

Search for `function renderShell()`. Inside the topbar's `work-toolbar` section, find the existing `<div class="filter-row">...` block.

- [ ] **Step 3: Insert the view-switcher BEFORE the filter-row**

Add this block immediately before `<div class="filter-row">`:

```html
<div class="view-switch" id="viewSwitch" role="tablist" aria-label="View">
  <button data-view="list" class="active" type="button" role="tab" aria-selected="true">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
    List
  </button>
  <button data-view="kanban" type="button" role="tab" aria-selected="false">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="6" height="18" rx="1"/><rect x="10" y="3" width="6" height="12" rx="1"/><rect x="17" y="3" width="4" height="8" rx="1"/></svg>
    Kanban
  </button>
</div>
```

- [ ] **Step 4: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): add activeView state field + view-switcher UI"
```

---

### Task 8: Add Kanban container to shell + view-switch CSS + kanban CSS

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

- [ ] **Step 1: Insert kanban container in renderShell**

In `cockpit.js`, find the existing list-view block in `renderShell`:

```html
<div class="work-table-wrap" id="listView">
  ...
</div>
```

Immediately AFTER its closing `</div>` (the one that closes `work-table-wrap`), insert:

```html
<div class="kanban-wrap" id="kanbanView" style="display:none;" aria-hidden="true">
  <div class="kanban" id="kanban"></div>
</div>
```

- [ ] **Step 2: Append view-switch CSS to cockpit.css**

Find the existing CSS section "/* -- 6. State tab strip --" (or whichever section block your file uses). Append this block immediately after the state-tabs CSS:

```css
/* -- View switcher (List / Kanban) -- */
.baro-cockpit .view-switch { display: inline-flex; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 3px; gap: 2px; }
.baro-cockpit .view-switch button { padding: 5px 12px; border-radius: 5px; font-size: 12.5px; color: var(--text-muted); font-weight: 500; display: inline-flex; align-items: center; gap: 4px; }
.baro-cockpit .view-switch button.active { background: var(--bg); color: var(--text); box-shadow: var(--shadow-sm); }
```

- [ ] **Step 3: Append kanban layout CSS to cockpit.css**

Append immediately after the view-switch CSS:

```css
/* -- Kanban view -- */
.baro-cockpit .kanban-wrap { flex: 1; overflow-x: auto; overflow-y: hidden; padding: 0 22px 22px; }
.baro-cockpit .kanban { display: flex; gap: 12px; height: 100%; padding-bottom: 4px; }
.baro-cockpit .kanban-col { width: 290px; flex-shrink: 0; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); display: flex; flex-direction: column; max-height: 100%; }
.baro-cockpit .kanban-col-head { padding: 12px 14px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; }
.baro-cockpit .kanban-col-head .kc-dot { width: 8px; height: 8px; border-radius: 50%; }
.baro-cockpit .kanban-col-head .kc-name { font-size: 12.5px; font-weight: 600; color: var(--text); }
.baro-cockpit .kanban-col-head .kc-count { margin-left: auto; font-size: 11.5px; color: var(--text-muted); background: var(--surface); padding: 1px 7px; border-radius: 10px; }
.baro-cockpit .kanban-col-body { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 8px; min-height: 40px; }
.baro-cockpit .kanban-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; cursor: pointer; transition: border-color .12s, box-shadow .12s, transform .12s; }
.baro-cockpit .kanban-card:hover { border-color: var(--brand); box-shadow: var(--shadow); transform: translateY(-1px); }
.baro-cockpit .kanban-card .kc-id { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.baro-cockpit .kanban-card .kc-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 6px; line-height: 1.3; }
.baro-cockpit .kanban-card .kc-meta { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--text-muted); flex-wrap: wrap; }
.baro-cockpit .kanban-card .kc-foot { display: flex; align-items: center; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.baro-cockpit .kanban-card .kc-foot .avatar { width: 20px; height: 20px; font-size: 9px; }
.baro-cockpit .kanban-card .kc-foot small { color: var(--text-muted); font-size: 11px; margin-left: auto; }
```

- [ ] **Step 4: Commit**

```powershell
git add baro_crm/baro_crm/public/css/cockpit.css baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): add kanban container + view-switch + kanban layout CSS"
```

---

### Task 9: Add `renderKanban()` function

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Find a good insertion point**

Search for `function renderTable()`. Insert the new `renderKanban` function **immediately after** the closing `}` of `renderTable`.

- [ ] **Step 2: Add this exact function**

```javascript
  function renderKanban() {
    const kanban = $('#kanban');
    if (!kanban) return;
    const cols = [
      { title: 'Intake',        keys: ['New','Need Follow-up'] },
      { title: 'Sales',         keys: ['Diagnostics Offered','Waiting Prepayment','Diagnostics Paid','Estimate Sent','Waiting Client Approval'] },
      { title: 'Production',    keys: ['Technician Assigned','Diagnostics In Progress','Diagnosis Completed','Parts Needed','Repair In Progress','Repair Completed'] },
      { title: 'Money & Care',  keys: ['Invoice Sent','Paid','Warranty Active','Closed'] },
      { title: 'Out',           keys: ['Lost','Spam','Unrelated'] },
    ];
    kanban.innerHTML = cols.map(col => {
      const items = state.jobs.filter(j => col.keys.includes(j.status));
      const dotColor = STATUS_MAP[col.keys[0]]?.color || 'slate';
      return `
        <div class="kanban-col">
          <div class="kanban-col-head">
            <span class="kc-dot" style="background:var(--c-${dotColor});" aria-hidden="true"></span>
            <span class="kc-name">${escapeHtml(col.title)}</span>
            <span class="kc-count">${items.length}</span>
          </div>
          <div class="kanban-col-body" data-column="${escapeHtml(col.title)}">
            ${items.map(j => {
              const s = STATUS_MAP[j.status] || { color: 'slate' };
              const customerLabel = (j.customer || '').replace(/^DEMO\s*-\s*/i, '');
              return `
                <div class="kanban-card" data-id="${escapeHtml(j.name)}" data-status="${escapeHtml(j.status)}">
                  <div class="kc-id">${escapeHtml(j.name)}</div>
                  <div class="kc-title">${escapeHtml(customerLabel || j.name)}</div>
                  <div class="kc-meta">
                    <span class="status-pill s-${s.color}"><span class="dot" aria-hidden="true"></span>${escapeHtml(j.status)}</span>
                  </div>
                  <div class="kc-meta" style="margin-top:6px;">
                    ${escapeHtml(j.equipment_type || '—')} • ${escapeHtml(j.service_state || j.area || '—')}
                  </div>
                  <div class="kc-foot">
                    ${j.technician
                      ? `<div class="avatar ${colorClass(j.technician)}" aria-hidden="true">${escapeHtml(initials(j.technician))}</div><span style="font-size:11.5px;color:var(--text-muted);">${escapeHtml(j.technician)}</span>`
                      : `<span style="font-size:11px;color:var(--text-faint);font-style:italic;">Unassigned</span>`}
                    <small>${escapeHtml(formatRelativeTime(j.modified))}</small>
                  </div>
                </div>`;
            }).join('')}
          </div>
        </div>
      `;
    }).join('');
  }
```

Note: each `.kanban-col-body` carries `data-column="<title>"`. Phase D's drag handlers depend on this attribute. Each `.kanban-card` carries `data-status` for the same reason.

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): add renderKanban() — groups by 5 columns with data-column / data-status attrs"
```

---

### Task 10: Wire the view-switch + card-click-to-inspector

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Find the existing main delegated click handler**

Search for `document.addEventListener('click'` in `cockpit.js`. The main delegated handler should be inside the `bindEvents()` function.

- [ ] **Step 2: Add a view-switch case at the TOP of that handler**

Inside the main `document.addEventListener('click', (e) => { ... })` callback, add this block at the very beginning (before any other case):

```javascript
    // View switch (List / Kanban)
    const viewBtn = e.target.closest('#viewSwitch button[data-view]');
    if (viewBtn) {
      document.querySelectorAll('#viewSwitch button').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      viewBtn.classList.add('active');
      viewBtn.setAttribute('aria-selected', 'true');
      state.activeView = viewBtn.dataset.view;
      const list = $('#listView'), kan = $('#kanbanView');
      if (state.activeView === 'kanban') {
        if (list) list.style.display = 'none';
        if (kan) { kan.style.display = ''; kan.setAttribute('aria-hidden', 'false'); }
        renderKanban();
      } else {
        if (list) list.style.display = '';
        if (kan) { kan.style.display = 'none'; kan.setAttribute('aria-hidden', 'true'); }
      }
      return;
    }
```

- [ ] **Step 3: Find the existing row-click handler that opens the inspector**

In the same `bindEvents` function, find the existing block that does something like:

```javascript
    const row = e.target.closest('tr[data-id]');
    if (row && !e.target.closest('[data-stop]')) {
      openInspector(row.dataset.id);
      return;
    }
```

- [ ] **Step 4: Add a parallel block for kanban-card clicks immediately after the row handler**

```javascript
    const card = e.target.closest('.kanban-card[data-id]');
    if (card && !e.target.closest('[data-stop]')) {
      openInspector(card.dataset.id);
      return;
    }
```

- [ ] **Step 5: Make `loadAll` also refresh the kanban view when it's active**

Search for `async function loadAll`. Find the line `renderTable();` inside it. Replace that single line with:

```javascript
      renderTable();
      if (state.activeView === 'kanban') renderKanban();
```

- [ ] **Step 6: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): wire view-switch + kanban-card click-to-inspector + auto-refresh"
```

---

### Task 11: ★ CHECKPOINT — deploy Phase B, verify kanban view appears

- [ ] **Step 1: Sync and install**

```powershell
cd "C:\Users\epmek\Documents"
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
```

On server:
```bash
cd ~/baro_crm
./install.sh
```

Expected: install green, smoke passes.

- [ ] **Step 2: Browser verification**

Open `http://100.127.172.110:8080/repair-jobs`. You should see:

- A new "List | Kanban" switcher in the toolbar (List active by default)
- The list view renders as before
- Click "Kanban" → list disappears, kanban view appears with 5 columns
- Each column has a header with name + dot + count
- Cards render with id, customer, status pill, equipment, technician, time
- Click a card → inspector opens for that job
- Click List → kanban hides, list returns
- No console errors

- [ ] **Step 3: ★ Wait for user**

Tell the user: *"Phase B complete. Kanban view exists, cards render, clicking a card opens the inspector. No drag yet. OK to start Phase C (drag-ready card markup + drag CSS scaffolding)?"*

---

## Phase C — Drag-ready card markup + CSS scaffolding

### Task 12: Modify renderKanban() to emit drag-ready card markup (handle + body)

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

The current `renderKanban` (from Task 9) emits flat cards. We restructure each card into a left handle + body so the drag handle is the only draggable region.

- [ ] **Step 1: Find the inner template literal in `renderKanban`**

In `renderKanban`, find the `items.map(j => { ... return \`...\` ... })`. We're replacing the returned `<div class="kanban-card">...</div>` template.

- [ ] **Step 2: Replace the returned card template with this**

```javascript
              return `
                <div class="kanban-card" data-id="${escapeHtml(j.name)}" data-status="${escapeHtml(j.status)}">
                  <span class="kc-handle" data-stop aria-label="Drag ${escapeHtml(customerLabel || j.name)}" tabindex="-1">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <circle cx="9" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/>
                      <circle cx="15" cy="6" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="15" cy="18" r="1.5"/>
                    </svg>
                  </span>
                  <div class="kc-body">
                    <div class="kc-id">${escapeHtml(j.name)}</div>
                    <div class="kc-title">${escapeHtml(customerLabel || j.name)}</div>
                    <div class="kc-meta">
                      <span class="status-pill s-${s.color}" data-stop><span class="dot" aria-hidden="true"></span>${escapeHtml(j.status)}</span>
                    </div>
                    <div class="kc-meta" style="margin-top:6px;">
                      ${escapeHtml(j.equipment_type || '—')} • ${escapeHtml(j.service_state || j.area || '—')}
                    </div>
                    <div class="kc-foot">
                      ${j.technician
                        ? `<div class="avatar ${colorClass(j.technician)}" aria-hidden="true">${escapeHtml(initials(j.technician))}</div><span style="font-size:11.5px;color:var(--text-muted);">${escapeHtml(j.technician)}</span>`
                        : `<span style="font-size:11px;color:var(--text-faint);font-style:italic;">Unassigned</span>`}
                      <small>${escapeHtml(formatRelativeTime(j.modified))}</small>
                    </div>
                  </div>
                </div>`;
```

Note: `data-stop` on `.kc-handle` and `.status-pill` prevents the body-click handler from opening the inspector when the user grabs the handle or the pill.

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): emit drag-ready card markup with handle + body"
```

---

### Task 13: Add drag handle + card layout CSS

**Files:**
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

- [ ] **Step 1: Append this block to cockpit.css, after the existing kanban-card rules from Task 8**

```css
/* -- Drag handle + card body layout -- */
.baro-cockpit .kanban-card { display: flex; align-items: stretch; padding: 0; overflow: hidden; }
.baro-cockpit .kanban-card .kc-handle {
  display: flex; align-items: center; justify-content: center;
  width: 22px; flex-shrink: 0;
  color: var(--text-faint);
  background: var(--surface-2);
  border-right: 1px solid var(--border);
  cursor: grab;
  transition: color .12s, background .12s;
  touch-action: none;
}
.baro-cockpit .kanban-card .kc-handle:hover { color: var(--text-muted); background: var(--brand-50); }
.baro-cockpit .kanban-card .kc-handle:active { cursor: grabbing; }
.baro-cockpit .kanban-card .kc-body { flex: 1; padding: 10px 12px; min-width: 0; }
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/css/cockpit.css
git commit -m "feat(cockpit): add drag handle + card body layout CSS"
```

---

### Task 14: Add drag visual-state CSS (ghost, dragging, drop-valid, drop-invalid-hover)

**Files:**
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

- [ ] **Step 1: Append this block to cockpit.css, immediately after Task 13's block**

```css
/* -- Drag visual states -- */
.baro-cockpit .kanban-card.kc-ghost { opacity: 0.35; pointer-events: none; }
.baro-cockpit .kanban-card.kc-dragging {
  opacity: 1;
  transform: rotate(1deg);
  box-shadow: 0 12px 28px rgba(15,23,42,.18);
  cursor: grabbing;
}
body.is-dragging { cursor: grabbing; }
body.is-dragging .baro-cockpit, body.is-dragging .baro-cockpit * { user-select: none; }
.baro-cockpit .kanban-col-body.drop-valid {
  box-shadow: inset 0 0 0 2px var(--brand-100);
  background: var(--brand-50);
  border-radius: 8px;
  transition: box-shadow .12s, background .12s;
}
.baro-cockpit .kanban-col-body.drop-invalid-hover {
  box-shadow: inset 0 0 0 2px var(--c-rose-bg);
  border-radius: 8px;
  transition: box-shadow .12s;
}
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/css/cockpit.css
git commit -m "feat(cockpit): add drag visual state CSS (ghost, dragging, drop targets)"
```

---

### Task 15: Add empty-column drop placeholder CSS

**Files:**
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

- [ ] **Step 1: Append this block to cockpit.css, immediately after Task 14's block**

```css
/* -- Empty column drop placeholder (only during drag) -- */
body.is-dragging .baro-cockpit .kanban-col-body:empty {
  min-height: 64px;
  border: 1px dashed var(--border-strong);
  border-radius: 6px;
  margin: 6px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
  font-size: 12px;
  background: transparent;
}
body.is-dragging .baro-cockpit .kanban-col-body:empty::after {
  content: 'No transition from ' attr(data-empty-from);
}
body.is-dragging .baro-cockpit .kanban-col-body.drop-valid:empty::after {
  content: 'Drop here to ' attr(data-empty-to);
}
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/css/cockpit.css
git commit -m "feat(cockpit): add empty-column drop placeholder CSS during drag"
```

---

### Task 16: Add confirm-modal CSS

**Files:**
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

The destructive confirm modal will be appended **inside** `.baro-cockpit` (Task 22 enforces this) so the namespaced CSS below applies.

- [ ] **Step 1: Append this block to cockpit.css, immediately after Task 15's block**

```css
/* -- Destructive confirm modal -- */
.baro-cockpit .confirm-overlay {
  position: fixed; inset: 0;
  background: rgba(15,23,42,0.18);
  backdrop-filter: blur(2px);
  display: grid; place-items: center;
  z-index: 250;
  opacity: 0; pointer-events: none;
  transition: opacity .15s;
}
.baro-cockpit .confirm-overlay.open { opacity: 1; pointer-events: all; }
.baro-cockpit .confirm-modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: min(420px, 92vw);
  padding: 22px 22px 18px;
  transform: scale(0.97);
  transition: transform .15s;
}
.baro-cockpit .confirm-overlay.open .confirm-modal { transform: scale(1); }
.baro-cockpit .confirm-modal h3 {
  margin: 0 0 6px;
  font-size: 16px; font-weight: 700; color: var(--text);
  line-height: 1.3;
}
.baro-cockpit .confirm-modal .confirm-desc {
  font-size: 13px; color: var(--text-muted); line-height: 1.55;
  margin-bottom: 18px;
}
.baro-cockpit .confirm-modal .confirm-actions {
  display: flex; justify-content: flex-end; gap: 8px;
}
.baro-cockpit .confirm-modal .btn-destructive {
  background: var(--c-rose); color: #fff;
  padding: 7px 14px; border-radius: 7px; font-size: 13px; font-weight: 600;
  border: 1px solid var(--c-rose);
  transition: filter .12s;
}
.baro-cockpit .confirm-modal .btn-destructive:hover { filter: brightness(0.92); }
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/css/cockpit.css
git commit -m "feat(cockpit): add destructive confirm modal CSS (scoped under .baro-cockpit)"
```

---

### Task 17: ★ CHECKPOINT — deploy Phase C, verify card markup + handle visible

- [ ] **Step 1: Sync and install**

```powershell
cd "C:\Users\epmek\Documents"
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
```

On server:
```bash
cd ~/baro_crm
./install.sh
```

- [ ] **Step 2: Browser verification**

Open `/repair-jobs`, switch to Kanban. Verify:
- Each card now has a small grip icon (6 dots in 2x3) on the **left edge**
- Hovering the grip → cursor becomes `grab`
- Hovering the body (not grip) → no `grab` cursor
- Click the grip itself → inspector does **not** open
- Click the body → inspector opens
- No console errors

The grip doesn't actually drag anything yet — Phase D wires that.

- [ ] **Step 3: ★ Wait for user**

Tell the user: *"Phase C complete. Cards have a left grip handle, all drag CSS states defined (but not wired), confirm-modal CSS scoped under .baro-cockpit. OK to start Phase D (drag mechanics)?"*

---

## Phase D — Drag mechanics + API integration

### Task 18: Add `COLUMN_STATUSES`, `DESTRUCTIVE_STATUSES` constants

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Find `STATE_TABS` declaration in cockpit.js**

Search for `const STATE_TABS = [`. Find its closing `];`.

- [ ] **Step 2: Insert this block immediately after the closing `];` of STATE_TABS**

```javascript
  // ---------------------------------------------------------------------------
  // Drag/drop: column → status map and destructive status set
  // (Must match the cols array in renderKanban())
  // ---------------------------------------------------------------------------
  const COLUMN_STATUSES = {
    'Intake':       new Set(['New', 'Need Follow-up']),
    'Sales':        new Set(['Diagnostics Offered', 'Waiting Prepayment',
                             'Diagnostics Paid', 'Estimate Sent',
                             'Waiting Client Approval']),
    'Production':   new Set(['Technician Assigned', 'Diagnostics In Progress',
                             'Diagnosis Completed', 'Parts Needed',
                             'Repair In Progress', 'Repair Completed']),
    'Money & Care': new Set(['Invoice Sent', 'Paid', 'Warranty Active', 'Closed']),
    'Out':          new Set(['Lost', 'Spam', 'Unrelated']),
  };

  const DESTRUCTIVE_STATUSES = new Set(['Lost', 'Spam', 'Unrelated', 'Closed']);
```

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): add COLUMN_STATUSES + DESTRUCTIVE_STATUSES constants"
```

---

### Task 19: Add `resolveDropAction()` pure function + drag helpers

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Find the end of section 3 (Frappe API plumbing)**

Search for `const api = {`. Find the closing `};` of that const object.

- [ ] **Step 2: Insert this section immediately after that `};`**

```javascript
  // ---------------------------------------------------------------------------
  // Section 16: Drag/drop — pure helpers
  // ---------------------------------------------------------------------------
  function resolveDropAction(cardStatus, targetColumnName) {
    const targetSet = COLUMN_STATUSES[targetColumnName];
    if (!targetSet) return { kind: 'none', reason: 'unknown column ' + targetColumnName };
    const candidates = TRANSITIONS_FROM[cardStatus] || [];
    const valid = candidates.filter(t => targetSet.has(t.to));
    if (valid.length === 0) return { kind: 'none', reason: 'no valid transition from ' + cardStatus + ' to ' + targetColumnName };
    if (valid.length === 1) return { kind: 'single', action: valid[0] };
    return { kind: 'multi', actions: valid };
  }

  function revertSortableMove(evt) {
    if (!evt || !evt.from || !evt.item) return;
    const siblings = evt.from.children;
    const before = siblings[evt.oldIndex] || null;
    evt.from.insertBefore(evt.item, before);
  }

  function cleanupDragVisuals() {
    document.body.classList.remove('is-dragging');
    document.querySelectorAll('.baro-cockpit .kanban-col-body.drop-valid')
      .forEach(el => el.classList.remove('drop-valid'));
    document.querySelectorAll('.baro-cockpit .kanban-col-body.drop-invalid-hover')
      .forEach(el => el.classList.remove('drop-invalid-hover'));
    document.querySelectorAll('.baro-cockpit .kanban-col-body[data-empty-from]')
      .forEach(el => { el.removeAttribute('data-empty-from'); });
    document.querySelectorAll('.baro-cockpit .kanban-col-body[data-empty-to]')
      .forEach(el => { el.removeAttribute('data-empty-to'); });
  }
```

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): add resolveDropAction + revertSortableMove + cleanupDragVisuals"
```

---

### Task 20: Defensively re-scope the existing `.pop-item` click handler

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

The existing global delegated click handler matches `.pop-item` and calls `changeStatus(state.statusPopoverFor, popItem.dataset.status)`. In Phase D the drag popover will render `.pop-item` buttons too, but with `data-drag-action` / `data-drag-target` instead of `data-status`. Without this fix, the global handler would fire with `undefined`. We tighten the selector to require `[data-status]`.

- [ ] **Step 1: Find the popover-item handler in `bindEvents`**

Search inside `bindEvents` for:

```javascript
    const popItem = e.target.closest('.pop-item');
```

- [ ] **Step 2: Replace that line with the narrower selector**

```javascript
    const popItem = e.target.closest('.pop-item[data-status]');
```

Everything else in that handler block stays unchanged. Now the global handler only fires for the original status-change popover, never for the drag popover.

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "fix(cockpit): scope global pop-item handler to [data-status] only"
```

---

### Task 21: Add `showConfirmDialog` — **appended INSIDE `.baro-cockpit`** so namespaced CSS applies

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Append this block to section 16 (after `cleanupDragVisuals`)**

```javascript
  let confirmEl = null;
  function ensureConfirmDom() {
    if (confirmEl) return confirmEl;
    const root = document.createElement('div');
    root.className = 'confirm-overlay';
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = `
      <div class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirmTitle" tabindex="-1">
        <h3 id="confirmTitle"></h3>
        <div class="confirm-desc" id="confirmDesc"></div>
        <div class="confirm-actions">
          <button class="btn btn-outline" data-confirm-cancel type="button">Cancel</button>
          <button class="btn-destructive" data-confirm-ok type="button"></button>
        </div>
      </div>
    `;
    // CRITICAL: append INSIDE .baro-cockpit so the namespaced CSS
    // (.baro-cockpit .confirm-overlay { ... }) applies.
    const cockpitRoot = document.querySelector('.baro-cockpit') || document.body;
    cockpitRoot.appendChild(root);
    confirmEl = root;
    return root;
  }

  function showConfirmDialog({ title, desc, okLabel }) {
    return new Promise((resolve) => {
      const root = ensureConfirmDom();
      root.querySelector('#confirmTitle').textContent = title;
      root.querySelector('#confirmDesc').textContent = desc;
      root.querySelector('[data-confirm-ok]').textContent = okLabel;
      const okBtn = root.querySelector('[data-confirm-ok]');
      const cancelBtn = root.querySelector('[data-confirm-cancel]');

      let settled = false;
      function close(result) {
        if (settled) return;
        settled = true;
        root.classList.remove('open');
        root.setAttribute('aria-hidden', 'true');
        document.removeEventListener('keydown', onKey);
        root.removeEventListener('click', onOverlayClick);
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
        resolve(result);
      }
      function onOk(e) { e.preventDefault(); e.stopPropagation(); close(true); }
      function onCancel(e) { e.preventDefault(); e.stopPropagation(); close(false); }
      function onOverlayClick(e) { if (e.target === root) close(false); }
      function onKey(e) {
        if (e.key === 'Escape') { e.preventDefault(); close(false); }
        if (e.key === 'Tab') {
          e.preventDefault();
          (document.activeElement === okBtn ? cancelBtn : okBtn).focus();
        }
      }
      okBtn.addEventListener('click', onOk);
      cancelBtn.addEventListener('click', onCancel);
      root.addEventListener('click', onOverlayClick);
      document.addEventListener('keydown', onKey);

      root.classList.add('open');
      root.setAttribute('aria-hidden', 'false');
      setTimeout(() => cancelBtn.focus(), 30);
    });
  }
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): showConfirmDialog appended INSIDE .baro-cockpit for namespaced CSS"
```

---

### Task 22: Initialize SortableJS on every kanban column body

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Append this block to section 16 (after `showConfirmDialog`)**

```javascript
  let sortableInstances = [];
  let activeSortableEvt = null;
  let escCancelled = false;

  function initDragDrop() {
    sortableInstances.forEach(s => { try { s.destroy(); } catch (e) {} });
    sortableInstances = [];

    if (typeof Sortable === 'undefined') {
      console.warn('Sortable global missing; drag/drop disabled');
      return;
    }

    document.querySelectorAll('.baro-cockpit .kanban-col-body').forEach(colEl => {
      const s = new Sortable(colEl, {
        group: 'kanban',
        handle: '.kc-handle',
        draggable: '.kanban-card',
        animation: 200,
        ghostClass: 'kc-ghost',
        dragClass: 'kc-dragging',
        forceFallback: true,
        fallbackOnBody: true,
        fallbackTolerance: 4,
        delay: 0,
        delayOnTouchOnly: true,
        touchStartThreshold: 4,
        onStart: handleDragStart,
        onMove: handleDragMove,
        onEnd: handleDragEnd,
      });
      sortableInstances.push(s);
    });
  }

  function handleDragStart(evt) {
    activeSortableEvt = evt;
    escCancelled = false;
    document.body.classList.add('is-dragging');
    const cardStatus = evt.item.dataset.status;
    document.querySelectorAll('.baro-cockpit .kanban-col-body').forEach(col => {
      const target = col.dataset.column;
      const res = resolveDropAction(cardStatus, target);
      if (res.kind === 'single' || res.kind === 'multi') {
        col.classList.add('drop-valid');
        col.setAttribute('data-empty-to', res.kind === 'single' ? res.action.action : 'choose action');
      } else {
        col.setAttribute('data-empty-from', cardStatus);
      }
    });
    document.addEventListener('keydown', onEscDuringDrag);
  }

  function handleDragMove(evt) {
    document.querySelectorAll('.baro-cockpit .kanban-col-body.drop-invalid-hover')
      .forEach(c => c.classList.remove('drop-invalid-hover'));
    if (evt.to && !evt.to.classList.contains('drop-valid')) {
      evt.to.classList.add('drop-invalid-hover');
    }
    return evt.to ? evt.to.classList.contains('drop-valid') : true;
  }

  function handleDragEnd(evt) {
    document.removeEventListener('keydown', onEscDuringDrag);
    cleanupDragVisuals();
    if (escCancelled) {
      escCancelled = false;
      activeSortableEvt = null;
      return;
    }
    handleDropResolution(evt);
    activeSortableEvt = null;
  }

  function onEscDuringDrag(e) {
    if (e.key !== 'Escape' || !activeSortableEvt) return;
    e.preventDefault();
    e.stopPropagation();
    escCancelled = true;
    revertSortableMove(activeSortableEvt);
    cleanupDragVisuals();
  }

  // Stub — Task 23+ replaces this
  function handleDropResolution(evt) {
    console.warn('handleDropResolution not implemented yet');
  }
```

- [ ] **Step 2: Call `initDragDrop()` at the end of `renderKanban()`**

In `renderKanban`, immediately after `kanban.innerHTML = cols.map(...).join('');`, add:

```javascript
    initDragDrop();
```

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): initialize SortableJS on every kanban column body"
```

---

### Task 23: Implement happy-path drop (single non-destructive workflow action)

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Replace the entire `function handleDropResolution(evt) { ... }` stub with this**

```javascript
  async function handleDropResolution(evt) {
    const targetCol = evt.to ? evt.to.dataset.column : null;
    const cardStatus = evt.item.dataset.status;
    const cardId = evt.item.dataset.id;
    const job = state.jobs.find(j => j.name === cardId);
    const customer = (job && job.customer) || cardId;

    if (!targetCol) {
      revertSortableMove(evt);
      return;
    }

    const res = resolveDropAction(cardStatus, targetCol);

    if (res.kind === 'none') {
      revertSortableMove(evt);
      toast(`No workflow transition from ${cardStatus} to ${targetCol}`, 'err');
      return;
    }

    if (res.kind === 'single') {
      if (DESTRUCTIVE_STATUSES.has(res.action.to)) {
        await runDestructive(evt, cardId, customer, res.action);
      } else {
        await runHappyPath(evt, cardId, res.action);
      }
      return;
    }

    if (res.kind === 'multi') {
      revertSortableMove(evt);
      showDragMultiPopover(evt, cardId, customer, res.actions);
    }
  }

  async function runHappyPath(evt, cardId, action) {
    try {
      const r = await api.changeStatus(cardId, action.action);
      const job = state.jobs.find(j => j.name === cardId);
      if (job) job.status = r.status;
      renderKanban();
      api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); });
      toast(`Status: ${r.status}`, 'ok');
      if (state.selectedId === cardId) openInspector(cardId);
    } catch (e) {
      revertSortableMove(evt);
      toast('Status change failed: ' + extractError(e), 'err');
    }
  }

  // Stubs — Task 24 + Task 25 replace these
  function showDragMultiPopover(evt, cardId, customer, actions) {
    console.warn('showDragMultiPopover not implemented yet');
    revertSortableMove(evt);
  }
  async function runDestructive(evt, cardId, customer, action) {
    console.warn('runDestructive not implemented yet');
    revertSortableMove(evt);
  }
```

- [ ] **Step 2: Deploy + smoke test**

Sync, install, reload `/repair-jobs`. Switch to Kanban. Grab a `New` card by the grip and drag to "Sales". Expected:
- Card opacity drops
- "Sales" column shows subtle valid border
- Release on Sales → toast "Status: Diagnostics Offered"
- Card moves to Sales column
- Status pill on the card updates

If anything else, stop and debug before moving on.

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): implement happy-path drop (single non-destructive action)"
```

---

### Task 24: Implement multi-action popover with event-leak guard

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

The drag popover reuses the existing `#statusPopover` DOM and `.pop-item` styling, but its click handler MUST stop propagation so the global delegated handler (which we already scoped to `[data-status]` in Task 20) doesn't double-fire. Two-layer defense.

- [ ] **Step 1: Replace the `function showDragMultiPopover(...)` stub with this implementation**

```javascript
  function showDragMultiPopover(evt, cardId, customer, actions) {
    const pop = $('#statusPopover');
    if (!pop) {
      revertSortableMove(evt);
      toast('Popover not found', 'err');
      return;
    }
    state.statusPopoverFor = cardId;

    const r = evt.originalEvent && evt.originalEvent.changedTouches
      ? evt.originalEvent.changedTouches[0]
      : (evt.originalEvent || { clientX: window.innerWidth / 2, clientY: window.innerHeight / 2 });
    const x = r.clientX ?? (window.innerWidth / 2);
    const y = r.clientY ?? (window.innerHeight / 2);
    pop.style.top = `${Math.min(y, window.innerHeight - 320)}px`;
    pop.style.left = `${Math.min(x, window.innerWidth - 280)}px`;

    $('#popList').innerHTML = `<div class="pop-label">Drag actions</div>` + actions.map(a => {
      const s = STATUS_MAP[a.to] || { color: 'slate' };
      return `<button class="pop-item" type="button" data-drag-action="${escapeHtml(a.action)}" data-drag-target="${escapeHtml(a.to)}">
        <span class="pop-dot" style="background:var(--c-${s.color});"></span>
        <span>${escapeHtml(a.to)}</span>
        <span style="margin-left:auto;font-size:11px;color:var(--text-faint);">${escapeHtml(a.action)}</span>
      </button>`;
    }).join('');
    pop.classList.add('open');
    if ($('#popSearch')) $('#popSearch').value = '';

    function onPopClick(e) {
      const item = e.target.closest('[data-drag-action]');
      if (!item) return;
      // BLOCK the global delegated handler from also firing.
      // It's already scoped to .pop-item[data-status] (Task 20), but defense in depth.
      e.preventDefault();
      e.stopPropagation();
      pop.classList.remove('open');
      pop.removeEventListener('click', onPopClick);
      document.removeEventListener('keydown', onPopKey);
      const action = item.dataset.dragAction;
      const target = item.dataset.dragTarget;
      const fakeAction = { action, to: target };
      if (DESTRUCTIVE_STATUSES.has(target)) {
        runDestructive(evt, cardId, customer, fakeAction);
      } else {
        runHappyPathFromMulti(cardId, fakeAction);
      }
    }
    function onPopKey(e) {
      if (e.key === 'Escape') {
        pop.classList.remove('open');
        pop.removeEventListener('click', onPopClick);
        document.removeEventListener('keydown', onPopKey);
      }
    }
    pop.addEventListener('click', onPopClick);
    document.addEventListener('keydown', onPopKey);
  }

  async function runHappyPathFromMulti(cardId, action) {
    try {
      const r = await api.changeStatus(cardId, action.action);
      const job = state.jobs.find(j => j.name === cardId);
      if (job) job.status = r.status;
      renderKanban();
      api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); });
      toast(`Status: ${r.status}`, 'ok');
      if (state.selectedId === cardId) openInspector(cardId);
    } catch (e) {
      toast('Status change failed: ' + extractError(e), 'err');
    }
  }
```

- [ ] **Step 2: Deploy + smoke test**

Grab a `Diagnostics Offered` card and drag to "Sales". From Diagnostics Offered there are two transitions into Sales (`Request Prepayment` → Waiting Prepayment, `Mark Diagnostics Paid` → Diagnostics Paid). Popover should appear with both. Pick one → status updates.

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): implement multi-action drag popover with event-leak guard"
```

---

### Task 25: Implement destructive drop with confirm modal

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Replace the `async function runDestructive(...)` stub with this implementation**

```javascript
  async function runDestructive(evt, cardId, customer, action) {
    revertSortableMove(evt);

    const customerLabel = (customer || cardId).replace(/^DEMO\s*-\s*/i, '');
    const confirmed = await showConfirmDialog({
      title: `${action.action} ${customerLabel}?`,
      desc: action.to === 'Closed'
        ? 'This closes the job. It will no longer appear in the active pipeline.'
        : `This marks the job as ${action.to} and closes it. It will no longer appear in the active pipeline.`,
      okLabel: action.action,
    });

    if (!confirmed) return;

    try {
      const r = await api.changeStatus(cardId, action.action);
      const job = state.jobs.find(j => j.name === cardId);
      if (job) job.status = r.status;
      renderKanban();
      api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); });
      toast(`Status: ${r.status}`, 'ok');
      if (state.selectedId === cardId) openInspector(cardId);
    } catch (e) {
      toast('Status change failed: ' + extractError(e), 'err');
    }
  }
```

- [ ] **Step 2: Deploy + smoke BOTH destructive paths**

**Single (8b):** Grab a `Diagnostics Offered` card, drag to "Out". Only `Mark Lost` is valid → no popover → confirm modal appears directly with default focus on Cancel → Esc cancels → no API call. Re-do, click "Mark Lost" → API fires, card moves.

**Multi (8a):** Grab a `New` card, drag to "Out". Popover with `Mark Lost` / `Mark Spam` / `Mark Unrelated` → pick Mark Lost → confirm modal → cancel works → re-do, confirm → API fires.

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git commit -m "feat(cockpit): destructive drop with confirm modal (default focus Cancel)"
```

---

### Task 26: Verify empty-column drop placeholder behavior

**Files:** None (verification step).

- [ ] **Step 1: Find or create an empty column scenario**

Most kanbans have at least one empty group column (e.g., no `Closed` jobs → "Money & Care" might still have other statuses; if all 4 Money & Care statuses have zero rows, the column body is empty).

If your data fills every column, manually move one card to make a column empty: drag any `Paid` card to "Money & Care" — leaving its previous column empty if it was the only one. Or just verify with whatever empty column you have today.

- [ ] **Step 2: Start a drag and observe the empty column**

Grab any card. Observe an empty column:
- If the drag is valid for that column: dashed border + text "Drop here to {action label}"
- If invalid: dashed border + text "No transition from {source status}"

End the drag. Empty column placeholder disappears.

- [ ] **Step 3: Commit (empty if no code change)**

```powershell
git commit --allow-empty -m "test(cockpit): manually verified empty-column drop placeholder"
```

---

### Task 27: ★ CHECKPOINT — run all 14 manual desktop tests

- [ ] **Step 1: Sync + install one more time**

```powershell
cd "C:\Users\epmek\Documents"
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
```

```bash
cd ~/baro_crm
./install.sh
```

- [ ] **Step 2: Execute every test from spec §11.2 on Chrome desktop**

Open `/repair-jobs`. Walk through in order:

| # | Test | Pass? |
|---|---|---|
| 1 | Open `/repair-jobs` signed in | ☐ |
| 2 | Switch to Kanban view | ☐ |
| 3 | Hover card (grip visible, cursor changes) | ☐ |
| 4 | Click body (not grip) → inspector opens | ☐ |
| 5 | Drag `New` → "Sales" → direct `Offer Diagnostics` | ☐ |
| 6 | Drag `Repair Completed` → "Money & Care" → direct `Send Invoice` | ☐ |
| 7 | Drag `New` → "Money & Care" (invalid) → subtle rejection only on that column; zero API calls | ☐ |
| 8a | Drag `New` → "Out" → popover (3) → pick Mark Lost → confirm modal → Esc → re-do → confirm → moved | ☐ |
| 8b | Drag `Diagnostics Offered` → "Out" → direct confirm → confirm → moved | ☐ |
| 9 | Two-tab realtime reflection within ~600ms | ☐ |
| 12 | Drag, kill Tailscale mid-drop → snap back + error toast | ☐ |
| 13 | Drag as low-perm user → rollback + permission toast | ☐ |
| 14 | Esc during drag → cancels, no API call | ☐ |

For each fail: note the symptom + console + network traceback, fix, commit, re-deploy, re-test just that one.

- [ ] **Step 3: ★ Wait for user**

Tell the user: *"Phase D complete. All 12 desktop manual tests pass [or: tests X, Y failed — see notes]. OK to do Phase E (iPad + screenshots)?"*

---

## Phase E — Tablet acceptance + sign-off

### Task 28: Run tablet tests #10 + #11 on iPad-class Safari

**Files:** None.

- [ ] **Step 1: Open the cockpit on iPad via Tailscale**

If Tailscale isn't installed on iPad: App Store → "Tailscale" → sign in. Then Safari: `http://100.127.172.110:8080/repair-jobs`.

- [ ] **Step 2: Test #10 — column scroll**

Swipe up/down on a card's **body** (not the grip). Column should scroll. Pass: visible scrolling, no card detaches.

- [ ] **Step 3: Test #11 — touch drag**

Long-press a card's **grip handle**, then drag to an adjacent column. After ~80ms the drag starts. Drop on a valid column → card moves + toast.

If drag doesn't start, verify `forceFallback: true` is in the Sortable config (Task 22).

- [ ] **Step 4: Record outcomes; commit**

```powershell
git commit --allow-empty -m "test(cockpit): verified iPad scroll-vs-drag + touch drag"
```

---

### Task 29: Capture screenshots, add to crm-prototype/README.md

**Files:**
- Modify: `crm-prototype/README.md`
- Create: `crm-prototype/dragdrop-evidence/` (folder with images)

- [ ] **Step 1: Capture 5+ screenshots**

Cover at minimum:
- Test #5 outcome (happy drop, card now in Sales)
- Test #7 mid-drag (invalid hover styling on ONE column only)
- Test #8 confirm modal open with default focus on Cancel
- Test #10 iPad scroll
- Test #11 iPad active touch drag

Save under `crm-prototype/dragdrop-evidence/` with descriptive filenames.

- [ ] **Step 2: Append a "Drag/drop evidence" section to crm-prototype/README.md**

```markdown
## Drag/drop evidence (2026-05-XX)

Reference screenshots and recordings for kanban drag/drop in `baro_crm` cockpit.
Captured during sign-off of spec `docs/superpowers/specs/2026-05-20-kanban-drag-drop-design.md`
and implementation plan `docs/superpowers/plans/2026-05-20-kanban-drag-drop.md`.

See `dragdrop-evidence/`:

- `test5-happy-drop.png` — single valid drop (New → Sales)
- `test7-invalid-rejection.png` — invalid column subtle styling only on hovered column
- `test8-confirm-modal.png` — destructive confirm modal with Cancel default-focused
- `test10-ipad-scroll.png` — iPad column scroll without drag initiation
- `test11-ipad-drag.png` — iPad touch drag via grip handle

If drag/drop behavior changes, re-capture and replace.
```

Replace `XX` with the actual capture date.

- [ ] **Step 3: Commit**

```powershell
git add crm-prototype/README.md crm-prototype/dragdrop-evidence/
git commit -m "docs(cockpit): add drag/drop sign-off evidence (screenshots)"
```

---

### Task 30: Final summary commit + roadmap update + tag

**Files:**
- Modify: `docs/superpowers/specs/2026-05-20-kanban-drag-drop-design.md`
- Modify: `docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md`
- Modify: `obsidian/00_Index.md/ERPNext/Roadmap.md`

- [ ] **Step 1: Update the spec status line**

In `docs/superpowers/specs/2026-05-20-kanban-drag-drop-design.md`, change the Status line near the top to:

```
Status: Shipped 2026-05-XX. All 14 acceptance tests passed. Spec frozen — change requires new spec.
```

- [ ] **Step 2: Update both roadmap files**

In `docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md` find the "Sub-project E · Kanban drag/drop in cockpit" section and prepend:

```markdown
> **Shipped 2026-05-XX.** Spec: `2026-05-20-kanban-drag-drop-design.md`. Plan: `docs/superpowers/plans/2026-05-20-kanban-drag-drop.md`. All 14 acceptance tests passed on Chrome desktop + Safari iPad. Sortable.min.js v1.15.6 vendored.
```

In `C:\Users\epmek\Documents\obsidian\00_Index.md\ERPNext\Roadmap.md` mark row E status as "✓ Shipped 2026-05-XX" and promote F (in-cockpit create drawer) to "next up".

- [ ] **Step 3: Final commit + tag**

```powershell
git add docs/ obsidian/
git commit -m "docs(roadmap): mark sub-project E (kanban drag/drop) shipped"
git tag kanban-dnd-shipped
git log --oneline | head -30
```

You should see ~30 commits between `pre-kanban-dnd` and `kanban-dnd-shipped`. Done.

---

## Appendix A — Quick recovery commands

| Problem | Recovery |
|---|---|
| Cockpit returns 500 after deploy | `docker compose -f ~/frappe_docker/pwd.yml exec backend tail -80 /home/frappe/frappe-bench/sites/frontend/logs/web.error.log` |
| `Sortable is not defined` in console | Re-run `./install.sh` — Task 4 asset smoke catches missing vendor file |
| Drag works but cards don't move on drop | Check `handleDragEnd` for an `evt.to` field-name typo |
| Status change fires but DOM doesn't update | Confirm Task 23's `renderKanban()` call inside `runHappyPath` |
| Esc doesn't cancel | Confirm Task 22's `document.addEventListener('keydown', onEscDuringDrag)` inside `handleDragStart` |
| Confirm modal CSS broken (looks unstyled) | Confirm Task 21's `cockpitRoot.appendChild(root)` uses `.baro-cockpit`, not `document.body` |
| Drag popover double-fires (status changes twice) | Confirm Task 20's selector change to `.pop-item[data-status]` AND Task 24's `e.stopPropagation()` |

---

## Appendix B — After every commit, self-review

- ☐ No console errors during testing
- ☐ Only the intended files committed
- ☐ Commit message in conventional-commits style (`feat:` / `fix:` / `chore:` / `docs:`)
- ☐ install.sh re-run after backend-affecting change
- ☐ Test for this task passed
