const STATUS_FLOW = ["New", "Need Follow-up", "Diagnostics Offered", "Waiting Prepayment", "Diagnostics Paid", "Technician Assigned", "Diagnostics In Progress", "Diagnosis Completed", "Estimate Sent", "Waiting Client Approval", "Parts Needed", "Repair In Progress", "Repair Completed", "Invoice Sent", "Paid", "Warranty Active", "Closed"];

const STATUS_COLUMNS = [
  { title: "Intake", tone: "sales", statuses: ["New", "Need Follow-up", "Diagnostics Offered", "Waiting Prepayment"] },
  { title: "Diagnostics", tone: "production", statuses: ["Diagnostics Paid", "Technician Assigned", "Diagnostics In Progress", "Diagnosis Completed"] },
  { title: "Estimate", tone: "sales", statuses: ["Estimate Sent", "Waiting Client Approval", "Parts Needed"] },
  { title: "Repair", tone: "production", statuses: ["Repair In Progress", "Repair Completed"] },
  { title: "Money", tone: "money", statuses: ["Invoice Sent", "Paid", "Warranty Active", "Closed"] },
  { title: "Noise", tone: "risk", statuses: ["Lost", "Spam", "Unrelated"] }
];

const STAGE_FILTERS = {
  all: STATUS_COLUMNS.flatMap((column) => column.statuses),
  sales: ["New", "Need Follow-up", "Diagnostics Offered", "Waiting Prepayment", "Estimate Sent", "Waiting Client Approval"],
  production: ["Diagnostics Paid", "Technician Assigned", "Diagnostics In Progress", "Diagnosis Completed", "Parts Needed", "Repair In Progress", "Repair Completed"],
  money: ["Invoice Sent", "Paid", "Warranty Active", "Closed"]
};

const sampleJobs = [
  {
    id: "RJ-2026-0042", customer: "Tradewinds Resort", contact: "Country Miller", phone: "+1 727 776 0653", did: "+1 813 564 8399", email: "not collected", address: "St. Pete Beach, FL", area: "FL-Tampa Bay", source: "Tampa-Miami", recording: "Zadarma recording link", datetime: "Today 09:00", duration: "01:41", status: "Need Follow-up", service: "Leasing inquiry / dishwasher", equipment: "Dishwashing machine", brand: "Unknown", model: "Banquet area unit", symptom: "Client asks whether Baro can lease and install a new dish machine.", urgency: "This Week", diagnosticPrice: "$0", prepayment: "Not Requested", dispatcher: "Lena", estimateManager: "Menna", regularManager: "Elena", productionManager: "Mohamed", technician: "Unassigned", mentor: "Unassigned", diagnosis: "Needs sales clarification: Baro repairs/installs, lease offering not confirmed.", estimate: "$0", approval: "Need Follow-up", partsStatus: "Not Needed", warrantyEnd: "None", nextFollowup: "Today 11:30", callQuality: "6/10 - client intent clear, policy unclear, contact data incomplete.", purpose: "Ask whether Baro leases dishwasher machines.", clientInfo: "Tradewinds Resort, banquet/function areas, St. Pete Beach.", summary: "Client wants leasing contract for a dishwashing machine. Agent answered installation/repair but did not clearly answer leasing. Follow-up should confirm if leasing is offered or route to sales partner.", transcript: "Client: I am looking to talk to somebody about leasing a dishwashing machine for our banquet and function areas. Agent: We do installation and repair, yes. Client: Do you lease or no? Agent: If you mean installation and repair, yes. We do not sell machines.", risk: true,
    history: [["Call received", "Zadarma call transcribed and summarized by AI."], ["Follow-up needed", "Clarify leasing policy and collect email/full address."], ["Owner suggested", "Estimate manager should call back before noon."]]
  },
  {
    id: "RJ-2026-0041", customer: "Santiago - Jersey Avenue", contact: "Santiago", phone: "+1 732 484 9733", did: "+1 347 919 4188", email: "not collected", address: "64 Jersey Avenue, New Brunswick, NJ 08901", area: "NY/NJ", source: "BaroSite NY", recording: "Zadarma recording link", datetime: "Yesterday 13:51", duration: "03:46", status: "Waiting Prepayment", service: "Diagnostics / HVAC display panel", equipment: "Frederick AC + heater 20,000 BTU", brand: "Frederick", model: "20,000 BTU", symptom: "Display panel cannot change temperature.", urgency: "Today", diagnosticPrice: "$199", prepayment: "Requested", dispatcher: "Vanessa", estimateManager: "Menna", regularManager: "Elena", productionManager: "Mohamed", technician: "Unassigned", mentor: "Unassigned", diagnosis: "Manufacturer requires licensed technician diagnosis for reimbursement/replacement.", estimate: "TBD", approval: "Not Sent", partsStatus: "Need Identify", warrantyEnd: "None", nextFollowup: "Today 10:00", callQuality: "8/10 - good communication, license requirement noted, email missing.", purpose: "Schedule licensed diagnostic service.", clientInfo: "Client accepted diagnostic and is available until evening.", summary: "Client accepts diagnostic service call and needs a licensed company diagnosis. Dispatch should collect prepayment, confirm ETA, and assign technician.", transcript: "Client: The company told me I need to give me the diagnosis. The company has gotta have a license. Agent: We can send someone today. The service call diagnostics is $199.", risk: true,
    history: [["Call received", "Client accepted diagnostic concept."], ["Prepayment requested", "$199 diagnostic should be collected before dispatch."], ["Missing data", "Email and confirmed arrival time missing."]]
  },
  {
    id: "RJ-2026-0039", customer: "Friendship Missionary Baptist Church", contact: "Richard Clark", phone: "+1 727 643 8435", did: "+1 727 390 2465", email: "not collected", address: "St. Petersburg, FL", area: "FL-St. Petersburg", source: "yard signs Tampa", recording: "Zadarma recording link", datetime: "Yesterday 15:00", duration: "03:10", status: "Diagnostics Offered", service: "Diagnostics / commercial freezer", equipment: "Upright commercial freezer", brand: "Unknown", model: "Unknown", symptom: "Freezer not holding temperature; fan blows warm air.", urgency: "Today", diagnosticPrice: "$159", prepayment: "Not Requested", dispatcher: "Lena", estimateManager: "Ghassan", regularManager: "Elena", productionManager: "Mohamed", technician: "Unassigned", mentor: "Unassigned", diagnosis: "Likely refrigeration issue; needs diagnostics before estimate.", estimate: "TBD", approval: "Not Sent", partsStatus: "Need Identify", warrantyEnd: "None", nextFollowup: "Tomorrow 09:15", callQuality: "8/10 - price explained, decision-maker follow-up required.", purpose: "Ask cost and availability for freezer diagnostics.", clientInfo: "Church culinary ministry; secretary approval required.", summary: "Client is interested but needs approval from church secretary. Follow-up should capture address/email and schedule once approved.", transcript: "Client: I have the commercial freezer, and it went out on me. Agent: Diagnostics is $159 and used toward repair cost. Client: Let me run it by the church secretary.", risk: true,
    history: [["Diagnostics offered", "$159 explained and minimum repair mentioned."], ["Decision pending", "Secretary approval needed."], ["Follow-up scheduled", "Call tomorrow morning if client does not call back."]]
  },
  {
    id: "RJ-2026-0037", customer: "J Kay Restaurant", contact: "J Kay", phone: "+1 941 879 5827", did: "+1 727 677 9167", email: "not collected", address: "Sarasota / St. Petersburg area", area: "FL-Sarasota", source: "Sarasota website", recording: "Zadarma recording link", datetime: "Yesterday 19:47", duration: "04:27", status: "Technician Assigned", service: "Diagnostics / restaurant hood motor", equipment: "Restaurant hood", brand: "Unknown", model: "Unknown", symptom: "Hood is not working; possible motor issue.", urgency: "Today", diagnosticPrice: "$199", prepayment: "Paid", dispatcher: "Vanessa", estimateManager: "Ghassan", regularManager: "Elena", productionManager: "Mohamed", technician: "Alex P.", mentor: "Mustafa", diagnosis: "Technician scheduled for tomorrow morning; exact ETA needs text confirmation.", estimate: "TBD", approval: "Not Sent", partsStatus: "Need Identify", warrantyEnd: "None", nextFollowup: "Today 08:30", callQuality: "8/10 - service fit clear, address still missing.", purpose: "Repair restaurant hood with suspected motor problem.", clientInfo: "Client requested text updates because unknown calls go to voicemail.", summary: "Good repair opportunity. Text client, confirm address, confirm ETA, technician assigned.", transcript: "Client: The hood is not working, someone said the motor is out. Agent: We can send technician tomorrow morning. Diagnostics is $199 and goes toward repair cost.", risk: true,
    history: [["Diagnostic sold", "Client agreed to service call."], ["Technician assigned", "Alex P. assigned with mentor Mustafa."], ["Text required", "Client asked for SMS ETA confirmation."]]
  },
  {
    id: "RJ-2026-0034", customer: "503-509 Communipaw Avenue LLC", contact: "Adrian", phone: "+1 551 247 1317", did: "+1 347 919 4188", email: "not collected", address: "424 Arlington Ave, Jersey City, NJ 07304", area: "NY/NJ", source: "BaroSite NY", recording: "Zadarma recording link", datetime: "Yesterday 15:26", duration: "03:14", status: "Estimate Sent", service: "Maintenance / espresso machine cleaning", equipment: "Lavia Barista E400 espresso machine", brand: "Lavia", model: "Barista E400", symptom: "Cup-holder magnet/plate keeps falling down; cleaning requested.", urgency: "This Week", diagnosticPrice: "$199", prepayment: "Requested", dispatcher: "Vanessa", estimateManager: "Menna", regularManager: "Elena", productionManager: "Mohamed", technician: "Omar S.", mentor: "Mustafa", diagnosis: "Maintenance + magnet/cup holder inspection needed.", estimate: "$359 minimum repair", approval: "Sent", partsStatus: "Need Identify", warrantyEnd: "None", nextFollowup: "Today 14:00", callQuality: "7/10 - pricing explained, authorization pending.", purpose: "Service and clean espresso machine; inspect cup holder issue.", clientInfo: "Business name/address captured; authorization pending from decision-maker.", summary: "Client needs confirmation from another person before approving diagnostics/repair. Follow up with clear quote and missing email.", transcript: "Client: We need to service the machine, like a good cleaning, and this magnet keeps falling down. Agent: We perform diagnostics, cleaning and provide report.", risk: false,
    history: [["Quote explained", "$199 diagnostic and $359 minimum repair discussed."], ["Authorization pending", "Adrian will confirm and call back."], ["Estimate sent", "Follow-up set for 2 PM."]]
  },
  {
    id: "RJ-2026-0028", customer: "Miami Lavazza Caller", contact: "Unknown", phone: "+1 516 455 5847", did: "+1 786 746 9043", email: "not collected", address: "Miami, FL", area: "FL-Miami", source: "Miami site", recording: "Zadarma recording link", datetime: "Yesterday 15:22", duration: "01:07", status: "Lost", service: "Parts inquiry only", equipment: "Lavazza coffee machine", brand: "Lavazza", model: "Unknown", symptom: "Needs floater part only; no repair visit requested.", urgency: "Unknown", diagnosticPrice: "$0", prepayment: "Not Requested", dispatcher: "Vanessa", estimateManager: "Ghassan", regularManager: "Elena", productionManager: "Mohamed", technician: "Unassigned", mentor: "Unassigned", diagnosis: "Baro does not sell standalone parts.", estimate: "$0", approval: "Rejected", partsStatus: "Not Needed", warrantyEnd: "None", nextFollowup: "None", callQuality: "7/10 - policy clear, no service conversion.", purpose: "Buy a standalone Lavazza floater part.", clientInfo: "Parts-only customer; no repair job requested.", summary: "Not a fit unless client later wants technician visit. Mark lost but keep searchable record.", transcript: "Client: I need a little part called the floater. Do you carry them? Agent: We do not sell parts; we send technician to diagnose and provide required parts.", risk: false,
    history: [["Parts-only call", "Client wanted standalone part."], ["Policy explained", "Baro does not sell parts without service."], ["Closed as lost", "Keep in customer history for future searches."]]
  }
];

const initialState = {
  selectedJobId: "RJ-2026-0042",
  stageFilter: "all",
  viewFilter: "all",
  onlyNew: false,
  jobs: sampleJobs,
  techs: [
    { name: "Alex P.", initials: "AP", area: "FL-Sarasota", skills: "hoods, motors, HVAC", load: 62, eta: "35 min", jobs: ["RJ-2026-0037"] },
    { name: "Omar S.", initials: "OS", area: "NY/NJ", skills: "espresso, refrigeration", load: 48, eta: "55 min", jobs: ["RJ-2026-0034"] },
    { name: "Diego R.", initials: "DR", area: "FL-Tampa Bay", skills: "dishwashers, freezers", load: 32, eta: "22 min", jobs: [] },
    { name: "Sam K.", initials: "SK", area: "NY/NJ", skills: "AC, diagnostics", load: 24, eta: "40 min", jobs: [] }
  ],
  followups: [
    { type: "Warranty", title: "Warranty check: espresso repair", detail: "Ask client if machine is stable 5 days before warranty ends.", due: "Apr 24", tone: "money" },
    { type: "Invoice", title: "Invoice pending: restaurant hood", detail: "Invoice draft should be prepared after technician report.", due: "Today", tone: "risk" },
    { type: "Customer care", title: "No lost client rule", detail: "Call back Tradewinds and clarify leasing answer.", due: "11:30", tone: "sales" }
  ]
};

let state = loadState();

function loadState() {
  try {
    const saved = localStorage.getItem("baroCrmPrototype");
    return saved ? JSON.parse(saved) : structuredClone(initialState);
  } catch (error) {
    return structuredClone(initialState);
  }
}

function persist() {
  localStorage.setItem("baroCrmPrototype", JSON.stringify(state));
}

function $(selector, root = document) {
  return root.querySelector(selector);
}

function $all(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

function selectedJob() {
  return state.jobs.find((job) => job.id === state.selectedJobId) || state.jobs[0];
}

function statusTone(status) {
  const column = STATUS_COLUMNS.find((item) => item.statuses.includes(status));
  return column ? column.tone : "sales";
}

function matchesSearch(job) {
  const query = $("#globalSearch").value.trim().toLowerCase();
  if (!query) return true;

  return [
    job.id,
    job.customer,
    job.contact,
    job.phone,
    job.did,
    job.address,
    job.area,
    job.source,
    job.service,
    job.equipment,
    job.symptom,
    job.status
  ].join(" ").toLowerCase().includes(query);
}

function isRisk(job) {
  return job.risk || job.email === "not collected" || job.technician === "Unassigned" || ["Need Follow-up", "Waiting Prepayment"].includes(job.status);
}

function render() {
  ensureSelected();
  renderMetrics();
  renderTicker();
  renderCalls();
  renderKanban();
  renderInspector();
  renderTechs();
  renderFollowups();
  applyViewFilter();
  persist();
}

function ensureSelected() {
  if (!state.jobs.some((job) => job.id === state.selectedJobId)) {
    state.selectedJobId = state.jobs[0]?.id || null;
  }
}

function renderMetrics() {
  $("#metricCalls").textContent = state.jobs.length;
  $("#metricDiagnostics").textContent = state.jobs.filter((job) => ["Diagnostics Paid", "Technician Assigned", "Diagnostics In Progress", "Diagnosis Completed"].includes(job.status)).length;
  $("#metricFollowup").textContent = state.jobs.filter((job) => job.status === "Need Follow-up" || job.approval === "Need Follow-up").length;
  $("#metricRisk").textContent = state.jobs.filter(isRisk).length;
}

function renderTicker() {
  const unassigned = state.jobs.filter((job) => job.technician === "Unassigned" && !["Lost", "Spam", "Unrelated"].includes(job.status)).length;
  const paid = state.jobs.filter((job) => job.prepayment === "Paid").length;
  const selected = selectedJob();

  $("#statusTicker").innerHTML = [
    ["Open repair jobs", `${state.jobs.filter((job) => !["Closed", "Lost", "Spam", "Unrelated"].includes(job.status)).length}`],
    ["Paid diagnostics", `${paid}`],
    ["Unassigned jobs", `${unassigned}`],
    ["Selected status", selected.status]
  ].map(([label, value]) => `<div class="ticker-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function renderCalls() {
  const list = $("#callList");
  list.innerHTML = "";

  const visible = state.jobs
    .filter(matchesSearch)
    .filter((job) => !state.onlyNew || ["New", "Need Follow-up"].includes(job.status))
    .sort((a, b) => STATUS_FLOW.indexOf(a.status) - STATUS_FLOW.indexOf(b.status));

  visible.forEach((job) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `call-row ${job.id === state.selectedJobId ? "active" : ""}`;
    row.dataset.jobId = job.id;
    row.dataset.priority = isRisk(job) ? "high" : job.status === "Diagnostics Offered" ? "medium" : "normal";
    row.innerHTML = `
      <span class="call-pulse"></span>
      <span class="call-main">
        <strong>${escapeHtml(job.customer)}</strong>
        <small>${escapeHtml(job.phone)} -> ${escapeHtml(job.did)}</small>
      </span>
      <span class="call-meta">${escapeHtml(job.duration)}</span>
    `;
    row.addEventListener("click", () => selectJob(job.id));
    list.appendChild(row);
  });

  if (!visible.length) {
    list.innerHTML = `<div class="transcript-box">No calls match this filter. Clear search or show all records.</div>`;
  }
}

function renderKanban() {
  const allowed = STAGE_FILTERS[state.stageFilter] || STAGE_FILTERS.all;
  const kanban = $("#kanban");
  kanban.innerHTML = "";

  STATUS_COLUMNS.forEach((column) => {
    const columnJobs = state.jobs.filter((job) => column.statuses.includes(job.status) && allowed.includes(job.status) && matchesSearch(job));
    if (state.stageFilter !== "all" && !columnJobs.length) return;

    const el = document.createElement("section");
    el.className = "kanban-column";
    el.innerHTML = `
      <div class="column-title">
        <strong>${column.title}</strong>
        <span>${columnJobs.length}</span>
      </div>
      <div class="job-stack"></div>
    `;

    const stack = $(".job-stack", el);
    columnJobs.forEach((job) => stack.appendChild(jobCard(job)));
    kanban.appendChild(el);
  });
}

function jobCard(job) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `job-card ${job.id === state.selectedJobId ? "active" : ""}`;
  button.dataset.jobId = job.id;
  button.innerHTML = `
    <div class="job-top">
      <strong>${escapeHtml(job.customer)}</strong>
      <span class="status-chip" data-tone="${statusTone(job.status)}">${escapeHtml(job.status)}</span>
    </div>
    <small>${escapeHtml(job.service)}</small>
    <div class="job-tags">
      <span class="status-chip">${escapeHtml(job.area)}</span>
      <span class="status-chip">${escapeHtml(job.equipment)}</span>
      ${isRisk(job) ? `<span class="status-chip" data-tone="risk">risk</span>` : ""}
    </div>
  `;
  button.addEventListener("click", () => selectJob(job.id));
  return button;
}

function renderInspector() {
  const job = selectedJob();
  if (!job) return;

  $("#inspectorTitle").textContent = job.customer;
  $("#recordId").textContent = job.id;
  $("#inspectorContent").innerHTML = `
    <div class="customer-card">
      <section class="customer-hero">
        <p class="eyebrow">Customer chart</p>
        <h4>${escapeHtml(job.customer)}</h4>
        <p>${escapeHtml(job.summary)}</p>
        <div class="mini-metrics">
          <div class="mini-metric"><strong>${escapeHtml(job.status)}</strong><span>status</span></div>
          <div class="mini-metric"><strong>${escapeHtml(job.diagnosticPrice)}</strong><span>diagnostic</span></div>
          <div class="mini-metric"><strong>${escapeHtml(job.prepayment)}</strong><span>prepayment</span></div>
        </div>
      </section>

      <div class="next-action">
        <div>
          <strong>${nextAction(job)}</strong>
          <small>Owner: ${escapeHtml(ownerFor(job))} | Follow-up: ${escapeHtml(job.nextFollowup)}</small>
        </div>
      </div>

      <div class="inspector-controls">
        <button class="control-button primary" data-action="nextStatus">Move next status</button>
        <button class="control-button success" data-action="markPaid">Mark diagnostic paid</button>
        <button class="control-button" data-action="assignTech">Assign technician</button>
        <button class="control-button" data-action="sendEstimate">Send estimate</button>
        <button class="control-button danger" data-action="markLost">Mark lost</button>
      </div>

      <div class="field-grid">
        ${field("Contact", job.contact)}
        ${field("Phone", job.phone)}
        ${field("Address", job.address)}
        ${field("Email", job.email)}
        ${field("Area", job.area)}
        ${field("Source", job.source)}
        ${field("Equipment", `${job.equipment} / ${job.brand}`)}
        ${field("Symptom", job.symptom)}
        ${field("Technician", job.technician)}
        ${field("Production", job.productionManager)}
      </div>

      <section>
        <div class="section-heading tight"><div><p class="eyebrow">AI call analysis</p><h3>Transcript and extracted facts</h3></div></div>
        <div class="field-grid">
          ${field("Purpose", job.purpose)}
          ${field("Quality", job.callQuality)}
          ${field("Client info", job.clientInfo)}
          ${field("Recording", job.recording)}
        </div>
        <p class="transcript-box">${escapeHtml(job.transcript)}</p>
      </section>

      <section>
        <div class="section-heading tight"><div><p class="eyebrow">History</p><h3>Every touch in one place</h3></div></div>
        <div class="history">
          ${job.history.map(([title, detail]) => `<div class="history-row"><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(detail)}</small></div><span class="status-chip">saved</span></div>`).join("")}
        </div>
      </section>
    </div>
  `;

  $all("[data-action]", $("#inspectorContent")).forEach((button) => {
    button.addEventListener("click", () => handleAction(button.dataset.action));
  });
}

function field(label, value) {
  return `<div class="field"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value || "Unknown")}</strong></div>`;
}

function renderTechs() {
  const grid = $("#techGrid");
  grid.innerHTML = state.techs.map((tech) => {
    const assigned = tech.jobs.map((id) => state.jobs.find((job) => job.id === id)?.customer).filter(Boolean);

    return `
      <article class="tech-card">
        <div class="tech-head">
          <div class="tech-avatar">${escapeHtml(tech.initials)}</div>
          <span class="status-chip" data-tone="production">${escapeHtml(tech.eta)}</span>
        </div>
        <div>
          <strong>${escapeHtml(tech.name)}</strong>
          <small>${escapeHtml(tech.area)} | ${escapeHtml(tech.skills)}</small>
        </div>
        <div class="load-bar" aria-label="Technician load"><span style="width:${tech.load}%"></span></div>
        <div class="action-row"><small>${assigned.length ? escapeHtml(assigned.join(", ")) : "Available for dispatch"}</small><button class="small-action" data-tech="${escapeHtml(tech.name)}">Assign</button></div>
      </article>
    `;
  }).join("");

  $all("[data-tech]", grid).forEach((button) => {
    button.addEventListener("click", () => assignSpecificTech(button.dataset.tech));
  });
}

function renderFollowups() {
  const timeline = $("#followupTimeline");
  const jobItems = state.jobs
    .filter((job) => job.nextFollowup !== "None" && !["Closed", "Spam", "Unrelated"].includes(job.status))
    .slice(0, 4)
    .map((job) => ({
      type: job.status,
      title: job.customer,
      detail: nextAction(job),
      due: job.nextFollowup,
      tone: statusTone(job.status)
    }));

  const items = [...state.followups, ...jobItems].slice(0, 8);
  timeline.innerHTML = items.map((item) => `
    <article class="timeline-item">
      <span class="timeline-dot"></span>
      <div>
        <span class="status-chip" data-tone="${item.tone}">${escapeHtml(item.type)}</span>
        <strong>${escapeHtml(item.title)}</strong>
        <small>${escapeHtml(item.detail)}</small>
      </div>
      <span class="call-meta">${escapeHtml(item.due)}</span>
    </article>
  `).join("");
}

function nextAction(job) {
  const map = {
    "New": "Review AI summary and create/confirm Customer, Contact and Address.",
    "Need Follow-up": "Call client back; collect missing data and confirm service fit.",
    "Diagnostics Offered": "Close diagnostic sale or schedule follow-up with decision-maker.",
    "Waiting Prepayment": "Collect diagnostic prepayment before dispatch.",
    "Diagnostics Paid": "Assign technician and confirm ETA.",
    "Technician Assigned": "Text client ETA and verify service address.",
    "Diagnostics In Progress": "Technician should submit diagnosis, photos and required parts.",
    "Diagnosis Completed": "Estimate manager prepares quote from technician report.",
    "Estimate Sent": "Follow up until approved or lost.",
    "Waiting Client Approval": "Confirm approval, budget and appointment window.",
    "Parts Needed": "Supply finds/approves parts and updates ETA.",
    "Repair In Progress": "Production manager monitors repair completion.",
    "Repair Completed": "Create invoice and verify customer acceptance.",
    "Invoice Sent": "Collect payment and close accounting loop.",
    "Paid": "Activate warranty and schedule customer care message.",
    "Warranty Active": "Check in before warranty ends.",
    "Closed": "Record is complete; keep searchable history.",
    "Lost": "Keep reason searchable and do not spam the client."
  };

  return map[job.status] || "Review record and choose next step.";
}

function ownerFor(job) {
  if (["New", "Need Follow-up"].includes(job.status)) return job.dispatcher;
  if (["Diagnostics Offered", "Waiting Prepayment", "Estimate Sent", "Waiting Client Approval", "Lost"].includes(job.status)) return job.estimateManager;
  if (["Diagnostics Paid", "Technician Assigned", "Diagnostics In Progress", "Diagnosis Completed", "Parts Needed", "Repair In Progress", "Repair Completed"].includes(job.status)) return job.productionManager;
  if (["Invoice Sent", "Paid"].includes(job.status)) return "Accounting";
  return job.regularManager;
}

function selectJob(id) {
  state.selectedJobId = id;
  render();
}

function handleAction(action) {
  const job = selectedJob();
  if (!job) return;

  if (action === "nextStatus") moveNextStatus(job);
  if (action === "markPaid") markPaid(job);
  if (action === "assignTech") assignBestTech(job);
  if (action === "sendEstimate") sendEstimate(job);
  if (action === "markLost") markLost(job);

  render();
}

function moveNextStatus(job) {
  const index = STATUS_FLOW.indexOf(job.status);
  if (index >= 0 && index < STATUS_FLOW.length - 1) {
    job.status = STATUS_FLOW[index + 1];
    addHistory(job, "Status moved", `Moved to ${job.status}.`);
    toast(`${job.id} moved to ${job.status}`);
  }
}

function markPaid(job) {
  job.prepayment = "Paid";
  if (["New", "Need Follow-up", "Diagnostics Offered", "Waiting Prepayment"].includes(job.status)) {
    job.status = "Diagnostics Paid";
  }
  addHistory(job, "Diagnostic paid", "Payment marked paid and job is ready for production.");
  toast("Diagnostic payment marked as paid.");
}

function assignBestTech(job) {
  const sameArea = state.techs.filter((tech) => tech.area === job.area);
  const pool = sameArea.length ? sameArea : state.techs;
  const best = pool.slice().sort((a, b) => a.load - b.load)[0];
  if (best) assignJobToTech(job, best.name);
}

function assignSpecificTech(name) {
  const job = selectedJob();
  assignJobToTech(job, name);
  render();
}

function assignJobToTech(job, techName) {
  const tech = state.techs.find((item) => item.name === techName);
  if (!job || !tech) return;

  state.techs.forEach((item) => {
    item.jobs = item.jobs.filter((id) => id !== job.id);
  });
  tech.jobs.push(job.id);
  tech.load = Math.min(96, tech.load + 12);
  job.technician = tech.name;
  job.status = ["Diagnostics Paid", "Waiting Prepayment", "Diagnostics Offered", "Need Follow-up", "New"].includes(job.status) ? "Technician Assigned" : job.status;
  addHistory(job, "Technician assigned", `${tech.name} assigned by production manager.`);
  toast(`${tech.name} assigned to ${job.customer}.`);
}

function sendEstimate(job) {
  job.status = "Estimate Sent";
  job.approval = "Sent";
  if (job.estimate === "TBD" || job.estimate === "$0") job.estimate = "$359 minimum repair";
  addHistory(job, "Estimate sent", `${job.estimate} sent to customer for approval.`);
  toast("Estimate sent and follow-up created.");
}

function markLost(job) {
  job.status = "Lost";
  job.approval = "Rejected";
  job.risk = false;
  addHistory(job, "Marked lost", "Kept as searchable customer history, not deleted.");
  toast("Job marked lost but preserved in history.");
}

function addHistory(job, title, detail) {
  job.history.unshift([title, detail]);
}

function createDemoJob(kind = "manual") {
  const idNumber = Math.max(...state.jobs.map((job) => Number(job.id.split("-").pop()))) + 1;
  const id = `RJ-2026-${String(idNumber).padStart(4, "0")}`;
  const job = {
    id,
    customer: kind === "call" ? "New Caller - Houston" : "New Restaurant Lead",
    contact: "Unknown",
    phone: kind === "call" ? "+1 713 597 6912" : "+1 000 000 0000",
    did: kind === "call" ? "+1 713 597 6912" : "+1 347 919 4188",
    email: "not collected",
    address: kind === "call" ? "Houston, TX" : "Address not collected",
    area: kind === "call" ? "TX-Houston" : "NY/NJ",
    source: kind === "call" ? "HoustonGoogleAds2" : "Manual CRM entry",
    recording: kind === "call" ? "New Zadarma recording link" : "No recording yet",
    datetime: "Just now",
    duration: kind === "call" ? "02:18" : "00:00",
    status: "New",
    service: kind === "call" ? "Repair inquiry / refrigeration" : "Manual intake",
    equipment: kind === "call" ? "Commercial refrigerator" : "Unknown equipment",
    brand: "Unknown",
    model: "Unknown",
    symptom: kind === "call" ? "Client reports unit is warm and needs same-day technician." : "Needs qualification.",
    urgency: "Today",
    diagnosticPrice: "$199",
    prepayment: "Not Requested",
    dispatcher: "Lena",
    estimateManager: "Menna",
    regularManager: "Elena",
    productionManager: "Mohamed",
    technician: "Unassigned",
    mentor: "Unassigned",
    diagnosis: "Not diagnosed yet.",
    estimate: "TBD",
    approval: "Not Sent",
    partsStatus: "Need Identify",
    warrantyEnd: "None",
    nextFollowup: "In 20 min",
    callQuality: "Not reviewed yet.",
    purpose: "Qualify incoming service request.",
    clientInfo: "Needs business name, address, email, equipment and symptom confirmation.",
    summary: "New lead requires dispatcher review, customer matching and diagnostic offer.",
    transcript: "New call placeholder. Once AI runs, transcript and summary will be stored here.",
    risk: true,
    history: [["Created", kind === "call" ? "Created from simulated Zadarma call." : "Created manually in CRM prototype."]]
  };

  state.jobs.unshift(job);
  state.selectedJobId = id;
  toast(`${id} created.`);
  render();
}

function addFollowup() {
  const job = selectedJob();
  if (!job) return;

  job.nextFollowup = "Today + 30 min";
  addHistory(job, "Follow-up created", "Customer care reminder added from CRM cockpit.");
  state.followups.unshift({
    type: "Manual follow-up",
    title: job.customer,
    detail: "Call or text client; make sure no lead is forgotten.",
    due: "30 min",
    tone: "sales"
  });
  toast("Follow-up added.");
  render();
}

function autoAssign() {
  const candidates = state.jobs.filter((job) => job.technician === "Unassigned" && ["Diagnostics Paid", "Waiting Prepayment", "Diagnostics Offered"].includes(job.status));
  if (!candidates.length) {
    toast("No eligible unassigned jobs right now.");
    return;
  }

  candidates.forEach(assignBestTech);
  render();
}

function applyViewFilter() {
  const view = state.viewFilter;
  $all(".module-panel").forEach((panel) => panel.classList.remove("hidden-by-filter"));
  if (view === "all") return;

  const keep = new Set([view, "inspector"]);
  $all(".module-panel").forEach((panel) => {
    const section = panel.dataset.section;
    if (!keep.has(section)) panel.classList.add("hidden-by-filter");
  });
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function wireEvents() {
  $("#globalSearch").addEventListener("input", render);
  $("#quickCreate").addEventListener("click", () => createDemoJob("manual"));
  $("#simulateCall").addEventListener("click", () => createDemoJob("call"));
  $("#resetDemo").addEventListener("click", () => {
    localStorage.removeItem("baroCrmPrototype");
    state = structuredClone(initialState);
    $("#globalSearch").value = "";
    toast("Demo reset to original data.");
    render();
  });
  $("#showOnlyNew").addEventListener("click", (event) => {
    state.onlyNew = !state.onlyNew;
    event.currentTarget.textContent = state.onlyNew ? "Show all" : "Show new";
    render();
  });
  $("#autoAssign").addEventListener("click", autoAssign);
  $("#addFollowup").addEventListener("click", addFollowup);

  $all("[data-stage-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.stageFilter = button.dataset.stageFilter;
      $all("[data-stage-filter]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      render();
    });
  });

  $all("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.viewFilter = button.dataset.view;
      $all("[data-view]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      render();
    });
  });
}

wireEvents();
render();
