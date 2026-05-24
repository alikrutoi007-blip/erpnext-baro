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
    activeView: 'list',                  // 'list' or 'kanban' (view mode)
    activeViewId: 'active',              // which named view from VIEWS is selected
    activeTab: 'overview',
    search: '',
    canWrite: false,
    user: '',
    timeline: null,        // cache of last loaded timeline
    statusPopoverFor: null,
    statusPopoverTrigger: null,
    timelineRefreshTimer: null,
    inspectorTrapUninstall: null,
    scope: 'active',          // 'active' (default) | 'all'
    city: '',                 // empty = no filter
    cities: [],               // populated from filterOptions()
    sortBy: 'modified_desc',  // see SORT_MODES backend whitelist
    dateType: '',             // '' | 'follow_up' | 'call' | 'created' | 'updated'
    datePreset: '',           // '' | 'today' | 'yesterday' | 'tomorrow' | 'this_week' | 'overdue' | 'no_date'
    dateFrom: '',             // explicit ISO date (YYYY-MM-DD) — from calendar popover
    dateTo: '',               // explicit ISO date (YYYY-MM-DD) — from calendar popover
    pageLimit: 500,
    jobsHasMore: false,
    jobsTotal: null,
    createOpen: false,
    createDraft: null,
    createDedupWarnings: null,
    createForceNew: false,
    createSubmitting: false,
    createTrapUninstall: null,
    customerLookupCache: new Map(),
  };

  // O(1) lookup helper — keep state.jobs and state.jobsById in sync via setJobs()
  state.jobsById = new Map();
  function setJobs(jobs) {
    state.jobs = jobs || [];
    state.jobsById = new Map(state.jobs.map(j => [j.name, j]));
  }
  function jobById(id) { return state.jobsById.get(id) || null; }

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

  // ---------------------------------------------------------------------------
  // Named views (G). Hardcoded for MVP — flip to a Cockpit View DocType later.
  // Each view is `{id, label, hint, icon, filters}`. `filters` is exactly the
  // payload merged into api.getJobs() args; absent keys preserve user session
  // state for that filter (e.g. user's currently-selected sort or city).
  // ---------------------------------------------------------------------------
  const VIEW_ICONS = {
    inbox:   '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>',
    user:    '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    bolt:    '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    sun:     '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>',
    clock:   '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    wrench:  '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4l-6 6 2 2 6-6a4 4 0 0 0 5.4-5.4l-2.3 2.3-2-2 2.3-2.3z"/></svg>',
    cash:    '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/></svg>',
    shield:  '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    archive: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>',
    ban:     '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>',
  };

  const VIEWS = [
    { id: 'my-queue',        label: 'My Queue',          icon: 'user',
      filters: { assignee: 'me', scope: 'active' } },
    { id: 'unassigned',      label: 'Unassigned',        icon: 'inbox',
      filters: { unassigned: 1, scope: 'active' } },
    { id: 'active',          label: 'Active',            icon: 'bolt',
      filters: { scope: 'active' } },
    { id: 'today',           label: 'Today',             icon: 'sun',
      filters: { scope: 'active', date_type: 'call', date_preset: 'today' } },
    { id: 'needs-followup',  label: 'Needs Follow-up',   icon: 'clock',
      filters: { needs_followup: 1 } },
    { id: 'production',      label: 'Production',        icon: 'wrench',
      filters: { statuses: ['Technician Assigned','Diagnostics In Progress','Diagnosis Completed','Parts Needed','Repair In Progress','Repair Completed'] } },
    { id: 'waiting-money',   label: 'Waiting Money',     icon: 'cash',
      filters: { statuses: ['Waiting Prepayment','Diagnostics Paid','Estimate Sent','Waiting Client Approval','Invoice Sent'] } },
    { id: 'warranty',        label: 'Warranty',          icon: 'shield',
      filters: { statuses: ['Warranty Active'] } },
    { id: 'archive',         label: 'Archive',           icon: 'archive',
      filters: { statuses: ['Closed','Paid'] } },
    { id: 'spam-unrelated',  label: 'Spam / Unrelated',  icon: 'ban',
      filters: { statuses: ['Spam','Unrelated','Lost'] } },
  ];

  function viewById(id) { return VIEWS.find(v => v.id === id) || VIEWS[2]; }

  const api = {
    bootContext: () => call('baro_crm.api.repair_job.get_boot_context'),
    getJobs: (filters = {}) => call('baro_crm.api.repair_job.get_jobs', filters),
    stateCounts: () => call('baro_crm.api.repair_job.get_state_counts'),
    filterOptions: () => call('baro_crm.api.repair_job.get_filter_options'),
    timeline: (repair_job) => call('baro_crm.api.repair_job.get_timeline', { repair_job }),
    addComment: (repair_job, content) => call('baro_crm.api.repair_job.add_comment', { repair_job, content }),
    setField: (repair_job, fieldname, value) => call('baro_crm.api.repair_job.set_field', { repair_job, fieldname, value }),
    changeStatus: (repair_job, action) => call('baro_crm.api.repair_job.change_status', { repair_job, action }),
    searchLink: (doctype, query) => call('baro_crm.api.repair_job.search_link', { doctype, query }),
  };

  // ---------------------------------------------------------------------------
  // Section 15b: Shared focus-trap helper (used by inspector and F drawer)
  // ---------------------------------------------------------------------------
  function installFocusTrap(rootEl, { initialFocus = null } = {}) {
    if (!rootEl) return () => {};

    function focusableNodes() {
      return Array.from(rootEl.querySelectorAll([
        'a[href]', 'button:not([disabled])', 'input:not([disabled])',
        'select:not([disabled])', 'textarea:not([disabled])',
        '[tabindex]:not([tabindex="-1"])',
      ].join(','))).filter(el => el.offsetParent !== null);
    }

    function onKey(e) {
      if (e.key !== 'Tab') return;
      const nodes = focusableNodes();
      if (nodes.length === 0) { e.preventDefault(); return; }
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKey);

    setTimeout(() => {
      const target = initialFocus || focusableNodes()[0] || rootEl;
      try { target.focus(); } catch (e) {}
    }, 30);

    return function uninstall() {
      document.removeEventListener('keydown', onKey);
    };
  }

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

  // Lazily-built destructive-confirm dialog. Appended INSIDE .baro-cockpit so
  // the namespaced CSS in cockpit.css applies.
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

  // ---------------------------------------------------------------------------
  // Section 16b: SortableJS init + drag event handlers
  // ---------------------------------------------------------------------------
  let sortableInstances = [];
  let activeSortableEvt = null;
  let escCancelled = false;

  function initDragDrop() {
    sortableInstances.forEach(s => { try { s.destroy(); } catch (e) {} });
    sortableInstances = [];

    if (!state.canWrite) return;          // Readers cannot drag cards

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
      if (state._kanbanRenderDeferred) { state._kanbanRenderDeferred = false; renderKanban(); }
      return;
    }
    handleDropResolution(evt);
    activeSortableEvt = null;
    if (state._kanbanRenderDeferred) { state._kanbanRenderDeferred = false; renderKanban(); }
  }

  function onEscDuringDrag(e) {
    if (e.key !== 'Escape' || !activeSortableEvt) return;
    e.preventDefault();
    e.stopPropagation();
    escCancelled = true;
    revertSortableMove(activeSortableEvt);
    cleanupDragVisuals();
  }

  async function handleDropResolution(evt) {
    const targetCol = evt.to ? evt.to.dataset.column : null;
    const cardStatus = evt.item.dataset.status;
    const cardId = evt.item.dataset.id;
    const job = jobById(cardId);
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
      const job = jobById(cardId);
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

  async function runHappyPathFromMulti(cardId, action) {
    try {
      const r = await api.changeStatus(cardId, action.action);
      const job = jobById(cardId);
      if (job) job.status = r.status;
      renderKanban();
      api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); });
      toast(`Status: ${r.status}`, 'ok');
      if (state.selectedId === cardId) openInspector(cardId);
    } catch (e) {
      toast('Status change failed: ' + extractError(e), 'err');
    }
  }

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
      const job = jobById(cardId);
      if (job) job.status = r.status;
      renderKanban();
      api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); });
      toast(`Status: ${r.status}`, 'ok');
      if (state.selectedId === cardId) openInspector(cardId);
    } catch (e) {
      toast('Status change failed: ' + extractError(e), 'err');
    }
  }

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
          <div class="nav-label">Repair Jobs</div>
          <div id="viewsList" role="tablist" aria-label="Views"></div>
        </nav>

        <nav class="nav-section">
          <div class="nav-label">Workspace</div>
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
            ${state.canWrite ? `
            <button class="btn btn-primary" type="button" id="btnOpenCreateDrawer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              New Repair Job
            </button>
            <a class="btn btn-ghost" href="/app/repair-job/new" target="_blank" rel="noopener" title="Open ERPNext form (advanced)" style="font-size:11.5px;color:var(--text-faint);margin-left:4px;">⤴</a>
            ` : `
            <span class="btn btn-ghost" style="font-size:11.5px;color:var(--text-faint);cursor:default;" title="Read-only access">Read-only</span>
            `}
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
            <button class="filter-chip is-toggle is-on" id="scopeChip" type="button" aria-pressed="true" title="Hide Closed / Lost / Spam / Unrelated">
              <span class="chip-dot" aria-hidden="true"></span> Active only
            </button>
            <label class="filter-chip filter-chip-select" title="Filter by city / area">
              <span>City</span>
              <select id="cityFilter">
                <option value="">All cities</option>
              </select>
            </label>
            <label class="filter-chip filter-chip-select" title="Sort order">
              <span>Sort</span>
              <select id="sortFilter">
                <option value="modified_desc">Updated ↓</option>
                <option value="call_datetime_desc">Call time ↓</option>
                <option value="creation_desc">Created ↓</option>
                <option value="next_follow_up_asc">Follow-up ↑</option>
                <option value="urgency">Urgency</option>
                <option value="oldest_stuck">Oldest stuck</option>
              </select>
            </label>
            <button class="filter-chip" type="button" disabled title="Coming soon">Dispatcher</button>
            <button class="filter-chip" type="button" disabled title="Coming soon">Marketing source</button>
          </div>
          <div class="date-strip" role="group" aria-label="Date filter">
            <label class="filter-chip filter-chip-select" title="Choose which date the chips below filter on">
              <span>Date</span>
              <select id="dateTypeFilter">
                <option value="">Date type…</option>
                <option value="call">Call / lead</option>
                <option value="follow_up">Follow-up</option>
                <option value="created">Created</option>
                <option value="updated">Updated</option>
              </select>
            </label>
            <button class="filter-chip date-chip" type="button" data-date-preset="today">Today</button>
            <button class="filter-chip date-chip" type="button" data-date-preset="yesterday">Yesterday</button>
            <button class="filter-chip date-chip" type="button" data-date-preset="tomorrow">Tomorrow</button>
            <button class="filter-chip date-chip" type="button" data-date-preset="this_week">This week</button>
            <button class="filter-chip date-chip" type="button" data-date-preset="overdue">Overdue</button>
            <button class="filter-chip date-chip" type="button" data-date-preset="no_date">No date</button>
            <button class="filter-chip date-chip is-clear" type="button" data-date-preset="clear" title="Clear date filter">Clear</button>
          </div>
        </div>

        <div class="work-table-wrap" id="listView">
          <div class="table-head">
            <span class="th-title">Repair Jobs</span>
            <span class="th-count" id="rowCount">0 results</span>
            <div class="right"></div>
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
                  <th scope="col">Dispatcher</th>
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

        <div id="kanbanLoadMoreWrap"></div>
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

      <aside class="create-drawer" id="createDrawer" role="dialog" aria-modal="true" aria-labelledby="createDrawerTitle" aria-hidden="true" tabindex="-1">
        <div class="insp-head">
          <div class="col-main">
            <div class="insp-id">New Repair Job</div>
            <h2 id="createDrawerTitle">Create a Repair Job</h2>
            <div class="insp-meta">
              <span>Required fields are marked *</span>
            </div>
          </div>
          <button class="insp-close" id="createDrawerClose" aria-label="Close drawer" title="Close (Esc)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="insp-body" id="createDrawerBody">
          <div id="dedupBanners"></div>
          <form id="createRepairJobForm" autocomplete="off" novalidate></form>
        </div>
        <div class="insp-actionbar">
          <button class="btn btn-outline" type="button" id="btnCreateCancel">Cancel</button>
          <button class="btn btn-primary" type="button" id="btnCreateSubmit" disabled>Create Repair Job</button>
        </div>
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
    const totalEl = $('#totalCount');
    if (totalEl) totalEl.textContent = state.stateCounts.All ?? state.jobs.length;

    if (!state.jobs.length) {
      tbody.innerHTML = `<tr><td colspan="9">
        <div class="empty-table">
          <strong>No Repair Jobs in this view</strong>
          ${state.activeState !== 'All'
            ? '<div>Try a different state tab or "All".</div>'
            : '<div>When calls arrive from Zadarma, they will appear here.</div>'}
          ${state.canWrite ? `
          <div class="empty-actions">
            <button type="button" class="btn btn-primary" id="btnOpenCreateDrawerFromEmpty">+ Create Repair Job</button>
          </div>
          ` : ''}
        </div>
      </td></tr>`;
      return;
    }

    tbody.innerHTML = state.jobs.map(renderRow).join('');
  }

  function renderRow(j) {
    const s = STATUS_MAP[j.status] || { color: 'slate' };
    const dispatcher = j.assigned_dispatcher || '';
    const dispatcherHtml = dispatcher
      ? `<div class="dispatcher-cell"><div class="avatar ${colorClass(dispatcher)}" aria-hidden="true">${escapeHtml(initials(dispatcher))}</div><span>${escapeHtml(dispatcher)}</span></div>`
      : `<div class="dispatcher-cell empty">No dispatcher</div>`;
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
          <button class="status-pill s-${s.color}" type="button" data-status-btn data-job-id="${escapeHtml(j.name)}" data-stop aria-label="Status ${escapeHtml(j.status || '')}, click to change" aria-haspopup="listbox">
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
        <td>${dispatcherHtml}</td>
        <td><div class="time-cell">${escapeHtml(formatDateTime(j.modified))}<small>${escapeHtml(formatRelativeTime(j.modified))}</small></div></td>
      </tr>
    `;
  }

  // ---------------------------------------------------------------------------
  // 6b. Kanban view
  // ---------------------------------------------------------------------------
  function renderKanban() {
    const kanban = $('#kanban');
    if (!kanban) return;
    // Drag-in-flight guard (audit bug 1.8): never wipe and re-mount the kanban
    // while SortableJS is actively manipulating it — the DOM swap kills the drag.
    if (activeSortableEvt) { state._kanbanRenderDeferred = true; return; }
    const cols = [
      { title: 'Intake',        keys: ['New','Need Follow-up'] },
      { title: 'Sales',         keys: ['Diagnostics Offered','Waiting Prepayment','Diagnostics Paid','Estimate Sent','Waiting Client Approval'] },
      { title: 'Production',    keys: ['Technician Assigned','Diagnostics In Progress','Diagnosis Completed','Parts Needed','Repair In Progress','Repair Completed'] },
      { title: 'Money & Care',  keys: ['Invoice Sent','Paid','Warranty Active','Closed'] },
      { title: 'Out',           keys: ['Lost','Spam','Unrelated'] },
    ];
    // Single O(n) pass to bucket jobs by status — avoids 5x filter scans.
    const byStatus = new Map();
    for (const j of state.jobs) {
      const arr = byStatus.get(j.status);
      if (arr) arr.push(j); else byStatus.set(j.status, [j]);
    }
    kanban.innerHTML = cols.map(col => {
      const items = col.keys.flatMap(k => byStatus.get(k) || []);
      const dotColor = STATUS_MAP[col.keys[0]]?.color || 'slate';
      return `
        <div class="kanban-col">
          <div class="kanban-col-head">
            <span class="kc-dot" style="background:var(--c-${dotColor});" aria-hidden="true"></span>
            <span class="kc-name">${escapeHtml(col.title)}</span>
            <span class="kc-count">${items.length}</span>
          </div>
          <div class="kanban-col-body" data-column="${escapeHtml(col.title)}">
            ${items.map(kanbanCardHtml).join('')}
          </div>
        </div>
      `;
    }).join('');
    initDragDrop();
  }

  function kanbanCardHtml(j) {
    const s = STATUS_MAP[j.status] || { color: 'slate' };
    const customerLabel = (j.customer || '').replace(/^DEMO\s*-\s*/i, '');
    const urgencyCls = (j.urgency || 'Unknown').replace(/\s+/g, '-');
    return `
      <div class="kanban-card" data-id="${escapeHtml(j.name)}" data-status="${escapeHtml(j.status)}">
        <span class="kc-handle" data-stop aria-label="Drag ${escapeHtml(customerLabel || j.name)}" title="Drag to move" tabindex="-1">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <circle cx="9" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/>
            <circle cx="15" cy="6" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="15" cy="18" r="1.5"/>
          </svg>
        </span>
        <div class="kc-body">
          <div class="kc-title" title="${escapeHtml(customerLabel || j.name)}">${escapeHtml(customerLabel || j.name)}</div>
          <div class="kc-row">
            <span class="urg ${escapeHtml(urgencyCls)}" aria-hidden="true"></span>
            <span class="status-pill s-${s.color}" data-stop><span class="dot" aria-hidden="true"></span>${escapeHtml(j.status)}</span>
            <span class="kc-when">${escapeHtml(formatRelativeTime(j.modified))}</span>
          </div>
        </div>
      </div>`;
  }

  // ---------------------------------------------------------------------------
  // 7. Data loading
  // ---------------------------------------------------------------------------
  function buildJobArgs(extra = {}) {
    // Base session state, then overlay the active view's filters, then `extra`
    // (used by loadMore for offset etc.). View filters win against session,
    // but `extra` always wins last so it can override.
    const base = {
      state: state.activeState,
      search: state.search,
      scope: state.scope,
      city: state.city || null,
      sort_by: state.sortBy,
      date_type: state.dateType || null,
      date_preset: state.datePreset || null,
      date_from: state.dateFrom || null,
      date_to: state.dateTo || null,
      limit: state.pageLimit,
      offset: 0,
    };
    const view = viewById(state.activeViewId);
    const args = { ...base, ...view.filters, ...extra };
    if (Array.isArray(args.statuses)) {
      args.statuses = JSON.stringify(args.statuses);
    }
    return args;
  }

  async function loadAll({ refreshCounts = true } = {}) {
    try {
      const args = buildJobArgs();
      const [res, counts] = await Promise.all([
        api.getJobs(args),
        refreshCounts ? api.stateCounts() : Promise.resolve(state.stateCounts),
      ]);
      const jobs = Array.isArray(res) ? res : (res && res.jobs) || [];
      setJobs(jobs);
      state.jobsHasMore = !!(res && res.has_more);
      state.jobsTotal = (res && typeof res.total === 'number') ? res.total : null;
      if (counts) state.stateCounts = counts;
      renderStateTabs();
      renderTable();
      renderLoadMore();
      if (state.activeView === 'kanban') renderKanban();
    } catch (e) {
      console.error('loadAll failed', e);
      toast('Failed to load Repair Jobs. ' + extractError(e), 'err');
    }
  }

  async function loadMore() {
    const btn = $('#kanbanLoadMore');
    if (btn) btn.disabled = true;
    try {
      const args = buildJobArgs({ offset: state.jobs.length });
      const res = await api.getJobs(args);
      const more = Array.isArray(res) ? res : (res && res.jobs) || [];
      const merged = state.jobs.concat(more);
      setJobs(merged);
      state.jobsHasMore = !!(res && res.has_more);
      state.jobsTotal = (res && typeof res.total === 'number') ? res.total : state.jobsTotal;
      renderTable();
      renderLoadMore();
      if (state.activeView === 'kanban') renderKanban();
    } catch (e) {
      toast('Load more failed: ' + extractError(e), 'err');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function renderLoadMore() {
    const host = $('#kanbanLoadMoreWrap');
    if (!host) return;
    if (!state.jobsHasMore) { host.innerHTML = ''; return; }
    const remaining = state.jobsTotal != null ? Math.max(0, state.jobsTotal - state.jobs.length) : null;
    const label = remaining != null
      ? `Load more (${remaining} remaining)`
      : `Load more`;
    host.innerHTML = `
      <div class="load-more-bar">
        <div class="load-more-info">Showing ${state.jobs.length}${state.jobsTotal != null ? ` of ${state.jobsTotal}` : ''}</div>
        <button id="kanbanLoadMore" type="button" class="btn">${escapeHtml(label)}</button>
      </div>`;
  }

  function renderViewsSidebar() {
    const host = $('#viewsList');
    if (!host) return;
    const active = state.activeViewId;
    host.innerHTML = VIEWS.map(v => `
      <button class="nav-item ${v.id === active ? 'active' : ''}" type="button"
              role="tab" aria-selected="${v.id === active ? 'true' : 'false'}"
              data-view-id="${escapeHtml(v.id)}" title="${escapeHtml(v.label)}">
        ${VIEW_ICONS[v.icon] || ''}
        <span>${escapeHtml(v.label)}</span>
      </button>
    `).join('');
  }

  function selectView(viewId) {
    if (state.activeViewId === viewId) return;
    state.activeViewId = viewId;
    renderViewsSidebar();
    loadAll({ refreshCounts: false });
  }

  function updateDateStripUI() {
    const sel = $('#dateTypeFilter');
    if (sel) sel.value = state.dateType || '';
    $$('.date-chip[data-date-preset]').forEach(btn => {
      const on = btn.dataset.datePreset === state.datePreset && state.datePreset !== '';
      btn.classList.toggle('is-on', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  // ---------------------------------------------------------------------------
  // 8. Inspector — open + render tab content
  // ---------------------------------------------------------------------------
  let lastFocusedBeforeInspector = null;

  async function openInspector(id) {
    const j = jobById(id);
    if (!j) return;
    if (state.createOpen) closeCreateDrawer({ force: true });
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

    // Install focus trap (audit bug 1.6). Previous trap, if any, cleared first.
    if (state.inspectorTrapUninstall) state.inspectorTrapUninstall();
    state.inspectorTrapUninstall = installFocusTrap(insp, {
      initialFocus: $('#inspClose') || null,
    });
  }

  function closeInspector() {
    state.selectedId = null;
    state.timeline = null;
    if (state.inspectorTrapUninstall) {
      state.inspectorTrapUninstall();
      state.inspectorTrapUninstall = null;
    }
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
          const jobObj = jobById(job);
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
    const j = jobById(jobName);
    return j ? j[fieldname] : null;
  }

  function writeJobField(jobName, fieldname, value) {
    const j = jobById(jobName);
    if (j) j[fieldname] = value;
  }

  function extractError(e) {
    if (!e) return 'unknown error';
    const raw = e._server_messages || (e.responseJSON && e.responseJSON._server_messages);
    if (raw) {
      try {
        const msgs = typeof raw === 'string' ? JSON.parse(raw) : raw;
        const first = Array.isArray(msgs) ? msgs[0] : msgs;
        if (typeof first === 'string') {
          try { return JSON.parse(first).message || first; }
          catch { return first; }
        }
        if (first && typeof first === 'object') return first.message || JSON.stringify(first);
      } catch { /* fall through */ }
      return String(raw);
    }
    if (e.exception) return String(e.exception);
    if (e.message) return e.message;
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
    state.statusPopoverTrigger = targetEl;
    const job = jobById(jobId);
    if (!job) {
      console.warn('Status popover requested for unknown Repair Job', jobId);
      toast('Could not open status actions: job data is not loaded.', 'err');
      return;
    }

    const r = targetEl.getBoundingClientRect();
    const popWidth = 280;
    const popHeight = 390;
    const left = Math.max(8, Math.min(r.left, window.innerWidth - popWidth - 8));
    const below = r.bottom + 6;
    const above = r.top - popHeight - 6;
    const top = (below + popHeight > window.innerHeight && above > 8)
      ? above
      : Math.min(below, window.innerHeight - popHeight - 8);
    pop.style.top = `${Math.max(8, top)}px`;
    pop.style.left = `${left}px`;

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
    const trigger = state.statusPopoverTrigger;
    state.statusPopoverTrigger = null;
    if (trigger && typeof trigger.focus === 'function') {
      try { trigger.focus(); } catch (e) {}
    }
  }

  async function applyAction(jobId, action) {
    closeStatusPopover();
    try {
      const r = await api.changeStatus(jobId, action);
      writeJobField(jobId, 'status', r.status);
      renderTable();
      if (state.selectedId === jobId) {
        const j = jobById(jobId);
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
      const j = jobById(state.selectedId);
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
            const j = jobById(data.name);
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
      // View switch (List / Kanban) — handled first so other delegated cases below don't intercept
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

      const viewBtn2 = e.target.closest('#viewsList .nav-item[data-view-id]');
      if (viewBtn2) {
        selectView(viewBtn2.dataset.viewId);
        return;
      }

      const stateTab = e.target.closest('.state-tab');
      if (stateTab) {
        state.activeState = stateTab.dataset.state;
        renderStateTabs();
        loadAll({ refreshCounts: false });
        return;
      }

      const scopeChip = e.target.closest('#scopeChip');
      if (scopeChip) {
        state.scope = state.scope === 'active' ? 'all' : 'active';
        const on = state.scope === 'active';
        scopeChip.classList.toggle('is-on', on);
        scopeChip.setAttribute('aria-pressed', on ? 'true' : 'false');
        scopeChip.firstElementChild.nextSibling.textContent = on ? ' Active only' : ' All jobs';
        loadAll({ refreshCounts: false });
        return;
      }

      if (e.target.closest('#kanbanLoadMore')) {
        loadMore();
        return;
      }

      const dateChip = e.target.closest('.date-chip[data-date-preset]');
      if (dateChip) {
        const preset = dateChip.dataset.datePreset;
        if (preset === 'clear') {
          state.datePreset = '';
        } else {
          // Leads are usually reviewed by call date; follow-up remains selectable.
          if (!state.dateType) state.dateType = 'call';
          state.datePreset = (state.datePreset === preset) ? '' : preset;
        }
        updateDateStripUI();
        loadAll({ refreshCounts: false });
        return;
      }

      const statusBtn = e.target.closest('[data-status-btn]');
      const row = e.target.closest('tr[data-id]');
      if (statusBtn) {
        const jobId = statusBtn.dataset.jobId || (row && row.dataset.id);
        e.stopPropagation();
        e.preventDefault();
        if (jobId) openStatusPopover(statusBtn, jobId);
        else toast('Could not identify this Repair Job row.', 'err');
        return;
      }

      const inspPill = e.target.closest('#inspStatusPill');
      if (inspPill && state.selectedId) {
        openStatusPopover(inspPill, state.selectedId);
        return;
      }

      const popItem = e.target.closest('.pop-item[data-action]:not([data-drag-action])');
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

      const card = e.target.closest('.kanban-card[data-id]');
      if (card && !e.target.closest('[data-stop]')) {
        openInspector(card.dataset.id);
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

      if (e.target.closest('#btnOpenCreateDrawer') || e.target.closest('#btnOpenCreateDrawerFromEmpty')) {
        openCreateDrawer();
        return;
      }
      if (e.target.closest('#createDrawerClose') || e.target.closest('#btnCreateCancel')) {
        closeCreateDrawer();
        return;
      }
      if (e.target.closest('#btnCreateSubmit')) {
        submitCreateRepairJob();
        return;
      }

      if (e.target.closest('#inspOverlay')
          && !e.target.closest('.inspector')
          && !e.target.closest('.create-drawer')) {
        if (state.createOpen) closeCreateDrawer();
        else closeInspector();
        return;
      }

      // Close customer typeahead panel on outside click
      if (!e.target.closest('#cr_customer_panel') && !e.target.closest('#cr_customer')) {
        const panel = $('#cr_customer_panel');
        if (panel) panel.classList.remove('open');
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
        const j = jobById(state.selectedId);
        if (j) renderInspBody(j);
      }
    });

    // City + Sort + Date-type filters
    document.addEventListener('change', (e) => {
      if (!e.target) return;
      if (e.target.id === 'cityFilter') {
        state.city = e.target.value || '';
        loadAll({ refreshCounts: false });
      } else if (e.target.id === 'sortFilter') {
        state.sortBy = e.target.value || 'modified_desc';
        loadAll({ refreshCounts: false });
      } else if (e.target.id === 'dateTypeFilter') {
        state.dateType = e.target.value || '';
        // Switching to "Date type…" clears the preset too
        if (!state.dateType) state.datePreset = '';
        updateDateStripUI();
        if (state.datePreset) loadAll({ refreshCounts: false });
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
        if (state.createOpen) { closeCreateDrawer(); return; }
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
  // Section 18: Create Repair Job drawer
  // ---------------------------------------------------------------------------
  function openCreateDrawer() {
    if (state.selectedId) closeInspector();
    state.createOpen = true;
    state.createDraft = { force_create_new: false };
    state.createForceNew = false;
    state.createDedupWarnings = null;
    state.createSubmitting = false;
    renderCreateForm();
    renderDedupBanners();
    const drawer = $('#createDrawer');
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    $('#inspOverlay').classList.add('open');
    if (state.createTrapUninstall) state.createTrapUninstall();
    state.createTrapUninstall = installFocusTrap(drawer, {
      initialFocus: drawer.querySelector('input[name="customer_name"]') || $('#createDrawerClose'),
    });
    const btn = $('#btnOpenCreateDrawer');
    if (btn) btn.disabled = true;
  }

  function closeCreateDrawer({ force = false } = {}) {
    if (!state.createOpen) return;
    if (!force && createDirty()) {
      showConfirmDialog({
        title: 'Discard new Repair Job?',
        desc: 'Your changes will be lost.',
        okLabel: 'Discard',
      }).then(ok => { if (ok) closeCreateDrawer({ force: true }); });
      return;
    }
    state.createOpen = false;
    state.createDraft = null;
    state.createDedupWarnings = null;
    state.createForceNew = false;
    const drawer = $('#createDrawer');
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    if (!state.selectedId) $('#inspOverlay').classList.remove('open');
    if (state.createTrapUninstall) {
      state.createTrapUninstall();
      state.createTrapUninstall = null;
    }
    const btn = $('#btnOpenCreateDrawer');
    if (btn) btn.disabled = false;
  }

  function createDirty() {
    const d = state.createDraft || {};
    return !!(d.customer_name || d.caller_phone || d.equipment_type
              || d.symptom || d.service_address || d.internal_comment
              || d.service_state || d.urgency
              || d.business_phone_did || d.marketing_source
              || d.area);
  }

  function renderCreateForm() {
    const f = $('#createRepairJobForm');
    if (!f) return;
    const d = state.createDraft || {};
    const lockedCustomer = !!d.customer_id;

    f.innerHTML = `
      <div class="field-row" data-field="customer">
        <label for="cr_customer">Customer <span class="required-mark">*</span></label>
        <div class="typeahead-host">
          ${lockedCustomer ? `
            <div class="typeahead-locked">
              <span>✓ ${escapeHtml(d.customer_name || d.customer_id)}</span>
              <button type="button" class="unlock" id="cr_customer_unlock" aria-label="Unlock and re-search">×</button>
            </div>
          ` : `
            <input type="text" id="cr_customer" name="customer_name" value="${escapeHtml(d.customer_name || '')}" placeholder="Type business name…" autocomplete="off">
            <div class="typeahead-panel" id="cr_customer_panel" role="listbox"></div>
          `}
        </div>
        <div class="field-error" id="err_customer" style="display:none;">Required</div>
      </div>

      <div class="field-row" data-field="caller_phone">
        <label for="cr_phone">Caller phone <span class="required-mark">*</span></label>
        <input type="tel" id="cr_phone" name="caller_phone" value="${escapeHtml(d.caller_phone || '')}" placeholder="+1 212 555 0101 — any format">
        <div class="field-error" id="err_caller_phone" style="display:none;">Required</div>
      </div>

      <div class="field-row" data-field="service_state">
        <label for="cr_state">Service state <span class="required-mark">*</span></label>
        <select id="cr_state" name="service_state">
          <option value="">— pick —</option>
          <option value="Texas"     ${d.service_state === 'Texas' ? 'selected' : ''}>Texas</option>
          <option value="Florida"   ${d.service_state === 'Florida' ? 'selected' : ''}>Florida</option>
          <option value="New York"  ${d.service_state === 'New York' ? 'selected' : ''}>New York</option>
          <option value="New Jersey" ${d.service_state === 'New Jersey' ? 'selected' : ''}>New Jersey</option>
        </select>
        <div class="field-error" id="err_service_state" style="display:none;">Required</div>
      </div>

      <div class="field-row" data-field="equipment_type">
        <label for="cr_equip">Equipment type <span class="required-mark">*</span></label>
        <input type="text" id="cr_equip" name="equipment_type" value="${escapeHtml(d.equipment_type || '')}" placeholder="Combi Oven / Walk-in Cooler / …">
        <div class="field-error" id="err_equipment_type" style="display:none;">Required</div>
      </div>

      <div class="field-row" data-field="symptom">
        <label for="cr_symptom">Symptom <span class="required-mark">*</span></label>
        <textarea id="cr_symptom" name="symptom" rows="2" placeholder="What's wrong with the equipment?">${escapeHtml(d.symptom || '')}</textarea>
        <div class="field-error" id="err_symptom" style="display:none;">Required</div>
      </div>

      <div class="field-row" data-field="urgency">
        <label for="cr_urgency">Urgency <span class="required-mark">*</span></label>
        <select id="cr_urgency" name="urgency">
          <option value="">— pick —</option>
          <option value="Emergency"  ${d.urgency === 'Emergency' ? 'selected' : ''}>Emergency</option>
          <option value="Today"      ${d.urgency === 'Today' ? 'selected' : ''}>Today</option>
          <option value="This Week"  ${d.urgency === 'This Week' ? 'selected' : ''}>This Week</option>
          <option value="Scheduled"  ${d.urgency === 'Scheduled' ? 'selected' : ''}>Scheduled</option>
          <option value="Unknown"    ${d.urgency === 'Unknown' ? 'selected' : ''}>Unknown</option>
        </select>
        <div class="field-error" id="err_urgency" style="display:none;">Required</div>
      </div>

      <button type="button" class="optional-fields-toggle" id="cr_optional_toggle" aria-expanded="${d.__optionalOpen ? 'true' : 'false'}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <polyline points="${d.__optionalOpen ? '6 9 12 15 18 9' : '9 6 15 12 9 18'}"/>
        </svg>
        Optional fields
      </button>
      <div class="optional-fields ${d.__optionalOpen ? 'expanded' : ''}" id="cr_optional">
        <div class="field-row"><label for="cr_did">Business DID</label>
          <input type="text" id="cr_did" name="business_phone_did" value="${escapeHtml(d.business_phone_did || '')}"></div>
        <div class="field-row"><label for="cr_source">Marketing source</label>
          <input type="text" id="cr_source" name="marketing_source" value="${escapeHtml(d.marketing_source || '')}"></div>
        <div class="field-row"><label for="cr_area">Area (city/region)</label>
          <input type="text" id="cr_area" name="area" value="${escapeHtml(d.area || '')}"></div>
        <div class="field-row"><label for="cr_addr">Service address</label>
          <textarea id="cr_addr" name="service_address" rows="2" placeholder="e.g. 124 East 50th, New York, NY 10022">${escapeHtml(d.service_address || '')}</textarea></div>
        <div class="field-row"><label for="cr_note">Internal comment</label>
          <textarea id="cr_note" name="internal_comment" rows="2">${escapeHtml(d.internal_comment || '')}</textarea></div>
      </div>
    `;

    bindCreateFormEvents();
    updateSubmitEnabled();
  }

  function bindCreateFormEvents() {
    const f = $('#createRepairJobForm');
    if (!f) return;

    f.addEventListener('input', (e) => {
      const name = e.target.name;
      if (!name) return;
      const d = state.createDraft || (state.createDraft = {});
      d[name] = e.target.value;
      updateSubmitEnabled();
      const err = $('#err_' + name);
      if (err) err.style.display = 'none';
      const row = e.target.closest('.field-row');
      if (row) row.classList.remove('invalid');

      if (name === 'customer_name') triggerCustomerTypeahead(e.target.value);
      if (name === 'caller_phone') triggerPhoneDedupCheck();
    });

    const tgl = $('#cr_optional_toggle');
    if (tgl) tgl.addEventListener('click', () => {
      const d = state.createDraft || (state.createDraft = {});
      d.__optionalOpen = !d.__optionalOpen;
      const panel = $('#cr_optional');
      const svg = tgl.querySelector('polyline');
      if (d.__optionalOpen) { panel.classList.add('expanded'); if (svg) svg.setAttribute('points', '6 9 12 15 18 9'); }
      else { panel.classList.remove('expanded'); if (svg) svg.setAttribute('points', '9 6 15 12 9 18'); }
      tgl.setAttribute('aria-expanded', d.__optionalOpen ? 'true' : 'false');
    });

    const unlock = $('#cr_customer_unlock');
    if (unlock) unlock.addEventListener('click', () => {
      const d = state.createDraft;
      delete d.customer_id;
      renderCreateForm();
      setTimeout(() => $('#cr_customer')?.focus(), 0);
    });
  }

  function updateSubmitEnabled() {
    const d = state.createDraft || {};
    const required = ['caller_phone', 'service_state', 'equipment_type', 'symptom', 'urgency'];
    const customerOk = !!(d.customer_id || (d.customer_name && d.customer_name.trim()));
    const requiredOk = required.every(k => (d[k] || '').toString().trim());
    const w = state.createDedupWarnings;
    const blockedByDedup = !!(w && w.phone_multi_match && w.phone_multi_match.length > 1
                              && !state.createForceNew && !d.customer_id);
    const enable = customerOk && requiredOk && !blockedByDedup && !state.createSubmitting;
    const btn = $('#btnCreateSubmit');
    if (btn) btn.disabled = !enable;
  }

  // -- Customer typeahead --
  let customerTypeaheadTimer = null;
  function triggerCustomerTypeahead(q) {
    clearTimeout(customerTypeaheadTimer);
    customerTypeaheadTimer = setTimeout(() => doCustomerTypeahead(q), 200);
  }

  async function doCustomerTypeahead(q) {
    const panel = $('#cr_customer_panel');
    if (!panel) return;
    const query = (q || '').trim();
    if (query.length < 2) { panel.classList.remove('open'); panel.innerHTML = ''; return; }

    let results;
    if (state.customerLookupCache.has(query)) {
      results = state.customerLookupCache.get(query);
    } else {
      try { results = await api.searchLink('Customer', query); }
      catch (e) { console.error('typeahead failed', e); return; }
      state.customerLookupCache.set(query, results);
    }

    const d = state.createDraft || {};
    const items = (results || []).slice(0, 8).map(r => `
      <button type="button" class="typeahead-item" role="option"
              data-customer-id="${escapeHtml(r.value)}"
              data-customer-name="${escapeHtml(r.label || r.value)}">
        ${escapeHtml(r.label || r.value)}
      </button>`).join('');

    let system = '';
    if (query.length >= 3) {
      system += `<button type="button" class="typeahead-item system" data-create-new="1">
        + Create new "${escapeHtml(query)}"
      </button>`;
    }
    if (d.caller_phone && d.caller_phone.trim()) {
      system += `<button type="button" class="typeahead-item system" data-use-phone="1">
        Use phone ${escapeHtml(d.caller_phone)} — no name
      </button>`;
    }

    panel.innerHTML = items + system;
    panel.classList.add('open');

    panel.querySelectorAll('.typeahead-item').forEach(el => {
      el.addEventListener('click', () => {
        if (el.dataset.createNew) { panel.classList.remove('open'); return; }
        if (el.dataset.usePhone) {
          state.createDraft.customer_name = '';
          delete state.createDraft.customer_id;
          renderCreateForm();
          return;
        }
        state.createDraft.customer_id = el.dataset.customerId;
        state.createDraft.customer_name = el.dataset.customerName;
        renderCreateForm();
        triggerPhoneDedupCheck();
      });
    });
  }

  // -- Dedup banners --
  let dedupCheckTimer = null;
  function triggerPhoneDedupCheck() {
    clearTimeout(dedupCheckTimer);
    dedupCheckTimer = setTimeout(() => doPhoneDedupCheck(), 400);
  }

  async function doPhoneDedupCheck() {
    if (!state.createOpen) return;
    const d = state.createDraft || {};
    const phone = (d.caller_phone || '').trim();
    if (!phone && !d.customer_id) {
      state.createDedupWarnings = null;
      renderDedupBanners();
      updateSubmitEnabled();
      return;
    }
    try {
      const r = await call('baro_crm.api.repair_job.find_dedup_warnings', {
        customer: d.customer_id || null,
        customer_name: d.customer_name || null,
        caller_phone: phone || null,
        equipment_type: d.equipment_type || null,
        lookback_days: 90,
      });
      state.createDedupWarnings = r;
      renderDedupBanners();
      updateSubmitEnabled();
    } catch (e) { console.error('find_dedup_warnings failed', e); }
  }

  function renderDedupBanners() {
    const host = $('#dedupBanners');
    if (!host) return;
    const w = state.createDedupWarnings;
    if (!w) { host.innerHTML = ''; return; }
    const parts = [];

    if (w.phone_multi_match && w.phone_multi_match.length > 1) {
      const list = w.phone_multi_match.map(c =>
        `<button type="button" class="btn-mini" data-pick-customer="${escapeHtml(c)}">${escapeHtml(c)}</button>`
      ).join(' ');
      parts.push(`
        <div class="dedup-banner block">
          <strong>Phone matches ${w.phone_multi_match.length} customers.</strong>
          Pick one or tick "Create new anyway" to proceed with a new Customer.
          <div class="actions">${list}</div>
          <label class="force-create-new-row">
            <input type="checkbox" id="cr_force_new" ${state.createForceNew ? 'checked' : ''}>
            Create new Customer anyway
          </label>
        </div>`);
    }
    if (w.phone_match_customer) {
      parts.push(`
        <div class="dedup-banner info">
          Phone matches existing Customer <strong>${escapeHtml(w.phone_match_customer)}</strong> —
          will be linked unless you pick a different Customer.
        </div>`);
    }
    if (w.similar_customers && w.similar_customers.length) {
      const list = w.similar_customers.map(s =>
        `<button type="button" class="btn-mini" data-pick-customer="${escapeHtml(s.name)}">${escapeHtml(s.customer_name)}</button>`
      ).join(' ');
      parts.push(`
        <div class="dedup-banner warn">
          Similar existing customers — verify this isn't a duplicate:
          <div class="actions">${list}</div>
        </div>`);
    }
    if (w.active_jobs && w.active_jobs.length) {
      const list = w.active_jobs.slice(0, 3).map(rj => `
        <div class="actions">
          <strong>${escapeHtml(rj.name)}</strong> · ${escapeHtml(rj.equipment_type || '—')} · ${escapeHtml(rj.reason || '')}
          <button type="button" class="btn-mini" data-open-rj="${escapeHtml(rj.name)}">Open RJ</button>
        </div>`).join('');
      parts.push(`
        <div class="dedup-banner warn">
          <strong>Possible existing active job(s):</strong>
          ${list}
        </div>`);
    }

    host.innerHTML = parts.join('');

    host.querySelectorAll('[data-pick-customer]').forEach(el => {
      el.addEventListener('click', () => {
        state.createDraft.customer_id = el.dataset.pickCustomer;
        state.createDraft.customer_name = el.dataset.pickCustomer;
        state.createForceNew = false;
        renderCreateForm();
        renderDedupBanners();
        updateSubmitEnabled();
      });
    });
    host.querySelectorAll('[data-open-rj]').forEach(el => {
      el.addEventListener('click', () => {
        const id = el.dataset.openRj;
        closeCreateDrawer({ force: true });
        openInspector(id);
      });
    });
    const fcn = $('#cr_force_new');
    if (fcn) fcn.addEventListener('change', () => {
      state.createForceNew = fcn.checked;
      state.createDraft.force_create_new = fcn.checked;
      updateSubmitEnabled();
    });
  }

  // -- Submit --
  async function submitCreateRepairJob() {
    if (state.createSubmitting) return;
    const d = state.createDraft || {};
    const required = ['caller_phone', 'service_state', 'equipment_type', 'symptom', 'urgency'];
    const customerOk = !!(d.customer_id || (d.customer_name && d.customer_name.trim()));
    let firstInvalid = null;

    if (!customerOk) {
      const row = $('#createRepairJobForm [data-field="customer"]');
      if (row) row.classList.add('invalid');
      const err = $('#err_customer'); if (err) err.style.display = '';
      firstInvalid = firstInvalid || (row && row.querySelector('input,textarea,select'));
    }
    for (const k of required) {
      const val = (d[k] || '').toString().trim();
      if (!val) {
        const row = $(`#createRepairJobForm [data-field="${k}"]`);
        if (row) row.classList.add('invalid');
        const err = $(`#err_${k}`); if (err) err.style.display = '';
        firstInvalid = firstInvalid || (row && row.querySelector('input,textarea,select'));
      }
    }
    if (firstInvalid) { firstInvalid.focus(); return; }

    const payload = {};
    for (const k of ['customer_id', 'customer_name', 'caller_phone', 'business_phone_did',
                     'area', 'service_state', 'marketing_source', 'service_address',
                     'equipment_type', 'symptom', 'urgency', 'internal_comment']) {
      if (d[k] && d[k].toString().trim()) payload[k] = d[k].toString().trim();
    }
    if (state.createForceNew) payload.force_create_new = true;

    state.createSubmitting = true;
    const btn = $('#btnCreateSubmit');
    btn.disabled = true;
    btn.textContent = 'Creating…';

    try {
      const r = await call('baro_crm.api.repair_job.create_repair_job', { payload });
      const newJob = r.doc;
      const merged = [newJob].concat(state.jobs);
      setJobs(merged);
      if (state.jobsTotal != null) state.jobsTotal += 1;

      if (state.activeView === 'list') {
        const tbody = $('#tableBody');
        if (tbody) tbody.insertAdjacentHTML('afterbegin', renderRow(newJob));
      } else if (state.activeView === 'kanban') {
        const colTitle = colTitleForStatus(newJob.status);
        if (colTitle) {
          const body = document.querySelector(`.kanban-col-body[data-column="${escapeAttr(colTitle)}"]`);
          if (body) body.insertAdjacentHTML('afterbegin', kanbanCardHtml(newJob));
        }
      }

      api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); }).catch(() => {});

      const warningSummary = (r.warnings || []).map(w => w.message).filter(Boolean).join(' · ');
      toast(`Created ${r.name}${warningSummary ? ' · ' + warningSummary : ''}`, 'ok');

      closeCreateDrawer({ force: true });
      openInspector(r.name);
    } catch (e) {
      console.error('create_repair_job failed', e);
      const msg = extractError(e);
      const host = $('#dedupBanners');
      if (host && msg.toLowerCase().includes('matches') && msg.toLowerCase().includes('customers')) {
        host.insertAdjacentHTML('afterbegin',
          `<div class="dedup-banner block"><strong>Cannot create.</strong> ${escapeHtml(msg)}</div>`);
      }
      toast('Create failed: ' + msg, 'err');
    } finally {
      state.createSubmitting = false;
      btn.disabled = false;
      btn.textContent = 'Create Repair Job';
      updateSubmitEnabled();
    }
  }

  function colTitleForStatus(status) {
    const cols = {
      'Intake':       ['New', 'Need Follow-up'],
      'Sales':        ['Diagnostics Offered', 'Waiting Prepayment', 'Diagnostics Paid', 'Estimate Sent', 'Waiting Client Approval'],
      'Production':   ['Technician Assigned', 'Diagnostics In Progress', 'Diagnosis Completed', 'Parts Needed', 'Repair In Progress', 'Repair Completed'],
      'Money & Care': ['Invoice Sent', 'Paid', 'Warranty Active', 'Closed'],
      'Out':          ['Lost', 'Spam', 'Unrelated'],
    };
    for (const [title, set] of Object.entries(cols)) if (set.includes(status)) return title;
    return null;
  }

  function escapeAttr(s) { return String(s).replace(/"/g, '&quot;'); }

  // ---------------------------------------------------------------------------
  // 15. Boot
  // ---------------------------------------------------------------------------
  async function boot() {
    state.canWrite = meta('cockpit_can_write', '0') === '1';
    state.user = meta('cockpit_user', '');
    try {
      const ctx = await api.bootContext();
      if (ctx) {
        state.canWrite = String(ctx.can_write_repair_job) === '1';
        state.user = ctx.user || state.user;
      }
    } catch (e) {
      console.warn('Boot context failed; using page meta fallback', e);
    }
    renderShell();
    renderViewsSidebar();
    bindEvents();
    setupRealtime();
    // Fire filter options + initial jobs in parallel; cities are non-blocking.
    api.filterOptions().then(opts => {
      state.cities = (opts && opts.cities) || [];
      const sel = $('#cityFilter');
      if (sel) {
        const current = state.city;
        sel.innerHTML = '<option value="">All cities</option>'
          + state.cities.map(c => `<option value="${escapeHtml(c)}"${c === current ? ' selected' : ''}>${escapeHtml(c)}</option>`).join('');
      }
    }).catch(e => console.warn('filterOptions failed', e));
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
