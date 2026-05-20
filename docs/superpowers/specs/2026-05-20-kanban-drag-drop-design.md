# Kanban drag/drop in baro_crm cockpit — design

Date: 2026-05-20
Status: **Shipped 2026-05-20.** All 4 automated install-time checks pass. All 12 of 14 desktop manual tests pass (tests 10–11 require iPad-class Safari and are deferred until tablet is available; see spec §11.2). Spec frozen — change requires new spec.
Roadmap parent: `2026-05-19-baro-crm-roadmap.md` (sub-project E)
Implementation target: `baro_crm` Frappe app
Estimated effort: 1–2 days

---

## 1. Goal

Let users move a Repair Job through its workflow by dragging its kanban card from one group column to another. Every drag must resolve to a real workflow action (not a raw `status` field write) so that role permissions, transitions, and audit history all flow through Frappe's workflow engine.

## 2. Success criteria

The feature is "done" when:

- The cockpit at `/repair-jobs` shows a kanban view where cards have an explicit drag handle on the left edge.
- Dragging a card to a valid group column either (a) fires the single valid workflow action and updates the card in place, or (b) opens a popover at the drop point to pick when multiple actions are valid.
- Dragging to a column with no valid transition shows subtle rejection feedback on that column only and snaps the card back with **zero** API calls.
- Dragging to a destructive group (containing `Lost`, `Spam`, `Unrelated`, `Closed`) triggers a confirm modal with default focus on **Cancel** before any DOM move or API call.
- Touch users on iPad-class tablets can drag via the handle while still being able to scroll column bodies by swiping outside the handle.
- All 4 automated install-time checks and all 14 manual browser tests (see §11) pass.

## 3. Constraints (from user, in priority order)

1. Optimistic update on the DOM is OK for normal transitions; **rollback on API error**.
2. **No** optimistic update for destructive transitions; confirm first.
3. Source of truth for the card's status is always the server response from `baro_crm.api.repair_job.change_status`. The DOM is a guess until the call returns.
4. Drag/drop must only call `change_status`. **Never** call `set_field` for `status`.
5. Cards have an explicit drag handle. The handle starts the drag; the card body opens the inspector. Tablet users must be able to scroll without grabbing.
6. Valid columns get subtle highlighting during drag. Invalid columns stay neutral; only the specific column currently under the cursor gets a rejection style. No board-wide red.
7. Empty columns show a drop-target placeholder only during a drag.
8. Permission errors from the server cause card rollback + a clear toast.
9. **No** client-side pre-filtering of valid actions by user role. Workflow engine is the source of truth.
10. Assets must serve at `/assets/baro_crm/...` through nginx on port 8080. Verify via curl in install.sh.

## 4. Architecture and data flow

### 4.1 Components

```
baro_crm/baro_crm/public/
├── css/cockpit.css                      ← +80 lines (drag styles, confirm modal)
├── js/cockpit.js                        ← +250 lines (drag logic kept inline)
└── vendor/
    └── Sortable.min.js          NEW     ← vendored SortableJS v1.15.6, ~12KB, MIT

baro_crm/baro_crm/www/repair-jobs.html   ← +1 <script> tag for Sortable
baro_crm/install.sh                      ← +20 lines (asset smoke test)
baro_crm/DEPLOY.md                       ← +30 lines (asset story, license note)
```

Drag logic stays inside `cockpit.js` to remove load-order risk. The only new asset is `Sortable.min.js`, loaded before `cockpit.js`:

```html
<script src="/assets/baro_crm/vendor/Sortable.min.js"></script>
<script src="/assets/baro_crm/js/cockpit.js"></script>
```

### 4.2 Card markup

```html
<div class="kanban-card" data-id="RJ-2026-0001" data-status="Diagnostics Offered">
  <span class="kc-handle" aria-label="Drag to move" tabindex="-1">
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <!-- 6-dot grip icon -->
    </span>
  <div class="kc-body">
    <!-- existing card content: id, title, status pill, equipment, technician avatar, time -->
  </div>
</div>
```

SortableJS configuration:

```javascript
new Sortable(columnBodyEl, {
  group: 'kanban',
  handle: '.kc-handle',
  draggable: '.kanban-card',
  animation: 200,
  ghostClass: 'kc-ghost',
  dragClass: 'kc-dragging',
  forceFallback: true,             // consistent visual across desktop + touch
  fallbackOnBody: true,
  fallbackTolerance: 4,            // small movement before drag starts; protects scroll
  delay: 0,                         // mouse: instant on handle
  delayOnTouchOnly: true,           // touch: 80ms long-press to disambiguate scroll
  touchStartThreshold: 4,
  onStart: handleDragStart,
  onMove: handleDragMove,
  onEnd: handleDragEnd,
});
```

### 4.3 Happy path data flow (single valid transition)

```
1. User mousedown/touchstart on .kc-handle
2. SortableJS starts drag, applies kc-dragging class to card, kc-ghost class to placeholder
3. handleDragStart() computes which columns are "valid targets" for this card's status
   and adds .drop-valid to each. Invalid columns get no class.
4. As user moves cursor, handleDragMove() checks which column is currently under cursor:
   - If valid: column stays subtle .drop-valid
   - If invalid: column momentarily gets .drop-invalid-hover (only while hovered)
   - On leave: .drop-invalid-hover is removed; column returns to neutral
5. User releases over a valid column → onEnd fires
6. resolveDropAction(card, column) returns { kind: 'single', action: {...} }
7. SortableJS has already moved the card in DOM (optimistic)
8. We call: api.changeStatus(card.id, action.action)
9. On success:
     - Update state.jobs[i].status to action.to
     - Re-render that one row
     - Refresh state counts (state tab badges)
     - Toast: "Status: <new>"
     - If inspector is open for this card, refresh inspector status pill + Timeline
10. On failure:
     - Move card DOM back to original parent column (we remembered it in onStart)
     - Toast with error.message
```

### 4.4 Ambiguous path (2+ valid transitions)

SortableJS moves the DOM on drop by default. For multi-action and destructive cases, we **immediately revert** that move so the card visually stays put until the user picks an action / confirms. The revert pattern:

```javascript
function revertSortableMove(evt) {
  // evt is the SortableJS onEnd event; from = source col body, oldIndex = source position
  evt.from.insertBefore(evt.item, evt.from.children[evt.oldIndex] || null);
}
```

Flow:

```
Steps 1–6 same as happy path. Then:
7. resolveDropAction returns { kind: 'multi', actions: [...] }
8. We call revertSortableMove(evt) immediately — card returns to source column visually.
9. We position the existing #statusPopover at the drop coordinates, populated with
   only those valid actions.
10. User clicks an action → fire api.changeStatus, then move DOM to target on success
    via the same single-row re-render path the happy path uses.
11. User clicks outside / Esc → popover closes, card stays in source. Zero API calls.
```

### 4.5 Destructive path

```
Steps 1–6 same as happy path, then potentially 4.4 steps 7–9 for the multi case. After we
have a specific resolved action:
1. Check: is action.to in DESTRUCTIVE_STATUSES?
2. If YES: call revertSortableMove(evt) so the card sits in source while the modal shows.
3. confirmDialog.show(card.customer, action) returns Promise<boolean>.
4. User clicks Cancel / Esc / outside → resolves false → no API call, card stays in source.
5. User clicks the destructive button → resolves true → fire api.changeStatus →
   on success, re-render the row (which moves it to the target column naturally).
```

Key invariant: **for multi-action AND destructive paths, the DOM move is reverted first, then conditionally re-applied on success.** Only the happy-path single-non-destructive transition lets SortableJS's optimistic move stand.

### 4.8 Esc-to-cancel during an active drag

SortableJS does not handle Esc natively. We install a `document.keydown` listener that is active **only while a drag is in progress** (tracked via the `body.is-dragging` class — set in `onStart`, cleared in `onEnd`):

```javascript
let activeSortableEvt = null;
let escCancelled = false;

function onSortableStart(evt) {
  activeSortableEvt = evt;
  escCancelled = false;
  document.body.classList.add('is-dragging');
  document.addEventListener('keydown', onEscDuringDrag);
  // ... add .drop-valid to all valid columns
}

function onEscDuringDrag(e) {
  if (e.key !== 'Escape' || !activeSortableEvt) return;
  e.preventDefault();
  escCancelled = true;
  revertSortableMove(activeSortableEvt);
  // SortableJS will still fire onEnd; we guard against acting on it via escCancelled
  // Manually clean visual state since onEnd path is silenced
  cleanupDragVisuals();
}

function onSortableEnd(evt) {
  document.removeEventListener('keydown', onEscDuringDrag);
  document.body.classList.remove('is-dragging');
  if (escCancelled) {
    escCancelled = false;
    activeSortableEvt = null;
    return;  // silenced — no resolveDropAction, no API call
  }
  // ... normal drop resolution path
  activeSortableEvt = null;
}
```

This pattern keeps the listener scoped to drag duration only, so we don't intercept Esc when the user is editing a field elsewhere on the page.

### 4.6 Invalid drop

```
1–4 same as happy path.
5. User releases over an invalid column (or outside any column).
6. SortableJS would normally move the DOM. We intercept onMove with a `return false`
   when target is invalid; SortableJS won't move into that column.
7. If no valid column was hit, card stays in source. No animation glitch.
8. Optional toast: "<source> → <target>: no workflow transition available." (Subtle, 2s.)
9. Zero API calls fire.
```

### 4.7 State invariants

- `state.jobs[].status` is the canonical client-side status. Updated only after `change_status` returns 200.
- The DOM column a card sits in is a guess that may drift for ~50–500ms during optimistic moves; this is by design.
- On `doc_update` realtime event from another user, we reload the affected job and re-render its row, which moves it to the correct column if its status changed elsewhere.

## 5. Drop resolution algorithm

```javascript
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

function resolveDropAction(cardStatus, targetColumnName) {
  const targetSet = COLUMN_STATUSES[targetColumnName];
  if (!targetSet) return { kind: 'none', reason: 'unknown column' };

  const candidates = TRANSITIONS_FROM[cardStatus] || [];
  const valid = candidates.filter(t => targetSet.has(t.to));

  if (valid.length === 0) return { kind: 'none', reason: 'no valid transition' };
  if (valid.length === 1) return { kind: 'single', action: valid[0] };
  return { kind: 'multi', actions: valid };
}
```

`TRANSITIONS_FROM` already exists in `cockpit.js` — same constant the status popover uses for resolving valid transitions. No duplication.

## 6. Confirmation modal

```
┌─ Confirm action ────────────┐
│  Mark Sunrise Diner as Lost?│
│  This closes the job and    │
│  removes it from the active │
│  pipeline.                  │
│                             │
│   [ Cancel ] [Mark as Lost] │
└─────────────────────────────┘
```

Behaviour:

- Centered modal with overlay (`rgba(15,23,42,0.18)` + `backdrop-filter: blur(2px)`), same overlay treatment as the inspector
- Default focus on **Cancel** button (so accidental Enter doesn't fire)
- Esc closes the modal as Cancel
- Outside-click closes the modal as Cancel
- Destructive button uses `--c-rose` color, "Mark as Lost"/"Mark as Spam"/etc. — text matches the workflow action label
- Focus trap: Tab cycles between Cancel and the destructive button only
- ARIA: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing at the question

Returns a `Promise<boolean>`. Resolve `true` on destructive button, `false` on any cancel path.

## 7. Visual feedback states

| State | Selector | Style |
|---|---|---|
| Idle hover on handle | `.kc-handle:hover` | `cursor: grab` |
| Idle hover on body | `.kc-body:hover` | inherit row hover (already exists) |
| Source-spot ghost (placeholder left behind) | `.kanban-card.kc-ghost` | `opacity: 0.35`; `pointer-events: none`. SortableJS applies this via `ghostClass: 'kc-ghost'`. |
| Floating clone (follows cursor) | `.kanban-card.kc-dragging` | full opacity card, slight rotation `+1°`, shadow lifted. SortableJS applies this via `dragClass: 'kc-dragging'`. |
| Valid drop targets (all of them) | `.kanban-col-body.drop-valid` | inner box-shadow `inset 0 0 0 2px var(--brand-100)`, slight bg tint `var(--brand-50)`. Always visible during drag. |
| Invalid column currently hovered | `.kanban-col-body.drop-invalid-hover` | inner box-shadow `inset 0 0 0 2px var(--c-rose-bg)`, NO bg fill. Removed on `dragleave`. **Only one column at a time.** |
| Empty column drop placeholder | `.kanban-col-body:empty::after` (during drag) | dashed 1px border, 60px height, centered text "Drop here to {action label}" when target is valid, "No transition from {current}" when invalid. Hidden when drag ends. |
| Cursor during drag | `body.is-dragging` | `cursor: grabbing` globally |

The "no board-wide red" rule is enforced by NOT applying `.drop-invalid` to invalid columns at drag start. Only on hover.

## 8. Empty column handling

The current kanban renders empty columns with zero height beyond the header. During drag, we add a visible drop target inside each column body so users can drop into empty columns:

```css
body.is-dragging .kanban-col-body:empty {
  min-height: 64px;
  border: 1px dashed var(--border-strong);
  border-radius: 6px;
  margin: 4px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
  font-size: 12px;
}
body.is-dragging .kanban-col-body:empty::after {
  content: 'Drop here';
}
body.is-dragging .kanban-col-body.drop-valid:empty::after {
  content: 'Drop here to ' attr(data-drop-action);
}
```

`data-drop-action` is set dynamically during `onStart` based on the card being dragged.

## 9. Files and deploy

### 9.1 Vendoring SortableJS

- Source: https://github.com/SortableJS/Sortable/releases/tag/1.15.6
- File: `Sortable.min.js` (the UMD minified build), ~12KB
- License: MIT — record in `baro_crm/baro_crm/public/vendor/LICENSE-Sortable.txt`
- Pin to v1.15.6 — do not auto-upgrade
- Add note in `DEPLOY.md` under "Third-party dependencies": "SortableJS v1.15.6, MIT, vendored in `baro_crm/public/vendor/`. No npm/build step required."

### 9.2 install.sh asset materialization + verification (new step 5b)

**Symlink-only assets have already produced 404s on this site.** Step 5b therefore (a) replaces any existing `sites/assets/baro_crm` with a **real directory containing copied files**, and (b) verifies it via two-stage smoke test: real-file presence + HTTP fetch through the actual nginx the browser hits.

Critical correctness detail: the HTTP smoke test must **not** use `http://localhost:8080` from inside the backend container — `localhost` there resolves to backend (gunicorn), not the nginx frontend, and gunicorn does not serve `/assets/*`. We use Docker's internal DNS service name `frontend:8080` instead, which works regardless of how the host publishes ports.

```bash
say "5b/6 · Materializing assets as real files + verifying via nginx"
docker compose -f "$BARO_COMPOSE" exec -T backend bash <<'ASSET_CHECK_EOF'
set -e
cd /home/frappe/frappe-bench

# ---------- 1. Replace symlink with a real directory of copied files ----------
ASSET_DIR=sites/assets/baro_crm
SRC_DIR=apps/baro_crm/baro_crm/public

if [ ! -d "$SRC_DIR" ]; then
  echo "FAIL source assets missing at $SRC_DIR"
  exit 1
fi

# Wipe whatever's there (symlink or directory) and recreate as a real dir
rm -rf "$ASSET_DIR"
mkdir -p "$ASSET_DIR"
cp -R "$SRC_DIR"/* "$ASSET_DIR"/

# Confirm it's a real directory, not a symlink
if [ -L "$ASSET_DIR" ]; then
  echo "FAIL $ASSET_DIR is a symlink after copy — should be a real directory"
  exit 1
fi

# ---------- 2. Real-file size check (catches empty/broken files) ----------
echo "▸ Real files in $ASSET_DIR:"
for f in css/cockpit.css js/cockpit.js vendor/Sortable.min.js; do
  full="$ASSET_DIR/$f"
  if [ ! -f "$full" ]; then
    echo "  FAIL $f does not exist at $full"
    exit 1
  fi
  if [ -L "$full" ]; then
    echo "  FAIL $f is a symlink — should be a real file"
    exit 1
  fi
  size=$(stat -c%s "$full" 2>/dev/null || echo 0)
  if [ "$size" -lt 100 ]; then
    echo "  FAIL $f exists but is empty/broken ($size bytes)"
    exit 1
  fi
  echo "  OK   $f ($size bytes, real file)"
done

# ---------- 3. HTTP fetch through the actual nginx the user reaches ----------
# Use Docker's internal DNS: 'frontend' resolves to the nginx container.
# Override via env if your compose file uses a different service name.
FRONTEND_SVC="${BARO_FRONTEND_SVC:-frontend}"
FRONTEND_PORT="${BARO_FRONTEND_PORT:-8080}"

echo "▸ HTTP smoke through nginx at http://${FRONTEND_SVC}:${FRONTEND_PORT} (real user path):"
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

**Why this catches what symlinks miss:** Frappe's `bench setup symlinks` creates `sites/assets/baro_crm` as a symlink to `apps/baro_crm/baro_crm/public/`. Nginx in some configurations (and especially under permission-restricted Docker mounts) refuses to serve files reached through a symlink, returning 404 with no warning. Real copied files bypass that class of failure entirely. The trade-off — slightly stale files if you forget to re-run install.sh after a code change — is acceptable for a project this small, and install.sh is the canonical "I changed something" command anyway.

### 9.3 DEPLOY.md additions

- New section: "Third-party dependencies" — lists Sortable v1.15.6 with source URL + license
- New section: "Asset verification" — explains how the install.sh smoke test works and what to do if it fails (re-run `bench setup symlinks`, check `sites/assets/baro_crm`, restart container)

## 10. Out-of-scope (for this design)

- Phone-screen support (< 768px). Drag/drop on a 6" screen is broken UX regardless of library; cockpit on mobile should fall back to the status pill popover, not enable kanban drag.
- Multi-select drag.
- Undo for non-destructive transitions. (Destructive use the confirm modal as a pre-action gate.)
- Cross-column manual ordering. Cards order by `modified desc`, no manual sort.
- Pre-filtering valid actions by user role on the client. The server `change_status` enforces; rejection → rollback + toast.
- The "New Repair Job" in-cockpit create drawer. **This is a separate sub-project (F) in the roadmap, slated for after E ships.**

## 11. Testing and sign-off

### 11.1 Automated (run by install.sh on every deploy)

1. `sites/assets/baro_crm/{css,js,vendor}/*` exist and are > 100 bytes (`stat -L -c%s`).
2. `curl -o /dev/null -w '%{http_code}' http://localhost:8080/assets/baro_crm/{css/cockpit.css, js/cockpit.js, vendor/Sortable.min.js}` returns 200 for each.
3. `bench --site frontend list-apps` includes `baro_crm`.
4. `bench --site frontend execute baro_crm.api.repair_job.get_state_counts` returns valid JSON.

### 11.2 Manual browser acceptance (run on Chrome desktop + Safari iPad)

| # | Test | Expected outcome |
|---|---|---|
| 1 | Open `/repair-jobs` while signed in | Cockpit loads, no console errors, state tabs visible |
| 2 | Switch to Kanban view | Five group columns render with cards in the correct columns by status |
| 3 | Hover a card | Cursor changes; left-side grip icon (`.kc-handle`) visible |
| 4 | Click card body (not handle) | Inspector opens for that job; no drag started |
| 5 | Grab handle on a `New` card; drag toward "Sales" | Card opacity drops; "Sales" gets subtle valid border; release on Sales → since "Offer Diagnostics" is the only valid transition into Sales from New, fires directly; toast "Status: Diagnostics Offered"; card now in Sales column |
| 6 | Drag a `Repair Completed` card to "Money & Care" | Single valid transition "Send Invoice" fires directly without popover |
| 7 | Drag a `New` card to "Money & Care" (no valid path) | Hovering Money & Care shows subtle rejection styling on that column only (board not screaming red); release → ghost snaps back; **zero** API calls in devtools Network tab |
| 8a | Drag a **New** card to "Out" (multi-action source) | From `New`, three transitions land in Out: `Mark Lost`, `Mark Spam`, `Mark Unrelated`. Expected: card snaps back to source (revert), popover appears at drop point with three options. Pick `Mark Lost` → confirm modal appears with Sunrise Diner name and default focus on Cancel → Esc cancels (card stays in source, zero API calls) → re-do, confirm "Mark as Lost" → API fires once, card moves to Out. |
| 8b | Drag a **Diagnostics Offered** card to "Out" (single-action source) | From `Diagnostics Offered`, only `Mark Lost` lands in Out. Expected: NO popover (single valid action) → confirm modal appears directly with default focus on Cancel → confirm fires API → card moves to Out. |
| 9 | Open `/repair-jobs` in a second browser tab; drag a card in tab 1 | Tab 2 reflects the change within ~600ms (realtime `doc_update`) |
| 10 | iPad: swipe up/down inside a column body (not on a handle) | Column scrolls; no drag initiated |
| 11 | iPad: long-press handle, drag to adjacent column | Drag works; post-drop UI is correct |
| 12 | Drag, then disconnect network mid-drop | API fails; card snaps back; toast shows network error |
| 13 | Drag as a user whose role lacks the workflow action | API rejects; card snaps back; toast: "You don't have permission to {action}" |
| 14 | Press Esc during an active drag | Drag cancels; card returns to source column; no API call. **Implementation requirement:** SortableJS has no native Esc support — the cockpit must install a `document.keydown` listener that, while a drag is active, intercepts Esc, calls the same `revertSortableMove` helper used for multi-action/destructive paths, removes `.kc-dragging` / `.kc-ghost` / `.drop-valid` / `.drop-invalid-hover` / `.is-dragging` classes, and silences the next `onEnd` so it doesn't fire `change_status`. See §4.8. |

### 11.3 Sign-off criteria

Feature is "done" when:

- All 4 automated checks pass in install.sh on the Florida server.
- All 14 manual checks pass on Chrome desktop AND on iPad-class Safari.
- A walkthrough recording (or 5–8 screenshots) covering tests #5, #7, #8, #10, #11 is added to `crm-prototype/README.md` for future regression reference.

## 12. Related work flagged for follow-up

### F. In-cockpit Create Repair Job (drawer)

**Not part of this design.** Added to roadmap as sub-project F, immediately after E (this design).

Today the cockpit's "New Repair Job" button links to `/app/repair-job/new`, the standard ERPNext form. That contradicts the "employees live in the cockpit" principle and is a paper cut every time someone clicks it. The fix is a right-side drawer (mirrors the inspector pattern) that creates a Repair Job inline with the minimum required fields. Spec to follow when E ships.

---

## Appendix A — Open implementation notes

- The existing `cockpit.js` is ~1050 lines; adding drag logic brings it to ~1300. Still single-file. Sections are numbered 1–15 with header comments; drag logic becomes section 16.
- `Sortable.min.js` v1.15.6 sha256 must be recorded in `DEPLOY.md` for supply-chain verification. The implementer fetches the file, computes sha256, records it.
- The `forceFallback: true` SortableJS option is non-obvious but important: native HTML5 drag-and-drop has inconsistent visuals across browsers and breaks on iPad. The fallback mode renders the ghost via DOM, which is consistent and touch-compatible.
- Frappe's website asset pipeline normally needs `bench build` to update fingerprinted bundles. We bypass this by serving directly from `public/` (no build step). The trade-off is no minification — but our cockpit.js is already small and modern browsers handle it fine.
