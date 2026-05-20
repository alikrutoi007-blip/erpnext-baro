# Baro CRM Roadmap

Date: 2026-05-19 · **Revised 2026-05-21**
Status: Decomposition only. Each sub-project below gets its own design doc + plan before any code.

---

## Revision 2026-05-21 — expanded to 8 sub-projects

Original roadmap had 5 sub-projects (A–E). E shipped 2026-05-20. During the F brainstorm on 2026-05-21, user surfaced two additional sub-projects (K, L) and confirmed the lead-intake architecture is status-based (no new DocType).

**Final sub-project list (8 items), in execution order:**

| # | ID | Sub-project | Effort | Status |
|---|---|---|---|---|
| 1 | F | **Create Repair Job drawer (in-cockpit) + minimal dedup pre-check** | 2–3 days | in flight (mid-brainstorm 2026-05-21) |
| 2 | J | **ERPNext workspace integration** — cockpit added to main sidebar, default landing for `Baro Dispatcher` role profile | 0.5–1 day | pending |
| 3 | G | **Views + city/state filters** — 10 named views (My Queue, Unassigned, Active, Today, Needs Follow-up, Production, Waiting Money, Warranty, Archive, Spam/Unrelated), city chip under state tabs | 2–3 days | pending |
| 4 | K | **Existing Customer Migration** — bulk import 5–6k existing clients (Customer, Contact, Address; later Customer Equipment / history). New fields: `normalized_phone`, `legacy_customer_id`, `source_system`, `import_batch_id`, `duplicate_warning`, `service_state`, `city_area`. Dry-run first, chunks of 500–1000. **No auto-fuzzy-merge**; exact phone/email/name/address only, fuzzy matches become `duplicate_warning` flags. | 2–4 days | pending — blocks H and B |
| 5 | H | **Full Dedup UX + Attach-to-existing flow** — Possible Match panel with `[Attach to existing RJ]` / `[Create new anyway]` buttons; backend `find_possible_matches(phone, name, address, equipment)`; UI for attaching a new call to an existing active RJ | 3–4 days | pending |
| 6 | L | **Client Work Group + Teams Automation** — on `Diagnostics Paid` or `Technician Assigned`, create Project/Client Work Group if not already created. Add Dispatcher, Estimate Manager, Production Manager, Technician, Supply, Accounting, Regular Client Manager. Default ToDos/Tasks. Store back-reference on Repair Job (`client_group_project`, `client_work_group` — fields already exist). Teams sync is **phase 2**: create/update Teams chat/channel via Microsoft Graph / Power Automate / Make, store Teams link on RJ. See existing `docs/lead_group_automation.md`. | 2–4 days CRM + 2–4 days Teams | pending |
| 7 | I | **Lead Intake architectural decision** — confirmed status-based 2026-05-21: `New` / `Need Follow-up` are intake (pre-qualification); `Diagnostics Offered` onward is qualified RJ; Spam/Unrelated/Lost are terminal pre-qual buckets. Implementation = formalizing views in G + Spam/Unrelated sidebar item. | ~1 day | pending — folds into G |
| 8 | B | **Customer Chart page** at `/customers/<id>` — all calls, SMS, RJs, invoices, warranties, addresses, equipment, notes for one customer. Source of truth for repeat customers. | 3–5 days | pending — best after K loads real history |

**Sub-projects shipped before this revision:**

- A (Sheets→ERPNext ingest) — script exists at `scripts/ingest_sheet_to_erpnext.py`; first real RJ produced (RJ-2026-00001). Needs production hardening (separate from F).
- C (Executive insights wiring) — static mockup at `crm-prototype/executive-insights.html`; not yet wired to live data. Deferred to post-Customer-Chart (B).
- D (Production hardening + backups) — not done. Independent track. Should happen alongside, not after.
- ~~E~~ (Kanban drag/drop) — **✓ Shipped 2026-05-20.** See `2026-05-20-kanban-drag-drop-design.md`.

**For F specifically (2026-05-21 scope decision):**

- Drawer itself + audit polish (status popover bug fix, `extractError`, focus trap helper, kanbanCardHtml/renderRow extraction, `state.jobsById` map)
- **Minimal dedup pre-check only**: warning banner if normalized phone matches existing Customer/Contact OR if active RJ exists for same customer/phone/equipment within recent window. Buttons: `[Open existing]` / `[Create anyway]`. No fuzzy auto-link, no merge, no attach flow — those belong to H.
- Scale handling: kanban columns natural height (no internal scroll), sticky column heads, page-level scroll, API limit raised to 500 default / 2000 max, "Load more" affordance, `state.jobsById` map.

---

## Why this doc exists

The user asked to plan five things together: (1) Sheets→ERPNext ingest, (2) Customer chart deep view, (3) Executive insights page integration, (4) Production hardening + backups, (5) Kanban drag/drop in the cockpit. That's five independent sub-projects — each needs its own design cycle. This doc decomposes them, sequences them, and surfaces the open questions so we know what to deep-brainstorm first.

---

## URGENT — workspace deletion to recover

When `baro_crm` was installed, `bench migrate` deleted four workspaces that were live and important. They were not declared in any installed app, so migrate treated them as orphans.

Deleted:
- `Baro Dispatch Desk`
- `Baro Production Desk`
- `Baro Manager Desk`
- `Baro CRM Demo`

These were built by:
- `scripts/enhance_repair_job_experience.py` (the three role desks + their kanban boards + number cards)
- `scripts/setup_demo_environment.py` (the demo workspace + demo data references)

**Recovery is one command each** (both scripts are idempotent):

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\enhance_repair_job_experience.py --execute
python .\scripts\setup_demo_environment.py --execute
```

**Going forward**, every workspace that should survive `bench migrate` must be declared inside the `baro_crm` app's `workspace/` directory (or another installed app). I'll fold this into Sub-project #3 (Executive insights integration) so all four role desks + the cockpit + insights workspace are managed declaratively.

Repair Job custom field/section UX from `enhance_repair_job_experience.py` should still be intact (those are Customizations on the DocType, not workspaces). To confirm: open any Repair Job in `/app/repair-job/<name>` and check that the sections (Intake, Call Intelligence, Equipment and Problem, Money, Team, etc.) are still there. If not, re-run the script.

---

## Where the project is right now

**Live in ERPNext (Tailscale `http://100.127.172.110:8080`):**

- `Repair Job` custom DocType (45 fields, naming `RJ-.YYYY.-`, workflow with 20 states / 28 transitions, track_changes on)
- 7 Baro role profiles
- Customizations on `Repair Job` form (sections, required fields, list filters)
- 8 demo Repair Jobs (`RJ-2026-00002`–`-00009`) — data intact
- 1 real Repair Job from ingest (`RJ-2026-00001` Marriott Residence Inn)
- `baro_crm` Frappe app installed, providing `/repair-jobs` cockpit + `service_state` Custom Field on Repair Job

**Already written (Python scripts in `scripts/`):**

- `ingest_sheet_to_erpnext.py` — Sheets→ERPNext bridge with dry-run + per-row/per-call-id selectors
- `enhance_repair_job_experience.py` — form UX
- `setup_demo_environment.py` — demo data + workspaces (deleted by migrate, recoverable)
- `create_repair_job_doctype.py`, `create_repair_job_workflow.py`, `create_role_profiles.py`, `create_mvp_backlog_tasks.py`, `verify_*` — all complete

**Live HTML mockups (in `crm-prototype/`):**

- `repair-job-workspace.html` — production-style cockpit (now also live as the Frappe Page)
- `executive-insights.html` — exec dashboard, static
- `index.html` — earlier command center prototype

**Existing Obsidian docs:**

- `ERPNext/Repair Job Card.md`, `ERPNext/Setup Progress.md`, `ERPNext/Self Hosting Florida Plan.md`, etc.

---

## The 5 sub-projects

### Sub-project A · Sheets → ERPNext ingest, hardened to production

**Status:** Functional script exists (`scripts/ingest_sheet_to_erpnext.py`). First real Repair Job created. Now needs hardening for unattended operation.

**Goal:** Every new call in the `Zadarma real time calls` sheet becomes a Repair Job in ERPNext within ~2 minutes, with audit trail in the sheet and JSONL log, with no duplicates.

**What's done:**
- Read Sheets, parse `Person--Business` pattern, normalize phones, detect Baro DIDs
- Dry-run by default, `--execute` writes
- `zadarma_recording_url` + `zadarma_call_id` idempotency
- Sheet → Customer, Contact, Address, Repair Job
- Single-row test verified (RJ-2026-00001)

**What's left:**
1. Sheet write-back columns: `ERPNext Repair Job`, `ERPNext ingest status`, `ERPNext ingest error`, `ERPNext synced at`. Bot writes these on every run.
2. Scheduled execution: `systemd` user service on the Florida server (or Windows Task Scheduler if it lives on Ali's workstation). Every 90 sec, dry-run all "New" status rows, only execute rows that have not been synced.
3. Robust error handling: connection retries (Sheets API throttling, ERPNext 504), partial failures don't block other rows.
4. Logging: every row processed gets one line in `logs/ingest.jsonl` with call_id, action (create/update/skip), latency, error.
5. Alerting: if N consecutive failures or no successful run in 30 min, send notification (Telegram / Slack / email — pick one).
6. Run as the dedicated `baro-integration@local` ERPNext user (part of #D below).

**Open design questions:**
- Where does the worker run? Florida server (closest to ERPNext, but also closest to a single point of failure), or Ali's workstation, or a small VPS?
- One-shot per-run vs long-running daemon?
- Where do we set up the alert sink?
- How aggressive on rate limits? Sheets allows ~60 req/min; ERPNext we can hit harder.

**Effort:** 3–5 days.

**Depends on:** Dedicated integration user (part of #D). Otherwise can run independently.

---

### Sub-project B · Customer chart deep view

**Status:** Not built. The employee interviews (Elena, Menna, Ghassan) all asked for exactly this. The Repair Job cockpit is the *list* view; the customer chart is the *deep* view — one URL per customer with their full history.

**Goal:** A URL at `/customers/<customer-id>` (inside the baro_crm app) that shows everything about one customer in one screen, like a medical chart.

**Sections to include:**
- Header: name, primary contact, primary address, total revenue, total jobs, last service date
- Sticky timeline (all events across all jobs: call → diagnostic → repair → invoice → warranty)
- All Repair Jobs (mini cards, filterable by status/year)
- All Sales Invoices + Payment Entries
- All Warranty Cases
- All Contacts (with phone/email)
- All Addresses
- All ToDos/Tasks linked to the customer
- Notes/comments composer (visible to all team members)
- Customer health signals: missed calls, overdue invoices, expiring warranties, unfollowed-up estimates

**Open design questions:**
- Should this be a Frappe Page (under `/app/customer/<id>` enhanced) or a separate `/customers/<id>` route in baro_crm?
- How do we surface "this customer has had 2 callbacks under warranty" without being annoying?
- Print/PDF view for handing physical client charts to technicians on-site?
- Do we want to merge duplicate customers from the same business? (separate problem, flag for later)

**Effort:** 3–5 days.

**Depends on:** Real data flowing (so the customer pages aren't empty) — i.e., #A running for a while.

---

### Sub-project C · Executive insights integration

**Status:** Static HTML mockup exists (`crm-prototype/executive-insights.html`). Not wired to live ERPNext data. Lives outside the app.

**Goal:** Move the exec dashboard inside the `baro_crm` app at `/insights` so CEO/directors get a live view of revenue, funnel, source ROI, technician leaderboard, etc.

**What's already designed (from the mockup):**
- 8 KPIs with sparklines and period-over-period delta
- Revenue 30-day chart with previous-period comparison
- Lost reasons donut
- 7-step pipeline funnel with drop-off reasons
- Marketing source ROI table
- Cities breakdown
- Technician leaderboard
- Activity feed
- Date range selector (Today / 7d / 30d / 90d / YTD / Custom)

**What's left:**
1. New Frappe Page route `/insights` (parallel to `/repair-jobs`), same chrome-hiding pattern
2. New whitelisted API methods: `get_kpis`, `get_revenue_trend`, `get_funnel`, `get_lost_reasons`, `get_source_roi`, `get_city_breakdown`, `get_tech_leaderboard`, `get_activity`
3. Each method takes a `period` arg (days) and returns the shape the existing JS expects
4. SQL aggregations need to be efficient — pre-cache where possible
5. Permission gate: only roles with "view dashboard" can hit `/insights` (configurable)
6. Declarative workspace entry inside baro_crm so it shows in the ERPNext sidebar
7. Fold the deleted role desks (Dispatch / Production / Manager) into baro_crm's workspace/ so they survive future migrates

**Open design questions:**
- Auto-refresh interval? (mockup shows "Live · updated 2 min ago")
- Forecast model — keep it simple (extrapolate from pipeline value) or skip until we have more data?
- Export PDF — keep as a placeholder for now or build it?

**Effort:** 4–6 days.

**Depends on:** Real data (A running for ~2 weeks so trends are meaningful) — and the demo data restoration (for showing leadership in the meantime).

---

### Sub-project D · Production hardening + backups

**Status:** Not done. Foundation work, not a feature.

**Goal:** Sleep at night with real client data flowing. Five concrete deliverables:

1. **Credential rotation** + **dedicated integration user.** The API key pasted in chat earlier — rotate. Create `baro-integration@local` with a tight Role Profile (Sales User + Maintenance User + Projects User + a custom `Baro Repair Job Writer` role) and use *its* keys in `.env`. Revoke owner's API tokens.

2. **HTTPS termination on the ERPNext server.** Today: HTTP only via Tailscale. To open access to anyone outside the tailnet (e.g., a Vercel-hosted insights page for the board, or a customer portal later), we need Let's Encrypt + Traefik or Cloudflare Tunnel. Decision: tunnel is simpler, Traefik gives more control.

3. **Nightly backups, with offsite + tested restore.** `bench backup --with-files` on cron, copy to external HDD, then to Backblaze B2 (cheapest S3-compatible). **And a documented restore drill** to a second machine — backups you haven't restored aren't backups.

4. **Server hardening checklist:** UPS plugged in and tested, BIOS "power on after AC loss" verified, static LAN IP, BIOS sleep disabled, wired Ethernet, SSH locked to Tailscale or key-only.

5. **Monitoring:** uptime ping (uptimerobot free tier), disk-space alert (>80% triggers email), container health check.

**Open design questions:**
- HTTPS: Cloudflare Tunnel (zero infra changes) vs Traefik on the server (more control, more work)?
- Backup destination: Backblaze B2 ($6/TB/mo) vs Cloudflare R2 ($15/TB/mo egress-free) vs AWS S3 (most expensive)?
- Monitoring: free tools (uptimerobot + healthchecks.io) vs paid (Better Stack)?

**Effort:** 2–3 days for steps 1, 3, 4, 5. Add 1 day for HTTPS if we pick Tunnel; +2 days for Traefik.

**Depends on:** Nothing. **This is the right starter** — it unblocks everything else and protects against the worst failure modes.

---

### Sub-project E · Kanban drag/drop in cockpit

> **✓ Shipped 2026-05-20.** Spec: `2026-05-20-kanban-drag-drop-design.md` (Status: Shipped). Plan: `docs/superpowers/plans/2026-05-20-kanban-drag-drop.md`. All 4 automated checks + 12/14 desktop manual tests pass (tablet tests deferred pending iPad). SortableJS v1.15.6 vendored at `baro_crm/public/vendor/`. Git tag: `kanban-dnd-shipped`.

**Status:** Not built. Smallest of the five.

**Goal:** In the cockpit kanban view (already exists in `repair-job-workspace.html`), let users drag a card from one column to another to advance its workflow.

**User's stated constraint (verbatim):**

> drag/drop must resolve target column to a valid workflow action and call `baro_crm.api.repair_job.change_status`

That's the right pattern. Implementation:

1. HTML5 drag/drop on `.kanban-card` (draggable) and `.kanban-col-body` (drop target)
2. Each column's data attribute lists its valid statuses (e.g., the "Sales" column maps to `Diagnostics Offered`, `Waiting Prepayment`, `Diagnostics Paid`, `Estimate Sent`, `Waiting Client Approval`)
3. On drop:
   - Look up `TRANSITIONS_FROM[card.status]` for any action whose `to` status is in the target column's status set
   - If exactly one valid transition: call `change_status(card.id, action)`
   - If multiple valid: open status popover anchored to the drop point, let user pick which transition
   - If none: toast "Cannot move from {currentStatus} to {targetColumn} — no workflow transition"
4. Visual feedback: card has reduced opacity during drag, valid drop columns highlight green, invalid columns highlight red
5. Touch support via Pointer Events API (so it works on tablets too)
6. Optimistic update with rollback on API failure
7. Accessibility: keyboard-equivalent — focus a card, press Enter, get the status popover (already exists for inspector); we don't lose anything for keyboard users

**Open design questions:**
- Library or vanilla? Vanilla HTML5 drag/drop is awkward; SortableJS is 12KB and battle-tested. Recommendation: SortableJS.
- Multi-select drag (move 5 cards at once)? Probably not in v1.
- Stretch: drag to "Lost"/"Spam" requires a confirmation modal?

**Effort:** 1–2 days.

**Depends on:** Nothing. Standalone enhancement to cockpit JS.

---

## Recommended sequencing

The boring answer is also the right one:

```
1. D (Production hardening)     ── 2–3 days ──  Foundation. Credentials, backups, HTTPS.
2. A (Ingest hardening)         ── 3–5 days ──  Where business value lives. Needs D's integration user.
3. E (Kanban drag/drop)         ── 1–2 days ──  Quick UX win while A is settling in.
4. B (Customer chart)           ── 3–5 days ──  Highest-value greenfield, needs A's data.
5. C (Executive insights)       ── 4–6 days ──  Most polish, lowest urgency, needs A's data for meaningful trends.

Total: ~13–21 days of focused work.
```

**Why D first:** A single SSD failure right now would lose the demo data, the real RJ-2026-00001, and the `baro_crm` install. Without rotated credentials, the API tokens in chat are still live. Without HTTPS, we can't extend access beyond the tailnet. Doing D first removes the single largest project risk.

**Why A second:** It's the biggest *business value* item. Once D's integration user exists, A is unblocked.

**Why E third:** Cheap, high-perceived-value, doesn't need anything from A or B.

**Why B fourth:** Greenfield, big value, but the customer chart is meaningless without data — which A produces.

**Why C last:** It's the most polished mockup we have, so the static version can stand in for live exec demos for a while. Real wiring is highest effort and lowest urgency.

**Alternative if you disagree:** If business pressure is "the team needs to see calls flowing through the cockpit *now*", flip the order to A→D→E→B→C — accept the risk window while we set up backups in parallel.

---

## Independent of all five: restore the deleted workspaces NOW

Before anything else (5 minutes):

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\enhance_repair_job_experience.py --execute
python .\scripts\setup_demo_environment.py --execute
```

This restores Baro Dispatch Desk, Baro Production Desk, Baro Manager Desk, Baro CRM Demo, and their kanban boards. Idempotent — safe if some already came back.

---

## What we're brainstorming next

Pick one of A/B/C/D/E to deep-design — that one gets its own spec doc, then its own implementation plan.

My recommendation: **D first.** Smallest scope, highest leverage, unblocks everything.

If you want to push business value first: **A first** (ingest hardening).

If you want a fast UX win: **E first** (kanban drag/drop, ~1–2 days, no dependencies).

Decision back to you.
