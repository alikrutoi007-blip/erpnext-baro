/* =============================================================================
 *  baro_crm cockpit
 *  ---------------------------------------------------------------------------
 *  Wired to Frappe whitelisted methods under baro_crm.api.repair_job.*
 *  Reads real Repair Job rows, edits them inline (auto-save on blur), writes
 *  every change through Frappe so it shows up in the timeline (Version log +
 *  Comment log).
 *
 *  No build step — pure ES module-free IIFE. Drop into Frappe public/js, get
 *  served at /assets/baro_crm/js/cockpit.js after `bench build` or directly
 *  (Frappe serves public/ as static in dev).
 * ========================================================================== */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // 1. Constants — workflow, statuses, fields
  // ---------------------------------------------------------------------------
  const STATUSES = [
    { name: 'New',                     color: 'blue' },
    { name: 'Need Follow-up',          color: 'amber' },
    { name: 'Diagnostics Offered',     color: 'cyan' },
    { name: 'Waiting Prepayment',      color: 'amber' },
    { name: 'Diagnostics Paid',        color: 'emerald' },
    { name: 'Technician Assigned',     color: 'indigo' },
    { name: 'Diagnostics In Progress', color: 'indigo' },
    { name: 'Diagnosis Completed',     color: 'emerald' },
    { name: 'Estimate Sent',           color: 'cyan' },
    { name: 'Waiting Client Approval', color: 'amber' },
    { name: 'Parts Needed',            color: 'amber' },
    { name: 'Repair In Progress',      color: 'indigo' },
    { name: 'Repair Completed',        color: 'emerald' },
    { name: 'Invoice Sent',            color: 'cyan' },
    { name: 'Paid',                    color: 'emerald' },
    { name: 'Warranty Active',         color: 'violet' },
    { name: 'Closed',                  color: 'slate' },
    { name: 'Lost',                    color: 'rose' },
    { name: 'Spam',                    color: 'rose' },
    { name: 'Unrelated',               color: 'slate' },
  ];
  const STATUS_MAP = Object.fromEntries(STATUSES.map(s => [s.name, s]));

  // Workflow transitions — map (currentStatus -> [{ label, action, nextStatus }])
  // This must match scripts/create_repair_job_workflow.py TRANSITIONS list.
  const TRANSITIONS = [
    ['New', 'Mark Need Follow-up', 'Need Follow-up'],
    ['New', 'Offer Diagnostics', 'Diagnostics Offered'],
    ['New', 'Mark Lost', 'Lost'],
    ['New', 'Mark Spam', 'Spam'],
    ['New', 'Mark Unrelated', 'Unrelated'],
    ['Need Follow-up', 'Offer Diagnostics', 'Diagnostics Offered'],
    ['Need Follow-up', 'Mark Lost', 'Lost'],
    ['Need Follow-up', 'Mark Unrelated', 'Unrelated'],
    ['Diagnostics Offered', 'Request Prepayment', 'Waiting Prepayment'],
    ['Diagnostics Offered', 'Mark Diagnostics Paid', 'Diagnostics Paid'],
    ['Diagnostics Offered', 'Mark Lost', 'Lost'],
    ['Waiting Prepayment', 'Mark Diagnostics Paid', 'Diagnostics Paid'],
    ['Waiting Prepayment', 'Mark Need Follow-up', 'Need Follow-up'],
    ['Waiting Prepayment', 'Mark Lost', 'Lost'],
    ['Diagnostics Paid', 'Assign Technician', 'Technician Assigned'],
    ['Technician Assigned', 'Start Diagnostics', 'Diagnostics In Progress'],
    ['Diagnostics In Progress', 'Complete Diagnosis', 'Diagnosis Completed'],
    ['Diagnosis Completed', 'Send Estimate', 'Estimate Sent'],
    ['Estimate Sent', 'Wait Client Approval', 'Waiting Client Approval'],
    ['Waiting Client Approval', 'Mark Parts Needed', 'Parts Needed'],
    ['Waiting Client Approval', 'Start Repair', 'Repair In Progress'],
    ['Waiting Client Approval', 'Mark Lost', 'Lost'],
    ['Parts Needed', 'Start Repair', 'Repair In Progress'],
    ['Repair In Progress', 'Complete Repair', 'Repair Completed'],
    ['Repair Completed', 'Send Invoice', 'Invoice Sent'],
    ['Invoice Sent', 'Mark Paid', 'Paid'],
    ['Paid', 'Activate Warranty', 'Warranty Active'],
    ['Warranty Active', 'Close Job', 'Closed'],
  ];

  // Fast lookup: which transitions are valid from a given current status?
  const TRANSITIONS_FROM = {};
  for (const [from, action, to] of TRANSITIONS) {
    (TRANSITIONS_FROM[from] = TRANSITIONS_FROM[from] || []).push({ action, to });
  }

  // The 4 active service states + an "All" pseudo-state
  const STATE_TABS = [
    { key: 'All',         label: 'All',         cls: '' },
    { key: 'Texas',       label: 'Texas',       cls: 's-tx' },
    { key: 'Florida',     label: 'Florida',     cls: 's-fl' },
    { key: 'New York',    label: 'New York',    cls: 's-ny' },
    { key: 'New Jersey',  label: 'New Jersey',  cls: 's-nj' },
  ];

  // Inline-editable fields — metadata that controls the inline editor.
  // Keys must match the EDITABLE_FIELDS allowlist in repair_job.py exactly.
  const FIELD_META = {
    customer:           { label: 'Customer',           type: 'link',     doctype: 'Customer',      required: true },
    contact:            { label: 'Contact',            type: 'link',     doctype: 'Contact' },
    service_address:    { label: 'Service address',    type: 'link',     doctype: 'Address' },
    caller_phone:       { label: 'Caller phone',       type: 'data' },
    business_phone_did: { label: 'Business DID',       type: 'data' },
    area:               { label: 'Area',               type: 'data' },
    service_state:      { label: 'Service state',      type: 'select',   options: ['', 'Texas', 'Florida', 'New York', 'New Jersey'] },
    marketing_source:   { label: 'Marketing source',   type: 'data' },
    equipment_type:     { label: 'Equipment',          type: 'data' },
    equipment_brand:    { label: 'Brand',              type: 'data' },
    equipment_model:    { label: 'Model',              type: 'data' },
    symptom:            { label: 'Symptom',            type: 'textarea' },
    urgency:            { label: 'Urgency',            type: 'select',   options: ['', 'Emergency', 'Today', 'This Week', 'Scheduled', 'Unknown'] },
    diagnostic_price:   { label: 'Diagnostic price',   type: 'currency' },
    prepayment_status:  { label: 'Prepayment',         type: 'select',   options: ['', 'Not Requested', 'Requested', 'Paid', 'Failed', 'Refunded', 'Waived'] },
    assigned_dispatcher:{ label: 'Dispatcher',         type: 'link',     doctype: 'User' },
    estimate_manager:   { label: 'Estimate manager',   type: 'link',     doctype: 'User' },
    production_manager: { label: 'Production manager', type: 'link',     doctype: 'User' },
    technician:         { label: 'Technician',         type: 'link',     doctype: 'Employee' },
    mentor:             { label: 'Mentor',             type: 'link',     doctype: 'Employee' },
    diagnosis_result:   { label: 'Diagnosis result',   type: 'textarea' },
    estimate_amount:    { label: 'Estimate amount',    type: 'currency' },
    client_approval_status: { label: 'Approval',       type: 'select',   options: ['', 'Not Sent', 'Sent', 'Approved', 'Rejected', 'Need Follow-up'] },
    parts_needed:       { label: 'Parts needed?',      type: 'check' },
    parts_status:       { label: 'Parts status',       type: 'select',   options: ['', 'Not Needed', 'Need Identify', 'Ordered', 'Received', 'Installed'] },
    repair_result:      { label: 'Repair result',      type: 'textarea' },
    warranty_start_date:{ label: 'Warranty start',     type: 'date' },
    warranty_end_date:  { label: 'Warranty end',       type: 'date' },
    next_follow_up_datetime: { label: 'Next follow-up', type: 'datetime' },
    internal_comment:   { label: 'Internal comment',   type: 'textarea' },
  };

  // ---------------------------------------------------------------------------
  // 2. State + tiny helpers
  // ---------------------------------------------------------------------------
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
    timeline: null,        // cache of last loaded timeline
    statusPopoverFor: null,
    timelineRefreshTimer: null,
  };

  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function meta(name, dflt = '') {
    const el = document.querySelector(`meta[name="${name}"]`);
    return el ? el.content : dflt;
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function initials(name) {
    const cleaned = String(name || '').replace(/^DEMO\s*-\s*/i, '').trim();
    if (!cleaned) return '?';
    const parts = cleaned.split(/\s+/).slice(0, 2);
    return parts.map(p => p[0]).join('').toUpperCase();
  }

  function colorClass(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
    return 'c' + (Math.abs(h) % 8);
  }

  function formatRelativeTime(ts) {
    if (!ts) return '';
    const then = new Date(ts.replace(' ', 'T') + (ts.endsWith('Z') ? '' : 'Z'));
    if (isNaN(then)) return '';
    const diff = (Date.now() - then.getTime()) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + 'd ago';
    return then.toLocaleDateString();
  }

  function formatDateTime(ts) {
    if (!ts) return '';
    return ts.replace('T', ' ').slice(0, 16);
  }

  function formatCurrency(v) {
    if (v == null || v === '') return '';
    const n = Number(v);
    if (isNaN(n)) return v;
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  // ---------------------------------------------------------------------------
  // 3. Frappe API plumbing
  // ---------------------------------------------------------------------------
  function frappeReady() {
    return typeof window.frappe !== 'undefined' && typeof window.frappe.call === 'function';
  }

  function call(method, args = {}) {
    if (frappeReady()) {
      return new Promise((resolve, reject) => {
        frappe.call({
          method, args,
          callback: r => resolve(r && r.message),
          error: r => reject(r && r._server_messages ? r : new Error('Frappe call failed')),
        });
      });
    }
    // Fallback for /repair-jobs when frappe global isn't loaded — use raw fetch.
    const csrf = meta('csrf_token', '');
    return fetch('/api/method/' + method, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': csrf,
      },
      credentials: 'same-origin',
      body: JSON.stringify(args),
    }).then(async r => {
      if (!r.ok) {
        const t = await r.text();
        throw new Error(`API ${method} ${r.status}: ${t.slice(0, 240)}`);
      }
      const j = await r.json();
      return j.message;
    });
  }

  const api = {
    getJobs: (filters = {}) => call('baro_crm.api.repair_job.get_jobs', filters),
    stateCounts: () => call('baro_crm.api.repair_job.get_state_counts'),
    timeline: (repair_job) => call('baro_crm.api.repair_job.get_timeline', { repair_job }),
    addComment: (repair_job, content) => call('baro_crm.api.repair_job.add_comment', { repair_job, content }),
    setField: (repair_job, fieldname, value) => call('baro_crm.api.repair_job.set_field', { repair_job, fieldname, value }),
    changeStatus: (repair_job, action) => call('baro_crm.api.repair_job.change_status', { repair_job, action }),
    searchLink: (doctype, query) => call('baro_crm.api.repair_job.search_link', { doctype, query }),
  };

  // ---------------------------------------------------------------------------
  // 4. Render: full shell
  // ---------------------------------------------------------------------------
  function renderShell() {
    const userFullName = meta('cockpit_user_full_name', 'User');
    const userInitials = meta('cockpit_user_initials', 'U');
    const company = meta('cockpit_company', 'Baro Service');
    const userEmail = meta('cockpit_user', '');

    const root = $('#cockpit');
    root.classList.add('ready');
    root.innerHTML = `
      <aside class="sidebar" aria-label="Primary navigation">
        <div class="brand">
          <div class="brand-mark">BS</div>
          <div class="brand-text">
            <strong>Baro Service</strong>
            <small>Operations CRM</small>
          </div>
        </div>

        <button class="workspace-switcher" type="button" aria-label="Workspace">
          <div class="avatar c0" aria-hidden="true" style="width:24px;height:24px;font-size:10px;">BL</div>
          <div class="ws-name">${escapeHtml(company)}</div>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
        </button>

        <nav class="nav-section">
          <div class="nav-label">Workspace</div>
          <button class="nav-item active" type="button">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4l-6 6 2 2 6-6a4 4 0 0 0 5.4-5.4l-2.3 2.3-2-2 2.3-2.3z"/><path d="m17 14 4 4-3 3-4-4"/></svg>
            <span>Repair Jobs</span>
            <span class="count" id="totalCount">0</span>
          </button>
          <a class="nav-item" href="/app/repair-job" target="_blank" rel="noopener" title="Open the ERPNext list view">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span>ERPNext list</span>
          </a>
          <a class="nav-item" href="/app/workflow/Repair Job Workflow" target="_blank" rel="noopener">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
            <span>Workflow</span>
          </a>
        </nav>

        <div class="sidebar-footer">
          <div class="avatar c2" aria-hidden="true">${escapeHtml(userInitials)}</div>
          <div class="user-info">
            <strong>${escapeHtml(userFullName)}</strong>
            <small>${escapeHtml(userEmail)}</small>
          </div>
        </div>
      </aside>

      <main class="main" id="mainContent">
        <header class="topbar">
          <nav class="breadcrumb" aria-label="Breadcrumb">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
            <span>Workspace</span>
            <span class="sep" aria-hidden="true">/</span>
            <strong aria-current="page">Repair Jobs</strong>
          </nav>

          <div class="search-shell" role="search">
            <label for="search" class="sr-only">Search repair jobs</label>
            <svg class="s-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="search" type="search" placeholder="Search customer, phone, area, equipment, RJ ID…" autocomplete="off">
            <span class="kbd-hint" aria-hidden="true">Ctrl K</span>
          </div>

          <div class="topbar-actions">
            <button class="btn btn-ghost btn-icon" id="btnRefresh" title="Refresh" aria-label="Refresh">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            </button>
            <a class="btn btn-primary" href="/app/repair-job/new?status=New" target="_blank" rel="noopener">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              New Repair Job
            </a>
          </div>
        </header>

        <nav class="state-tabs" id="stateTabs" role="tablist" aria-label="Filter by service state"></nav>

        <div class="work-toolbar">
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
          <div class="filter-row">
            <button class="filter-chip" type="button" title="More filters coming">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Status
            </button>
            <button class="filter-chip" type="button"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Technician</button>
            <button class="filter-chip" type="button"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Marketing source</button>
            <button class="filter-chip" type="button"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Date range</button>
          </div>
        </div>

        <div class="work-table-wrap" id="listView">
          <div class="table-head">
            <span class="th-title">Repair Jobs</span>
            <span class="th-count" id="rowCount">0 results</span>
            <div class="right">
              <button class="btn btn-ghost" type="button" style="font-size:12.5px;padding:5px 10px;">Sort: Updated ↓</button>
            </div>
          </div>
          <div class="table-scroll">
            <table class="table">
              <thead>
                <tr>
                  <th scope="col">Customer</th>
                  <th scope="col">Status</th>
                  <th scope="col">Phone</th>
                  <th scope="col">Area</th>
                  <th scope="col">State</th>
                  <th scope="col">Source</th>
                  <th scope="col">Equipment</th>
                  <th scope="col">Technician</th>
                  <th scope="col">Updated</th>
                </tr>
              </thead>
              <tbody id="tableBody"></tbody>
            </table>
          </div>
        </div>

        <div class="kanban-wrap" id="kanbanView" style="display:none;" aria-hidden="true">
          <div class="kanban" id="kanban"></div>
        </div>
      </main>

      <div class="inspector-overlay" id="inspOverlay" aria-hidden="true"></div>
      <aside class="inspector" id="inspector" role="dialog" aria-modal="true" aria-labelledby="inspTitle" aria-hidden="true" tabindex="-1">
        <div class="insp-head">
          <div class="avatar c0" id="inspAvatar" aria-hidden="true" style="width:44px;height:44px;font-size:14px;">--</div>
          <div class="col-main">
            <div class="insp-id" id="inspId">RJ-…</div>
            <h2 id="inspTitle">Customer name</h2>
            <div class="insp-meta">
              <span id="inspPhone">—</span>
              <span class="sep">•</span>
              <span id="inspArea">—</span>
              <span class="sep">•</span>
              <span id="inspState">—</span>
            </div>
          </div>
          <button class="insp-close" id="inspClose" aria-label="Close inspector" title="Close (Esc)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div class="insp-status-bar">
          <span class="label">Status</span>
          <button class="status-pill" id="inspStatusPill" type="button" aria-haspopup="listbox">
            <span class="dot" aria-hidden="true"></span>
            <span class="status-text">—</span>
            <svg class="caret" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <span class="label" style="margin-left:auto;">Next action</span>
          <button class="btn btn-outline" id="btnAdvance" type="button" style="font-size:12.5px;padding:5px 10px;">
            <span id="advanceText">—</span>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
        </div>

        <nav class="insp-tabs" id="inspTabs" role="tablist" aria-label="Repair Job sections">
          <button class="insp-tab active" data-tab="overview" role="tab" aria-selected="true">Overview</button>
          <button class="insp-tab" data-tab="call" role="tab" aria-selected="false">Call</button>
          <button class="insp-tab" data-tab="service" role="tab" aria-selected="false">Service</button>
          <button class="insp-tab" data-tab="timeline" role="tab" aria-selected="false">Timeline <span class="badge" id="timelineBadge">0</span></button>
        </nav>

        <div class="insp-body" id="inspBody" role="tabpanel"></div>
      </aside>

      <div class="popover" id="statusPopover" role="listbox" aria-label="Change status">
        <label for="popSearch" class="sr-only">Search status</label>
        <input type="text" class="pop-search" placeholder="Search status…" id="popSearch">
        <div id="popList"></div>
      </div>

      <div class="toast" id="toast" role="status" aria-live="polite" aria-atomic="true"></div>
    `;

    renderStateTabs();
  }

  // ---------------------------------------------------------------------------
  // 5. State tabs
  // ---------------------------------------------------------------------------
  function renderStateTabs() {
    const root = $('#stateTabs');
    if (!root) return;
    root.innerHTML = STATE_TABS.map(t => {
      const cnt = state.stateCounts[t.key] ?? 0;
      const active = state.activeState === t.key ? 'active' : '';
      return `<button class="state-tab ${t.cls} ${active}" type="button" role="tab" aria-selected="${!!active}" data-state="${escapeHtml(t.key)}">
        ${escapeHtml(t.label)} <span class="count">${cnt}</span>
      </button>`;
    }).join('');
  }

  // ---------------------------------------------------------------------------
  // 6. Table
  // ---------------------------------------------------------------------------
  function renderTable() {
    const tbody = $('#tableBody');
    if (!tbody) return;
    $('#rowCount').textContent = `${state.jobs.length} result${state.jobs.length === 1 ? '' : 's'}`;
    $('#totalCount').textContent = state.stateCounts.All ?? state.jobs.length;

    if (!state.jobs.length) {
      tbody.innerHTML = `<tr><td colspan="9"><div class="empty-table"><strong>No Repair Jobs in this view</strong>${state.activeState !== 'All' ? `<div>Try a different state tab or "All".</div>` : '<div>When calls arrive from Zadarma, they will appear here.</div>'}</div></td></tr>`;
      return;
    }

    tbody.innerHTML = state.jobs.map(j => {
      const s = STATUS_MAP[j.status] || { color: 'slate' };
      const techHtml = j.technician
        ? `<div class="tech-cell"><div class="avatar ${colorClass(j.technician)}" aria-hidden="true">${escapeHtml(initials(j.technician))}</div><span>${escapeHtml(j.technician)}</span></div>`
        : `<div class="tech-cell empty">Unassigned</div>`;
      const customer = j.customer || '(no customer)';
      const urgencyCls = (j.urgency || 'Unknown').replace(/\s+/g, '-');
      return `
        <tr data-id="${escapeHtml(j.name)}" class="${state.selectedId === j.name ? 'selected' : ''}" tabindex="0" role="button" aria-label="Open ${escapeHtml(customer)} — ${escapeHtml(j.status || 'New')}">
          <td>
            <div class="customer-cell">
              <div class="avatar ${colorClass(customer)}" aria-hidden="true">${escapeHtml(initials(customer))}</div>
              <div class="col">
                <strong>${escapeHtml(customer)}</strong>
                <small class="id-cell">${escapeHtml(j.name)}</small>
              </div>
            </div>
          </td>
          <td>
            <button class="status-pill s-${s.color}" type="button" data-status-btn data-stop aria-label="Status ${escapeHtml(j.status || '')}, click to change" aria-haspopup="listbox">
              <span class="dot" aria-hidden="true"></span>
              <span>${escapeHtml(j.status || 'New')}</span>
              <svg class="caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </td>
          <td><span style="font-family:'JetBrains Mono',monospace;font-size:12.5px;">${escapeHtml(j.caller_phone || '')}</span></td>
          <td>${escapeHtml(j.area || '')}</td>
          <td>${j.service_state ? `<span class="source-tag"><span class="dot" aria-hidden="true"></span>${escapeHtml(j.service_state)}</span>` : '<span style="color:var(--text-faint);font-style:italic;">—</span>'}</td>
          <td>${j.marketing_source ? `<span class="source-tag"><span class="dot" aria-hidden="true"></span>${escapeHtml(j.marketing_source)}</span>` : ''}</td>
          <td><div class="equipment-cell"><span class="urg ${escapeHtml(urgencyCls)}" aria-hidden="true"></span><span class="sr-only">Urgency ${escapeHtml(j.urgency || 'unknown')}.</span>${escapeHtml(j.equipment_type || '')}</div></td>
          <td>${techHtml}</td>
          <td><div class="time-cell">${escapeHtml(formatDateTime(j.modified))}<small>${escapeHtml(formatRelativeTime(j.modified))}</small></div></td>
        </tr>
      `;
    }).join('');
  }

  // ---------------------------------------------------------------------------
  // 6b. Kanban view
  // ---------------------------------------------------------------------------
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

  // ---------------------------------------------------------------------------
  // 7. Data loading
  // ---------------------------------------------------------------------------
  async function loadAll({ refreshCounts = true } = {}) {
    try {
      const args = { state: state.activeState, search: state.search };
      const [jobs, counts] = await Promise.all([
        api.getJobs(args),
        refreshCounts ? api.stateCounts() : Promise.resolve(state.stateCounts),
      ]);
      state.jobs = jobs || [];
      if (counts) state.stateCounts = counts;
      renderStateTabs();
      renderTable();
    } catch (e) {
      console.error('loadAll failed', e);
      toast('Failed to load Repair Jobs. ' + (e.message || ''), 'err');
    }
  }

  // ---------------------------------------------------------------------------
  // 8. Inspector — open + render tab content
  // ---------------------------------------------------------------------------
  let lastFocusedBeforeInspector = null;

  async function openInspector(id) {
    const j = state.jobs.find(x => x.name === id);
    if (!j) return;
    if (!state.selectedId) lastFocusedBeforeInspector = document.activeElement;
    state.selectedId = id;

    // Refresh row highlight
    renderTable();

    // Header
    $('#inspId').textContent = j.name;
    $('#inspTitle').textContent = j.customer || '(no customer)';
    $('#inspPhone').textContent = j.caller_phone || '—';
    $('#inspArea').textContent = j.area || '—';
    $('#inspState').textContent = j.service_state || '—';
    const av = $('#inspAvatar');
    av.textContent = initials(j.customer || '');
    av.className = `avatar ${colorClass(j.customer || '')}`;
    av.style.cssText = 'width:44px;height:44px;font-size:14px;';

    updateStatusPill(j.status);
    updateAdvanceButton(j);
    renderInspBody(j);

    const insp = $('#inspector');
    insp.classList.add('open');
    insp.setAttribute('aria-hidden', 'false');
    $('#inspOverlay').classList.add('open');
    $('#inspOverlay').setAttribute('aria-hidden', 'false');
    setTimeout(() => $('#inspClose').focus(), 30);
  }

  function closeInspector() {
    state.selectedId = null;
    state.timeline = null;
    $('#inspector').classList.remove('open');
    $('#inspector').setAttribute('aria-hidden', 'true');
    $('#inspOverlay').classList.remove('open');
    $('#inspOverlay').setAttribute('aria-hidden', 'true');
    renderTable();
    if (lastFocusedBeforeInspector && document.body.contains(lastFocusedBeforeInspector)) {
      lastFocusedBeforeInspector.focus();
    }
    lastFocusedBeforeInspector = null;
  }

  function updateStatusPill(status) {
    const s = STATUS_MAP[status] || { color: 'slate' };
    const pill = $('#inspStatusPill');
    pill.className = `status-pill s-${s.color}`;
    pill.querySelector('.status-text').textContent = status || '—';
  }

  function updateAdvanceButton(j) {
    const trans = TRANSITIONS_FROM[j.status] || [];
    const next = trans.find(t => !['Lost','Spam','Unrelated','Closed'].includes(t.to)) || trans[0];
    const btn = $('#btnAdvance');
    if (next) {
      $('#advanceText').textContent = next.action;
      btn.dataset.action = next.action;
      btn.dataset.id = j.name;
      btn.disabled = !state.canWrite;
    } else {
      $('#advanceText').textContent = 'No next action';
      btn.dataset.action = '';
      btn.disabled = true;
    }
  }

  function renderInspBody(j) {
    const body = $('#inspBody');
    const tab = state.activeTab;
    if (tab === 'overview') {
      body.innerHTML = renderOverview(j);
    } else if (tab === 'call') {
      body.innerHTML = renderCallTab(j);
    } else if (tab === 'service') {
      body.innerHTML = renderServiceTab(j);
    } else if (tab === 'timeline') {
      body.innerHTML = renderTimelineSkeleton();
      loadTimeline(j.name).then(items => {
        if (state.selectedId !== j.name || state.activeTab !== 'timeline') return;
        body.innerHTML = renderTimeline(j, items);
      });
    }
  }

  function fieldHtml(jobName, fieldname, value, opts = {}) {
    const m = FIELD_META[fieldname] || { label: fieldname, type: 'data' };
    const readonly = opts.readonly || !state.canWrite;
    const display = formatDisplay(value, m);
    const empty = (value == null || value === '' || value === 0 && m.type === 'currency');
    return `
      <div class="field">
        <span class="k">${escapeHtml(opts.labelOverride || m.label)}</span>
        <div class="v ${empty ? 'empty' : ''} ${readonly ? 'readonly' : ''}"
             data-fieldname="${escapeHtml(fieldname)}"
             data-job="${escapeHtml(jobName)}"
             data-type="${m.type}"
             ${m.doctype ? `data-doctype="${escapeHtml(m.doctype)}"` : ''}
             ${m.options ? `data-options='${JSON.stringify(m.options).replace(/'/g, "&apos;")}'` : ''}
             tabindex="${readonly ? '-1' : '0'}"
             role="${readonly ? 'text' : 'button'}"
             aria-label="${escapeHtml(m.label)}: ${escapeHtml(String(value ?? ''))}"
             title="${readonly ? '' : 'Click to edit'}">${display || 'Click to add'}</div>
      </div>
    `;
  }

  function formatDisplay(value, meta) {
    if (value == null || value === '') return '';
    if (meta.type === 'currency') return formatCurrency(value);
    if (meta.type === 'check') return value ? '✓ Yes' : '— No';
    if (meta.type === 'textarea') return escapeHtml(value).replaceAll('\n', '<br>');
    return escapeHtml(value);
  }

  function renderOverview(j) {
    return `
      ${j.ai_call_summary ? `<div class="ai-summary">${escapeHtml(j.ai_call_summary)}</div>` : ''}
      <div class="field-group">
        <h4>Customer</h4>
        ${fieldHtml(j.name, 'customer', j.customer)}
        ${fieldHtml(j.name, 'caller_phone', j.caller_phone)}
        ${fieldHtml(j.name, 'service_address', j.service_address)}
        ${fieldHtml(j.name, 'area', j.area)}
        ${fieldHtml(j.name, 'service_state', j.service_state)}
        ${fieldHtml(j.name, 'marketing_source', j.marketing_source)}
      </div>
      <div class="field-group">
        <h4>Equipment</h4>
        ${fieldHtml(j.name, 'equipment_type', j.equipment_type)}
        ${fieldHtml(j.name, 'equipment_brand', j.equipment_brand)}
        ${fieldHtml(j.name, 'equipment_model', j.equipment_model)}
        ${fieldHtml(j.name, 'symptom', j.symptom)}
        ${fieldHtml(j.name, 'urgency', j.urgency)}
      </div>
      <div class="field-group">
        <h4>Assignment</h4>
        ${fieldHtml(j.name, 'assigned_dispatcher', j.assigned_dispatcher)}
        ${fieldHtml(j.name, 'production_manager', j.production_manager)}
        ${fieldHtml(j.name, 'technician', j.technician)}
        ${fieldHtml(j.name, 'estimate_manager', j.estimate_manager)}
      </div>
    `;
  }

  function renderCallTab(j) {
    return `
      ${j.ai_call_summary ? `<div class="ai-summary">${escapeHtml(j.ai_call_summary)}</div>` : ''}
      <div class="field-group">
        <h4>Zadarma call</h4>
        <div class="field"><span class="k">Datetime</span><div class="v readonly">${escapeHtml(formatDateTime(j.call_datetime))}</div></div>
        <div class="field"><span class="k">Duration</span><div class="v readonly">${j.call_duration_seconds ? Math.floor(j.call_duration_seconds/60) + 'm ' + (j.call_duration_seconds % 60) + 's' : '—'}</div></div>
        <div class="field"><span class="k">Phone</span><div class="v readonly">${escapeHtml(j.caller_phone || '')}</div></div>
        <div class="field"><span class="k">Business DID</span><div class="v readonly">${escapeHtml(j.business_phone_did || '')}</div></div>
      </div>
      <div class="field-group">
        <h4>Money</h4>
        ${fieldHtml(j.name, 'diagnostic_price', j.diagnostic_price)}
        ${fieldHtml(j.name, 'prepayment_status', j.prepayment_status)}
        ${fieldHtml(j.name, 'estimate_amount', j.estimate_amount)}
        ${fieldHtml(j.name, 'client_approval_status', j.client_approval_status)}
      </div>
    `;
  }

  function renderServiceTab(j) {
    return `
      <div class="field-group">
        <h4>Diagnosis</h4>
        ${fieldHtml(j.name, 'diagnosis_result', j.diagnosis_result)}
      </div>
      <div class="field-group">
        <h4>Parts</h4>
        ${fieldHtml(j.name, 'parts_needed', j.parts_needed)}
        ${fieldHtml(j.name, 'parts_status', j.parts_status)}
      </div>
      <div class="field-group">
        <h4>Repair</h4>
        ${fieldHtml(j.name, 'repair_result', j.repair_result)}
      </div>
      <div class="field-group">
        <h4>Warranty &amp; follow-up</h4>
        ${fieldHtml(j.name, 'warranty_start_date', j.warranty_start_date)}
        ${fieldHtml(j.name, 'warranty_end_date', j.warranty_end_date)}
        ${fieldHtml(j.name, 'next_follow_up_datetime', j.next_follow_up_datetime)}
      </div>
      <div class="field-group">
        <h4>Internal notes</h4>
        ${fieldHtml(j.name, 'internal_comment', j.internal_comment)}
      </div>
    `;
  }

  function renderTimelineSkeleton() {
    return `
      ${state.canWrite ? `
      <div class="comment-composer">
        <label for="commentBox" class="sr-only">Add a comment</label>
        <textarea id="commentBox" placeholder="Add a comment — visible in timeline, attributed to you…"></textarea>
        <div class="row">
          <span class="hint">Ctrl+Enter to submit</span>
          <button class="btn btn-primary" id="btnAddComment" type="button">Add comment</button>
        </div>
      </div>` : ''}
      <div class="field-group"><h4>Activity</h4>
        <div style="padding:24px;text-align:center;color:var(--text-muted);">Loading timeline…</div>
      </div>
    `;
  }

  function renderTimeline(j, items) {
    const composer = state.canWrite ? `
      <div class="comment-composer">
        <label for="commentBox" class="sr-only">Add a comment</label>
        <textarea id="commentBox" placeholder="Add a comment — visible in timeline, attributed to you…"></textarea>
        <div class="row">
          <span class="hint">Ctrl+Enter to submit</span>
          <button class="btn btn-primary" id="btnAddComment" type="button">Add comment</button>
        </div>
      </div>
    ` : '';

    const list = (items || []).map(it => renderTimelineItem(it)).join('');
    $('#timelineBadge').textContent = (items || []).length;
    return `
      ${composer}
      <div class="field-group">
        <h4>Activity</h4>
        ${list ? `<div class="timeline">${list}</div>` : '<div style="padding:18px;text-align:center;color:var(--text-muted);">No activity yet — be the first to add a comment.</div>'}
      </div>
    `;
  }

  function renderTimelineItem(it) {
    const when = `${escapeHtml(formatDateTime(it.creation))} · ${escapeHtml(formatRelativeTime(it.creation))} · ${escapeHtml(it.owner || '')}`;
    if (it.kind === 'comment') {
      return `
        <div class="timeline-item k-comment">
          <div class="ti-title">${escapeHtml(it.owner || 'user')} commented</div>
          <div class="ti-meta">${when}</div>
          <div class="ti-note">${escapeHtml(it.content || '').replaceAll('\n', '<br>')}</div>
        </div>
      `;
    }
    if (it.kind === 'change') {
      const changes = (it.changes || []).slice(0, 6).map(c => {
        const field = c[0];
        const oldVal = c[1] == null || c[1] === '' ? '(empty)' : c[1];
        const newVal = c[2] == null || c[2] === '' ? '(empty)' : c[2];
        return `<div><b>${escapeHtml(prettyField(field))}</b>: <span class="old">${escapeHtml(String(oldVal))}</span> → <span class="new">${escapeHtml(String(newVal))}</span></div>`;
      }).join('');
      return `
        <div class="timeline-item k-change">
          <div class="ti-title">${escapeHtml(it.owner || 'system')} updated fields</div>
          <div class="ti-meta">${when}</div>
          <div class="ti-change">${changes || '<i>structural change</i>'}</div>
        </div>
      `;
    }
    return `
      <div class="timeline-item k-info">
        <div class="ti-title">${escapeHtml(it.comment_type || 'event')}</div>
        <div class="ti-meta">${when}</div>
        <div class="ti-note">${escapeHtml(it.content || '')}</div>
      </div>
    `;
  }

  function prettyField(fieldname) {
    if (!fieldname) return '';
    return fieldname.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  async function loadTimeline(jobName) {
    try {
      const items = await api.timeline(jobName);
      state.timeline = items;
      return items;
    } catch (e) {
      console.error('timeline load failed', e);
      toast('Could not load timeline. ' + (e.message || ''), 'err');
      return [];
    }
  }

  // ---------------------------------------------------------------------------
  // 9. Inline edit
  // ---------------------------------------------------------------------------
  function beginEdit(vEl) {
    if (vEl.classList.contains('editing') || vEl.classList.contains('readonly')) return;
    const fieldname = vEl.dataset.fieldname;
    const job = vEl.dataset.job;
    const m = FIELD_META[fieldname];
    if (!m) return;

    const current = readJobField(job, fieldname);
    vEl.classList.add('editing');
    vEl.dataset.previous = current == null ? '' : current;

    let inputHtml = '';
    if (m.type === 'textarea') {
      inputHtml = `<textarea class="field-input" autofocus>${escapeHtml(current || '')}</textarea>`;
    } else if (m.type === 'select') {
      const opts = (m.options || []).map(o => `<option value="${escapeHtml(o)}" ${o === current ? 'selected' : ''}>${escapeHtml(o || '— none —')}</option>`).join('');
      inputHtml = `<select class="field-input" autofocus>${opts}</select>`;
    } else if (m.type === 'check') {
      inputHtml = `<select class="field-input" autofocus>
        <option value="0" ${!current ? 'selected' : ''}>No</option>
        <option value="1" ${current ? 'selected' : ''}>Yes</option>
      </select>`;
    } else if (m.type === 'date') {
      inputHtml = `<input class="field-input" type="date" value="${escapeHtml((current || '').slice(0, 10))}" autofocus>`;
    } else if (m.type === 'datetime') {
      inputHtml = `<input class="field-input" type="datetime-local" value="${escapeHtml((current || '').replace(' ', 'T').slice(0, 16))}" autofocus>`;
    } else if (m.type === 'currency') {
      inputHtml = `<input class="field-input" type="number" step="0.01" value="${escapeHtml(current ?? '')}" autofocus>`;
    } else if (m.type === 'link') {
      // For MVP: free text. Future: typeahead via search_link API.
      inputHtml = `<input class="field-input" type="text" value="${escapeHtml(current || '')}" placeholder="${escapeHtml(m.doctype || 'Search…')}" list="link-${fieldname}-list" autofocus>`;
    } else {
      inputHtml = `<input class="field-input" type="text" value="${escapeHtml(current || '')}" autofocus>`;
    }

    vEl.innerHTML = inputHtml;
    const inp = vEl.querySelector('.field-input');
    inp.focus();
    if (inp.select) try { inp.select(); } catch {}

    let committed = false;
    const commit = async () => {
      if (committed) return;
      committed = true;
      let raw = inp.value;
      if (m.type === 'check') raw = inp.value === '1' ? 1 : 0;
      else if (m.type === 'currency') raw = raw === '' ? null : parseFloat(raw);
      else if (m.type === 'datetime') raw = raw ? raw.replace('T', ' ') + ':00' : null;

      const previous = vEl.dataset.previous;
      // Compare as strings to detect no-op
      if (String(raw ?? '') === String(previous ?? '')) {
        finishEdit(vEl, fieldname, current);
        return;
      }

      vEl.classList.add('saving');
      try {
        const r = await api.setField(job, fieldname, raw);
        writeJobField(job, fieldname, r.value);
        vEl.classList.remove('saving');
        vEl.classList.add('saved');
        setTimeout(() => vEl.classList.remove('saved'), 1200);
        finishEdit(vEl, fieldname, r.value);
        // Refresh the row + timeline cache invalidates
        renderTable();
        if (state.activeTab === 'timeline') {
          const items = await loadTimeline(job);
          const jobObj = state.jobs.find(x => x.name === job);
          if (jobObj && state.selectedId === job) $('#inspBody').innerHTML = renderTimeline(jobObj, items);
        }
        toast(`Saved · ${m.label}`, 'ok');
      } catch (e) {
        console.error('setField failed', e);
        vEl.classList.remove('saving');
        vEl.classList.add('error');
        toast('Save failed: ' + extractError(e), 'err');
        setTimeout(() => {
          vEl.classList.remove('error');
          finishEdit(vEl, fieldname, current);
        }, 1500);
      }
    };

    const cancel = () => {
      if (committed) return;
      committed = true;
      finishEdit(vEl, fieldname, current);
    };

    inp.addEventListener('blur', commit, { once: true });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); inp.removeEventListener('blur', commit); cancel(); }
      if (e.key === 'Enter' && m.type !== 'textarea') { e.preventDefault(); inp.blur(); }
      if (e.key === 'Enter' && e.ctrlKey && m.type === 'textarea') { e.preventDefault(); inp.blur(); }
    });
  }

  function finishEdit(vEl, fieldname, value) {
    const m = FIELD_META[fieldname];
    vEl.classList.remove('editing');
    const empty = value == null || value === '' || (m.type === 'currency' && Number(value) === 0);
    vEl.innerHTML = formatDisplay(value, m) || 'Click to add';
    vEl.classList.toggle('empty', empty);
  }

  function readJobField(jobName, fieldname) {
    const j = state.jobs.find(x => x.name === jobName);
    return j ? j[fieldname] : null;
  }

  function writeJobField(jobName, fieldname, value) {
    const j = state.jobs.find(x => x.name === jobName);
    if (j) j[fieldname] = value;
  }

  function extractError(e) {
    if (!e) return 'unknown error';
    if (e.message) return e.message;
    if (e._server_messages) {
      try {
        const msgs = JSON.parse(e._server_messages);
        return JSON.parse(msgs[0]).message || msgs[0];
      } catch { return e._server_messages; }
    }
    return String(e);
  }

  // ---------------------------------------------------------------------------
  // 10. Status popover + change
  // ---------------------------------------------------------------------------
  function openStatusPopover(targetEl, jobId) {
    if (!state.canWrite) {
      toast('You do not have permission to change status.', 'err');
      return;
    }
    const pop = $('#statusPopover');
    state.statusPopoverFor = jobId;
    const job = state.jobs.find(x => x.name === jobId);
    if (!job) return;

    const r = targetEl.getBoundingClientRect();
    pop.style.top = `${r.bottom + 6}px`;
    pop.style.left = `${Math.min(r.left, window.innerWidth - 280)}px`;

    const validTransitions = TRANSITIONS_FROM[job.status] || [];
    const validActions = new Set(validTransitions.map(t => t.action));
    const validTargets = new Set(validTransitions.map(t => t.to));

    const groups = {
      'Available now (workflow)': validTransitions.map(t => ({ status: t.to, action: t.action })),
    };

    const html = Object.entries(groups).map(([label, items]) => {
      if (!items.length) return '';
      return `<div class="pop-label">${escapeHtml(label)}</div>` + items.map(it => {
        const s = STATUS_MAP[it.status] || { color: 'slate' };
        return `<button class="pop-item" type="button" data-action="${escapeHtml(it.action)}" data-target="${escapeHtml(it.status)}">
          <span class="pop-dot" style="background:var(--c-${s.color});"></span>
          <span>${escapeHtml(it.status)}</span>
          <span style="margin-left:auto;font-size:11px;color:var(--text-faint);">${escapeHtml(it.action)}</span>
        </button>`;
      }).join('');
    }).join('');

    $('#popList').innerHTML = html || `<div class="pop-label">No workflow transitions available from "${escapeHtml(job.status)}"</div>`;
    pop.classList.add('open');
    $('#popSearch').value = '';
    setTimeout(() => $('#popSearch').focus(), 30);
  }

  function closeStatusPopover() {
    $('#statusPopover').classList.remove('open');
    state.statusPopoverFor = null;
  }

  async function applyAction(jobId, action) {
    closeStatusPopover();
    try {
      const r = await api.changeStatus(jobId, action);
      writeJobField(jobId, 'status', r.status);
      renderTable();
      if (state.selectedId === jobId) {
        const j = state.jobs.find(x => x.name === jobId);
        if (j) {
          updateStatusPill(j.status);
          updateAdvanceButton(j);
          if (state.activeTab === 'timeline') {
            const items = await loadTimeline(jobId);
            $('#inspBody').innerHTML = renderTimeline(j, items);
          }
        }
      }
      // Refresh state counts since a state-ish change may have happened
      api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); });
      toast(`Status: ${r.status}`, 'ok');
    } catch (e) {
      console.error('changeStatus failed', e);
      toast('Status change failed: ' + extractError(e), 'err');
    }
  }

  // ---------------------------------------------------------------------------
  // 11. Comments
  // ---------------------------------------------------------------------------
  async function submitComment() {
    const box = $('#commentBox');
    if (!box || !state.selectedId) return;
    const text = box.value.trim();
    if (!text) {
      toast('Comment is empty', 'err');
      return;
    }
    const btn = $('#btnAddComment');
    btn.disabled = true;
    try {
      await api.addComment(state.selectedId, text);
      box.value = '';
      const items = await loadTimeline(state.selectedId);
      const j = state.jobs.find(x => x.name === state.selectedId);
      if (j) $('#inspBody').innerHTML = renderTimeline(j, items);
      toast('Comment added', 'ok');
    } catch (e) {
      toast('Comment failed: ' + extractError(e), 'err');
    } finally {
      const newBtn = $('#btnAddComment');
      if (newBtn) newBtn.disabled = false;
    }
  }

  // ---------------------------------------------------------------------------
  // 12. Toast
  // ---------------------------------------------------------------------------
  let toastTimer = null;
  function toast(msg, kind = 'ok') {
    const t = $('#toast');
    if (!t) return;
    t.className = 'toast ' + (kind === 'err' ? 'err' : 'ok');
    t.innerHTML = `<span class="toast-icon">${kind === 'err' ? '!' : '✓'}</span> <span>${escapeHtml(msg)}</span>`;
    t.classList.add('open');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('open'), kind === 'err' ? 4200 : 2400);
  }

  // ---------------------------------------------------------------------------
  // 13. Realtime — listen for other users' Repair Job edits
  // ---------------------------------------------------------------------------
  function setupRealtime() {
    if (!window.frappe || !frappe.realtime || !frappe.realtime.on) return;
    frappe.realtime.on('doc_update', (data) => {
      if (!data || data.doctype !== 'Repair Job') return;
      // Debounced reload
      clearTimeout(state.timelineRefreshTimer);
      state.timelineRefreshTimer = setTimeout(() => {
        loadAll({ refreshCounts: false });
        if (state.selectedId === data.name && state.activeTab === 'timeline') {
          loadTimeline(data.name).then(items => {
            const j = state.jobs.find(x => x.name === data.name);
            if (j) $('#inspBody').innerHTML = renderTimeline(j, items);
          });
        }
      }, 600);
    });
  }

  // ---------------------------------------------------------------------------
  // 14. Event wiring
  // ---------------------------------------------------------------------------
  function bindEvents() {
    document.addEventListener('click', (e) => {
      const stateTab = e.target.closest('.state-tab');
      if (stateTab) {
        state.activeState = stateTab.dataset.state;
        renderStateTabs();
        loadAll({ refreshCounts: false });
        return;
      }

      const statusBtn = e.target.closest('[data-status-btn]');
      const row = e.target.closest('tr[data-id]');
      if (statusBtn && row) {
        e.stopPropagation();
        openStatusPopover(statusBtn, row.dataset.id);
        return;
      }

      const inspPill = e.target.closest('#inspStatusPill');
      if (inspPill && state.selectedId) {
        openStatusPopover(inspPill, state.selectedId);
        return;
      }

      const popItem = e.target.closest('.pop-item');
      if (popItem) {
        applyAction(state.statusPopoverFor, popItem.dataset.action);
        return;
      }

      if (!e.target.closest('#statusPopover') && !statusBtn && !inspPill) {
        closeStatusPopover();
      }

      if (row && !e.target.closest('[data-stop]')) {
        openInspector(row.dataset.id);
        return;
      }

      const fieldV = e.target.closest('.v[data-fieldname]');
      if (fieldV && !fieldV.classList.contains('editing')) {
        beginEdit(fieldV);
        return;
      }

      if (e.target.closest('#btnAddComment')) {
        submitComment();
        return;
      }

      if (e.target.closest('#btnRefresh')) {
        loadAll();
        return;
      }

      if (e.target.closest('#inspClose')) {
        closeInspector();
        return;
      }

      if (e.target.closest('#inspOverlay') && !e.target.closest('.inspector')) {
        closeInspector();
        return;
      }

      const advanceBtn = e.target.closest('#btnAdvance');
      if (advanceBtn && advanceBtn.dataset.action) {
        applyAction(advanceBtn.dataset.id, advanceBtn.dataset.action);
        return;
      }
    });

    // Tabs (delegated)
    document.addEventListener('click', (e) => {
      const t = e.target.closest('#inspTabs .insp-tab');
      if (!t) return;
      $$('#inspTabs .insp-tab').forEach(x => {
        x.classList.remove('active');
        x.setAttribute('aria-selected', 'false');
      });
      t.classList.add('active');
      t.setAttribute('aria-selected', 'true');
      state.activeTab = t.dataset.tab;
      if (state.selectedId) {
        const j = state.jobs.find(x => x.name === state.selectedId);
        if (j) renderInspBody(j);
      }
    });

    // Search
    const searchInp = $('#search');
    let searchTimer = null;
    searchInp.addEventListener('input', (e) => {
      state.search = e.target.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadAll({ refreshCounts: false }), 280);
    });

    // Status popover search
    $('#popSearch').addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      $$('#popList .pop-item').forEach(i => {
        i.style.display = i.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });

    // Keyboard
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchInp.focus();
        searchInp.select();
      }
      if (e.key === 'Escape') {
        closeStatusPopover();
        if ($('#inspector').classList.contains('open')) closeInspector();
      }
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-id]')) {
        e.preventDefault();
        openInspector(e.target.dataset.id);
      }
      if (e.key === 'Enter' && e.ctrlKey && e.target.id === 'commentBox') {
        e.preventDefault();
        submitComment();
      }
    });
  }

  // ---------------------------------------------------------------------------
  // 15. Boot
  // ---------------------------------------------------------------------------
  async function boot() {
    state.canWrite = meta('cockpit_can_write', '0') === '1';
    state.user = meta('cockpit_user', '');
    renderShell();
    bindEvents();
    setupRealtime();
    await loadAll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  // Expose a tiny debug handle
  window.baroCockpit = { state, api, reload: () => loadAll() };
})();
