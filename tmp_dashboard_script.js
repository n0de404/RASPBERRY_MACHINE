
  const clientStatus = document.getElementById("client-status");
  const serverSettingsBtn = document.getElementById("serverSettingsBtn");
  const operatorsDirectoryBtn = document.getElementById("operatorsDirectoryBtn");
  const dailyRolesBtn = document.getElementById("dailyRolesBtn");
  const profileCreatorBtn = document.getElementById("profileCreatorBtn");
  const operatorDirectoryOverlay = document.getElementById("operatorDirectoryOverlay");
  const operatorDirectoryCloseBtn = document.getElementById("operatorDirectoryCloseBtn");
  const operatorDirectoryGrid = document.getElementById("operatorDirectoryGrid");
  const operatorDetailOverlay = document.getElementById("operatorDetailOverlay");
  const operatorDetailCloseBtn = document.getElementById("operatorDetailCloseBtn");
  const operatorDetailTitle = document.getElementById("operatorDetailTitle");
  const operatorDetailSub = document.getElementById("operatorDetailSub");
  const operatorDetailBody = document.getElementById("operatorDetailBody");
  const serverSettingsOverlay = document.getElementById("serverSettingsOverlay");
  const serverSettingsCloseBtn = document.getElementById("serverSettingsCloseBtn");
  const settingsNavGeneral = document.getElementById("settingsNavGeneral");
  const settingsNavTheme = document.getElementById("settingsNavTheme");
  const settingsNavApi = document.getElementById("settingsNavApi");
  const settingsNavProfile = document.getElementById("settingsNavProfile");
  const settingsPageGeneral = document.getElementById("settingsPageGeneral");
  const settingsPageTheme = document.getElementById("settingsPageTheme");
  const settingsPageApi = document.getElementById("settingsPageApi");
  const settingsPageProfile = document.getElementById("settingsPageProfile");
  const settingsServerHost = document.getElementById("settingsServerHost");
  const settingsThemeSelect = document.getElementById("settingsThemeSelect");
  const settingsQrApiBaseUrl = document.getElementById("settingsQrApiBaseUrl");
  const settingsProductsCount = document.getElementById("settingsProductsCount");
  const settingsProductsUpdated = document.getElementById("settingsProductsUpdated");
  const settingsProductsSourceFile = document.getElementById("settingsProductsSourceFile");
  const settingsProductsCacheFile = document.getElementById("settingsProductsCacheFile");
  const settingsProductsStatus = document.getElementById("settingsProductsStatus");
  const settingsProductsRefreshBtn = document.getElementById("settingsProductsRefreshBtn");
  const settingsProfilesTableBody = document.getElementById("settingsProfilesTableBody");
  const serverSettingsSaveBtn = document.getElementById("serverSettingsSaveBtn");
  const dailyRolesOverlay = document.getElementById("dailyRolesOverlay");
  const dailyRolesCloseBtn = document.getElementById("dailyRolesCloseBtn");
  const dailyRoleBadgeInput = document.getElementById("dailyRoleBadgeInput");
  const dailyRoleNameInput = document.getElementById("dailyRoleNameInput");
  const dailyRoleCompanyRoleInput = document.getElementById("dailyRoleCompanyRoleInput");
  const dailyRoleExtraPrivilegeSelect = document.getElementById("dailyRoleExtraPrivilegeSelect");
  const dailyRoleEffectiveRightsInput = document.getElementById("dailyRoleEffectiveRightsInput");
  const dailyRolesSaveBtn = document.getElementById("dailyRolesSaveBtn");
  const dailyRolesList = document.getElementById("dailyRolesList");
  const timeEl = document.getElementById("time");
  const lastMessageEl = document.getElementById("last-message");
  const machineCountEl = document.getElementById("machine-count");
  const machineGrid = document.getElementById("machineGrid");
  const jobQueueSummary = document.getElementById("jobQueueSummary");
  const jobQueueTableWrap = document.getElementById("jobQueueTableWrap");
  const finishedShiftQueueList = document.getElementById("finishedShiftQueueList");
  const finishedShiftJobProgress = document.getElementById("finishedShiftJobProgress");
  const finishedJobsList = document.getElementById("finishedJobsList");
  const archivedJobsTableWrap = document.getElementById("archivedJobsTableWrap");
  const machineStatusArchiveTableWrap = document.getElementById("machineStatusArchiveTableWrap");
  const downtimeArchiveTableWrap = document.getElementById("downtimeArchiveTableWrap");
  const maintenanceSummary = document.getElementById("maintenanceSummary");
  const maintenancePeopleList = document.getElementById("maintenancePeopleList");
  const maintenancePerformanceTableWrap = document.getElementById("maintenancePerformanceTableWrap");
  const maintenanceCurrentDate = document.getElementById("maintenanceCurrentDate");
  const approvePrintOverlay = document.getElementById("approvePrintOverlay");
  const overlayCloseBtn = document.getElementById("overlayCloseBtn");
  const overlayCancelBtn = document.getElementById("overlayCancelBtn");
  const overlayGenerateBtn = document.getElementById("overlayGenerateBtn");
  const overlayRequestBtn = document.getElementById("overlayRequestBtn");
  const overlayJobInfo = document.getElementById("overlayJobInfo");
  const overlayReviewJobInfo = document.getElementById("overlayReviewJobInfo");
  const overlayReviewJobInfoDisplay = document.getElementById("overlayReviewJobInfoDisplay");
  const overlayReviewSummary = document.getElementById("overlayReviewSummary");
  const overlayReviewRejects = document.getElementById("overlayReviewRejects");
  const overlayReviewSummaryDisplay = document.getElementById("overlayReviewSummaryDisplay");
  const overlayReviewRejectsDisplay = document.getElementById("overlayReviewRejectsDisplay");
  const overlayRawConsumption = document.getElementById("overlayRawConsumption");
  const overlayRawCycleSummary = document.getElementById("overlayRawCycleSummary");
  const overlayDowntimeSummary = document.getElementById("overlayDowntimeSummary");
  const overlayPeopleSummary = document.getElementById("overlayPeopleSummary");
  const overlayRawConsumptionDisplay = document.getElementById("overlayRawConsumptionDisplay");
  const overlayRawCycleSummaryDisplay = document.getElementById("overlayRawCycleSummaryDisplay");
  const overlayDowntimeSummaryDisplay = document.getElementById("overlayDowntimeSummaryDisplay");
  const overlayPeopleSummaryDisplay = document.getElementById("overlayPeopleSummaryDisplay");
  const overlayReviewerBadge = document.getElementById("overlayReviewerBadge");
  const overlayReviewerScanInput = document.getElementById("overlayReviewerScanInput");
  const overlayOpenScanFieldBtn = document.getElementById("overlayOpenScanFieldBtn");
  const overlayReviewRemarks = document.getElementById("overlayReviewRemarks");
  const overlayReviewAction = document.getElementById("overlayReviewAction");
  const overlayDisapproveFields = document.getElementById("overlayDisapproveFields");
  const editPackCount = document.getElementById("editPackCount");
  const editGoodTotal = document.getElementById("editGoodTotal");
  const editButalTotal = document.getElementById("editButalTotal");
  const editRejectTotal = document.getElementById("editRejectTotal");
  const editTotalGood = document.getElementById("editTotalGood");
  const editRejectBreakdown = document.getElementById("editRejectBreakdown");
  const overlayReviewSubmitBtn = document.getElementById("overlayReviewSubmitBtn");
  const overlayReviewContinueBtn = document.getElementById("overlayReviewContinueBtn");
  const overlayBackToReviewBtn = document.getElementById("overlayBackToReviewBtn");
  const overlayReviewStep = document.getElementById("overlayReviewStep");
  const overlayQrStep = document.getElementById("overlayQrStep");
  const overlayReviewPrevBtn = document.getElementById("overlayReviewPrevBtn");
  const overlayReviewNextBtn = document.getElementById("overlayReviewNextBtn");
  const overlayReviewSlideStatus = document.getElementById("overlayReviewSlideStatus");
  const reviewSubslide1 = document.getElementById("reviewSubslide1");
  const reviewSubslide2 = document.getElementById("reviewSubslide2");
  const reviewSubslide3 = document.getElementById("reviewSubslide3");
  const reviewSubslide4 = document.getElementById("reviewSubslide4");
  const overlayProductSelect = document.getElementById("overlayProductSelect");
  const overlayProductSuggest = document.getElementById("overlayProductSuggest");
  const overlayQrPayload = document.getElementById("overlayQrPayload");
  const overlayPoNumber = document.getElementById("overlayPoNumber");
  const overlayQty = document.getElementById("overlayQty");
  const overlayIndex = document.getElementById("overlayIndex");
  const overlayTotal = document.getElementById("overlayTotal");
  const overlayLotNumber = document.getElementById("overlayLotNumber");
  const overlayPoNumberRow = overlayPoNumber ? overlayPoNumber.closest(".overlay-row") : null;
  const machineDetailOverlay = document.getElementById("machineDetailOverlay");
  const machineDetailSettingsBtn = document.getElementById("machineDetailSettingsBtn");
  const machineDetailCloseBtn = document.getElementById("machineDetailCloseBtn");
  const machineDetailTitle = document.getElementById("machineDetailTitle");
  const machineDetailStatusPanel = document.getElementById("machineDetailStatusPanel");
  const machineDetailStatusSelect = document.getElementById("machineDetailStatusSelect");
  const machineDetailStatusReason = document.getElementById("machineDetailStatusReason");
  const machineDetailStatusSetterBadge = document.getElementById("machineDetailStatusSetterBadge");
  const machineDetailStatusSaveBtn = document.getElementById("machineDetailStatusSaveBtn");
  const machineStatusSaveFeedback = document.getElementById("machineStatusSaveFeedback");
  const machineStatusSaveBar = document.getElementById("machineStatusSaveBar");
  const machineStatusSaveCheck = document.getElementById("machineStatusSaveCheck");
  const machineDetailBody = document.getElementById("machineDetailBody");
  const qrScanCaptureOverlay = document.getElementById("qrScanCaptureOverlay");
  const qrScanCaptureInput = document.getElementById("qrScanCaptureInput");
  const qrScanCaptureCancelBtn = document.getElementById("qrScanCaptureCancelBtn");
  const MACHINE_NAME_MAP = {
    "M00001": "IMM 301",
    "M00002": "IMM 302",
    "M00003": "IMM 303",
    "M00004": "IMM 304",
    "M00005": "IMM 305",
    "M00006": "IMM 306",
    "M00007": "IMM 307",
    "M00008": "IMM 308",
    "M00009": "IMM 309",
    "M00010": "IMM 310",
    "M00011": "IMM 311",
    "M00012": "IMM 312",
    "M00013": "IMM 313",
    "M00014": "IMM 314",
    "M00015": "IMM 315",
    "M00016": "IMM 316",
    "M00017": "IMM 317",
    "M00018": "IMM 318",
    "M00019": "IMM 319",
    "M00020": "IMM 320",
    "M00021": "IMM 321",
  };
  const DEFAULT_MACHINE_CODES = Object.keys(MACHINE_NAME_MAP);
  let latestState = { sessions: [], active_ttl_seconds: 30 };
  let operatorDirectoryState = [];
  const machineCardEls = new Map();
  let finishedJobsState = [];
  let finishedShiftState = [];
  let archivedJobsState = [];
  let machineStatusArchiveState = [];
  let maintenanceCardIndexByKey = {};
  let finishedJobsInteractionLock = false;
  let pendingFinishedJobsRows = null;
  let productItems = [];
  let activeJobRow = null;
  let productsHydrated = false;
  let productSuggestionItems = [];
  let productSuggestionIndex = -1;
  const PRODUCT_SUGGEST_LIMIT = 8;
  let generatedQrState = {
    jobKey: "",
    payload: "",
    qty: "",
    index: "",
    total: "",
    lotNumber: "",
    stageLabel: "",
    stageKind: "",
    plan: [],
    planIndex: 0,
    printRequests: [],
  };
  let overlayReviewSavedApproved = false;
  let reviewSlideIndex = 0;
  let overlayReviewMode = "job";
  let serverSettingsState = { theme: "Default", qrgen_base_url: "" };
  let dailyRolesState = {};
  let settingsProfilesState = [];
  let machineStatusOverridesState = {};
  let activeMachineDetailCode = "";

  function esc(s){ return (s ?? "").toString().replaceAll("&","&amp;").replaceAll("<","&lt;"); }
  function escJson(v){
    try { return esc(JSON.stringify(v ?? {}, null, 2)); } catch { return esc(String(v ?? "")); }
  }

  function statusClass(lastSeenUtc, activeTtlSeconds = 30, manualStatus = ""){
    if(String(manualStatus || "").trim()) return "maintenance";
    if(!lastSeenUtc) return "disconnected";
    const seen = new Date(lastSeenUtc).getTime();
    if(Number.isNaN(seen)) return "disconnected";
    const ageSec = (Date.now() - seen) / 1000;
    return ageSec <= Number(activeTtlSeconds || 30) ? "active" : "disconnected";
  }

  function fmtDateLocal(iso){
    if(!iso) return "-";
    const d = new Date(iso);
    if(Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
  }

  function fmtDowntimeSeconds(s){
    const n = Number(s);
    if(!Number.isFinite(n) || n < 0) return "-";
    const t = Math.floor(n);
    const hh = Math.floor(t / 3600);
    const mm = Math.floor((t % 3600) / 60);
    const ss = t % 60;
    return `${String(hh).padStart(2,"0")}:${String(mm).padStart(2,"0")}:${String(ss).padStart(2,"0")}`;
  }

  function rawMaterialName(entry){
    const item = (entry && typeof entry === "object") ? entry : {};
    const label = item.material_name || item.material || item.name || item.material_code || item.code || item.value || "-";
    return String(label || "-").trim() || "-";
  }

  function fmtRawMaterialKg(qty){
    const n = Number(qty);
    if(!Number.isFinite(n)) return `${String(qty ?? 0)} kg`;
    return `${n.toFixed(4)} kg`;
  }

  function rawMaterialLine(entry, index = null){
    const prefix = Number.isInteger(index) ? `${index + 1}. ` : "";
    return `${prefix}${rawMaterialName(entry)} | ${fmtRawMaterialKg((entry && entry.qty) ?? 0)}`;
  }

  function renderRawMaterialListHtml(rows){
    const items = Array.isArray(rows) ? rows : [];
    if(!items.length) return `<div class="machine-detail-empty">No raw material consumption records.</div>`;
    return `
      <ol class="machine-detail-list">
        ${items.map(item => `
          <li><strong>${esc(rawMaterialName(item))}</strong> | ${esc(fmtRawMaterialKg((item && item.qty) ?? 0))}</li>
        `).join("")}
      </ol>
    `;
  }

  function extractJobRecord(session){
    const payload = (session && typeof session.job_payload === "object" && session.job_payload) || {};
    if(payload.data && payload.data.job && typeof payload.data.job === "object") return payload.data.job;
    if(payload.job && typeof payload.job === "object") return payload.job;
    return payload;
  }

  function detailItem(label, value){
    return `<div class="machine-detail-item"><div class="k">${esc(label)}</div><div class="v">${esc(value ?? "-")}</div></div>`;
  }

  function machineStatusOverrideFor(code){
    const c = String(code || "").trim();
    return (machineStatusOverridesState && machineStatusOverridesState[c]) || null;
  }

  function openMachineDetail(session){
    if(!session) return;
    activeMachineDetailCode = String(session.machine_code || "").trim();
    const activeTtlSeconds = Number((latestState && latestState.active_ttl_seconds) || 30);
    const manual = machineStatusOverrideFor(activeMachineDetailCode);
    const manualStatus = String((manual && manual.status) || "").trim();
    const manualReason = String((manual && manual.reason) || "").trim();
    const status = manualStatus || statusClass(session.last_seen_utc, activeTtlSeconds).toUpperCase();
    const totalGood = Number(session.good_total || 0) + Number(session.butal_total || 0);
    const job = extractJobRecord(session) || {};
    const rejectBreakdown = (session && typeof session.reject_breakdown === "object" && session.reject_breakdown) || {};
    const rejectRows = Object.entries(rejectBreakdown).sort((a,b) => String(a[0]).localeCompare(String(b[0])));
    const rawScans = Array.isArray(session.raw_material_scans) ? session.raw_material_scans : [];
    const rawLogs = Array.isArray(session.raw_material_logs) ? session.raw_material_logs : [];
    const rawConsumptionHtml = renderRawMaterialListHtml(rawLogs);
    const rejectHtml = rejectRows.length
      ? `<ol class="machine-detail-list">${rejectRows.map(([k,v]) => `<li>${esc(k)} = ${esc(v)}</li>`).join("")}</ol>`
      : `<div class="machine-detail-empty">No reject details recorded.</div>`;

    machineDetailTitle.textContent = `${session.machine_name || session.machine_code || "Machine"} Details`;
    if(machineDetailStatusSelect) machineDetailStatusSelect.value = manualStatus;
    if(machineDetailStatusReason) machineDetailStatusReason.value = manualReason;
    if(machineDetailStatusSetterBadge) machineDetailStatusSetterBadge.value = "";
    if(machineDetailStatusPanel) machineDetailStatusPanel.style.display = "none";
    machineDetailBody.innerHTML = `
      <div class="machine-detail-section">
        <h4>Overview</h4>
        <div class="machine-detail-grid">
          ${detailItem("Machine", session.machine_code || "-")}
          ${detailItem("Machine Name", session.machine_name || "-")}
          ${detailItem("Status", status)}
          ${detailItem("Status Reason", manualReason || "-")}
          ${detailItem("Status Set By", (manual && manual.set_by_name) ? `${manual.set_by_name}${manual.set_by_role ? ` (${manual.set_by_role})` : ""}` : "-")}
          ${detailItem("Status Set At", fmtDateLocal((manual && (manual.started_at_utc || manual.updated_at_utc)) || ""))}
          ${detailItem("Client", displayNameForId(session.client_id || "-"))}
          ${detailItem("Job Code", session.job_code || "-")}
          ${detailItem("Job Name", session.job_name || "-")}
          ${detailItem("Operator", displayNameForId(session.operator_id || "-"))}
          ${detailItem("Last Seen", fmtDateLocal(session.last_seen_utc))}
          ${detailItem("Last Event", session.last_event || "-")}
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Production Counters</h4>
        <div class="machine-detail-grid">
          ${detailItem("Pack", Number(session.pack_total || 0))}
          ${detailItem("Good", Number(session.good_total || 0))}
          ${detailItem("Butal", Number(session.butal_total || 0))}
          ${detailItem("Reject", Number(session.reject_total || 0))}
          ${detailItem("No Shot", Number(session.no_shot_total || 0))}
          ${detailItem("Total Good", totalGood)}
          ${detailItem("Start Up Reject", Number(session.startup_reject_total || 0))}
          ${detailItem("Raw Sacks Count", Number(session.raw_sacks_count || 0))}
          ${detailItem("Cycle Time", session.cycle_time_current || "-")}
          ${detailItem("Downtime Active", session.downtime_active ? "YES" : "NO")}
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Downtime</h4>
        <div class="machine-detail-grid">
          ${detailItem("Reason Code", session.downtime_reason_code || "-")}
          ${detailItem("Reason", session.downtime_reason_text || "-")}
          ${detailItem("Current/Last Duration", fmtDowntimeSeconds(session.downtime_active ? (Date.now()/1000 - Number(session.downtime_started_at || 0)) : session.downtime_last_seconds))}
          ${detailItem("Downtime Start", session.downtime_started_at ? new Date(Number(session.downtime_started_at) * 1000).toLocaleString() : "-")}
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Reject Details</h4>
        ${rejectHtml}
      </div>
      <div class="machine-detail-section">
        <h4>Raw Materials (Scanned IDs)</h4>
        ${rawScans.length ? `<div class="machine-detail-code">${esc(rawScans.join("\\n"))}</div>` : `<div class="machine-detail-empty">No raw materials scanned.</div>`}
      </div>
      <div class="machine-detail-section">
        <h4>Raw Materials Consumption</h4>
        ${rawConsumptionHtml}
      </div>
      <div class="machine-detail-section">
        <h4>Job Details Payload</h4>
        <div class="machine-detail-grid">
          ${detailItem("Job Ref", job.ref_no || job.reference || job.id || "-")}
          ${detailItem("Product ID", job.product_id || "-")}
          ${detailItem("Mold", job.custom_05 || "-")}
          ${detailItem("Color", job.custom_06 || "-")}
          ${detailItem("System Code", job.custom_09 || "-")}
          ${detailItem("Cavities", job.custom_11 || "-")}
        </div>
        <div class="machine-detail-code">${escJson(session.job_payload || {})}</div>
      </div>
    `;
    machineDetailOverlay.classList.add("active");
  }

  function closeMachineDetail(){
    machineDetailOverlay.classList.remove("active");
    activeMachineDetailCode = "";
    if(machineDetailStatusPanel) machineDetailStatusPanel.style.display = "none";
    if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.remove("active");
    if(machineStatusSaveBar) machineStatusSaveBar.style.width = "0%";
    if(machineStatusSaveCheck) machineStatusSaveCheck.classList.remove("done");
  }

  function applyDashboardTheme(themeName){
    const t = String(themeName || "Default").trim() || "Default";
    if(t === "Default" || t === "Blue Accent"){
      delete document.body.dataset.theme;
    } else {
      document.body.dataset.theme = t;
    }
  }

  function showServerSettingsPage(key){
    const map = {
      general: [settingsNavGeneral, settingsPageGeneral],
      theme: [settingsNavTheme, settingsPageTheme],
      api: [settingsNavApi, settingsPageApi],
      profile: [settingsNavProfile, settingsPageProfile],
    };
    Object.entries(map).forEach(([k, pair]) => {
      const [btn, page] = pair;
      btn?.classList.toggle("active", k === key);
      page?.classList.toggle("active", k === key);
    });
  }

  function normalizeCompanyRoleLabel(role){
    const low = String(role || "").trim().toLowerCase();
    if(["qa", "qc", "qa/qc"].includes(low)) return "QA/QC";
    if(low === "production manager") return "Production Manager";
    if(low === "supervisor") return "Supervisor";
    if(low === "operator") return "Operator";
    if(low === "maintenance") return "Maintenance";
    if(low === "planner") return "Planner";
    return String(role || "").trim();
  }

  function basePrivilegeFromRole(role){
    const low = String(role || "").trim().toLowerCase();
    if(low === "supervisor") return "supervisor";
    if(["qa", "qc", "qa/qc"].includes(low)) return "qc";
    if(low === "maintenance") return "maintenance";
    return "viewer";
  }

  function combinePrivileges(base, extra){
    const set = new Set([String(base || "viewer").trim().toLowerCase() || "viewer"]);
    const ex = String(extra || "").trim().toLowerCase();
    if(ex && ex !== "none") set.add(ex);
    if(set.has("supervisor") && set.has("qc")) return "both";
    if(set.has("supervisor")) return "supervisor";
    if(set.has("qc")) return "qc";
    if(set.has("maintenance")) return "maintenance";
    return "viewer";
  }

  function privilegeLabel(v){
    const x = String(v || "").trim().toLowerCase();
    if(x === "both") return "Supervisor + QC";
    if(x === "supervisor") return "Supervisor";
    if(x === "qc") return "QC";
    if(x === "maintenance") return "Maintenance";
    return "Viewer";
  }

  function findSettingsProfileById(id){
    const code = String(id || "").trim();
    return settingsProfilesState.find(p => String(p?.id_number || "").trim() === code) || null;
  }

  function refreshDailyRoleDerivedUi(){
    const badge = (dailyRoleBadgeInput?.value || "").trim();
    const p = findSettingsProfileById(badge);
    const profileName = p ? String(p.name || "").trim() : "";
    const roleLabel = p ? normalizeCompanyRoleLabel(p.role || "") : "";
    if(dailyRoleNameInput && !dailyRoleNameInput.value.trim()){
      dailyRoleNameInput.value = profileName || knownPersonNameFromBadge(badge) || "";
    }
    if(dailyRoleCompanyRoleInput) dailyRoleCompanyRoleInput.value = roleLabel;
    if(dailyRoleEffectiveRightsInput){
      dailyRoleEffectiveRightsInput.value = privilegeLabel(combinePrivileges(basePrivilegeFromRole(roleLabel), dailyRoleExtraPrivilegeSelect?.value || "none"));
    }
  }

  async function loadSettingsProfilesUi(){
    try {
      const resp = await fetch("/api/profiles");
      const out = await resp.json();
      const rows = Array.isArray(out.items) ? out.items : [];
      settingsProfilesState = rows;
      if(settingsProfilesTableBody){
        settingsProfilesTableBody.innerHTML = rows.length ? rows.slice().reverse().map(r => `
          <tr>
            <td>${esc(r.name || "-")}</td>
            <td>${esc(r.id_number || "-")}</td>
            <td>${esc(normalizeCompanyRoleLabel(r.role || "-"))}</td>
            <td>${esc(fmtDateLocal(r.created_at_utc || ""))}</td>
          </tr>
        `).join("") : `<tr><td colspan="4">No profiles yet.</td></tr>`;
      }
    } catch {
      if(settingsProfilesTableBody) settingsProfilesTableBody.innerHTML = `<tr><td colspan="4">Failed to load profiles.</td></tr>`;
    }
    refreshDailyRoleDerivedUi();
  }

  async function loadServerSettingsUi(applyTheme = true){
    settingsServerHost && (settingsServerHost.value = location.origin);
    try {
      const resp = await fetch("/api/server-settings");
      const out = await resp.json();
      if(!out.ok) return;
      const s = (out.settings && typeof out.settings === "object") ? out.settings : {};
      serverSettingsState = {
        theme: s.theme || "Default",
        qrgen_base_url: s.qrgen_base_url || "",
      };
      if(applyTheme) applyDashboardTheme(serverSettingsState.theme);
      if(settingsThemeSelect) settingsThemeSelect.value = serverSettingsState.theme;
      if(settingsQrApiBaseUrl) settingsQrApiBaseUrl.value = serverSettingsState.qrgen_base_url;
    } catch {}
    await loadProductsSettingsInfo(false);
  }

  async function loadProductsSettingsInfo(forceRefresh = false){
    if(settingsProductsStatus) settingsProductsStatus.value = forceRefresh ? "Refreshing product items..." : "Loading product cache info...";
    try {
      const url = forceRefresh ? "/api/products?refresh=1" : "/api/products";
      const resp = await fetch(url);
      const out = await resp.json();
      if(!out.ok){
        if(settingsProductsStatus) settingsProductsStatus.value = out.error || "Failed to load products.";
        return;
      }
      const items = Array.isArray(out.items) ? out.items : [];
      if(settingsProductsCount) settingsProductsCount.value = `${items.length} item(s)${out.from_cache ? " (from cache)" : " (fresh)"}`;
      if(settingsProductsUpdated) settingsProductsUpdated.value = out.updated ? fmtDateLocal(out.updated) : "-";
      if(settingsProductsSourceFile) settingsProductsSourceFile.value = out.source_file || "-";
      if(settingsProductsCacheFile) settingsProductsCacheFile.value = out.cache_file || "-";
      if(settingsProductsStatus){
        const base = out.error ? `Loaded with warning: ${out.error}` : "OK";
        settingsProductsStatus.value = base;
      }
      if(forceRefresh){
        productItems = items;
        productsHydrated = items.length > 0;
      }
    } catch (e) {
      if(settingsProductsStatus) settingsProductsStatus.value = `Failed: ${e}`;
    }
  }

  async function saveServerSettingsUi(){
    const payload = {
      theme: (settingsThemeSelect?.value || "Default").trim(),
      qrgen_base_url: (settingsQrApiBaseUrl?.value || "").trim(),
    };
    if(!payload.qrgen_base_url){
      alert("QR Print API Base URL is required.");
      showServerSettingsPage("api");
      return;
    }
    const resp = await fetch("/api/server-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const out = await resp.json();
    if(!out.ok){
      alert(out.error || "Failed to save settings.");
      return;
    }
    serverSettingsState = out.settings || payload;
    applyDashboardTheme(serverSettingsState.theme);
    alert("Server settings applied.");
  }

  function knownPersonNameFromBadge(code){
    const c = String(code || "").trim();
    const map = {
      "3000001": "Charlie Brown",
      "4000001": "Lucy Van Pelt",
    };
    return map[c] || "";
  }

  function displayNameForId(idValue){
    const raw = String(idValue || "").trim();
    if(!raw) return "-";
    const combinedMatch = raw.match(/^\s*[\w-]+\s*-\s*(.+)\s*$/);
    if(combinedMatch && String(combinedMatch[1] || "").trim()){
      return String(combinedMatch[1] || "").trim();
    }
    const code = raw;
    if(!code) return "-";
    const profile = findSettingsProfileById(code);
    if(profile && String(profile.name || "").trim()) return String(profile.name || "").trim();
    const daily = (dailyRolesState && typeof dailyRolesState === "object") ? dailyRolesState[code] : null;
    if(daily && String(daily.name || "").trim()) return String(daily.name || "").trim();
    return knownPersonNameFromBadge(code) || code;
  }

  function fmtLocal(ts){
    if(!ts) return "-";
    const dt = new Date(ts);
    if(Number.isNaN(dt.getTime())) return "-";
    return dt.toLocaleString();
  }

  function compactPair(primary, secondary){
    const p = String(primary || "").trim();
    const s = String(secondary || "").trim();
    if(!p && !s) return { primary: "-", secondary: "" };
    if(!p && s) return { primary: s, secondary: "" };
    if(p && !s) return { primary: p, secondary: "" };
    if(p === s) return { primary: p, secondary: "" };
    return { primary: p, secondary: s };
  }

  function openOperatorDetail(index){
    const row = Array.isArray(operatorDirectoryState) ? operatorDirectoryState[index] : null;
    if(!row || !operatorDetailBody) return;
    const fullName = row.name || "-";
    const badge = row.is_active ? "ACTIVE" : "IDLE";
    const activity = Array.isArray(row.all_activity) ? row.all_activity : [];
    operatorDetailTitle.textContent = fullName;
    operatorDetailSub.textContent = `ID ${row.id_number || '-'} | ${row.role || 'Operator'} | ${badge}`;
    const currentPair = compactPair(row.current_machine_name || row.current_machine_code, row.current_job_name || row.current_job_code);
    const lastPair = compactPair(row.last_machine_name || row.last_machine_code, row.last_job_name || row.last_job_code);
    const activityHtml = activity.length
      ? activity.map(item => `<div class="operator-detail-list-item"><strong>${esc(item.label || 'Activity')}</strong><span>${esc(item.detail || '-')}</span><span>${esc(fmtLocal(item.at_utc))}</span></div>`).join('')
      : '<div class="operator-directory-empty" style="padding:0;">No machine activity recorded yet.</div>';
    operatorDetailBody.innerHTML = `
      <div class="operator-detail-grid">
        <div class="operator-detail-item"><div class="k">Current Machine</div><div class="v">${esc(currentPair.primary)}${currentPair.secondary ? `<br>${esc(currentPair.secondary)}` : ''}</div></div>
        <div class="operator-detail-item"><div class="k">Last Handled</div><div class="v">${esc(lastPair.primary)}${lastPair.secondary ? `<br>${esc(lastPair.secondary)}` : ''}</div></div>
        <div class="operator-detail-item"><div class="k">Last Activity</div><div class="v">${esc(fmtLocal(row.last_activity_at_utc))}</div></div>
      </div>
      <div class="operator-detail-section">
        <h4>Recent Activity</h4>
        <div class="operator-detail-list">${activityHtml}</div>
      </div>
    `;
    operatorDetailOverlay?.classList.add("active");
  }

  function renderOperatorDirectory(items){
    const rows = Array.isArray(items) ? items : [];
    if(!operatorDirectoryGrid) return;
    operatorDirectoryState = rows.slice();
    if(!rows.length){
      operatorDirectoryGrid.innerHTML = '<div class="operator-directory-empty">No operator profiles found yet.</div>';
      return;
    }
    const header = `<div class="operator-directory-row header">
      <div>Operator</div>
      <div>Current Machine</div>
      <div>Last Handled</div>
      <div>Last Activity</div>
      <div>Status</div>
    </div>`;
    const body = rows.map((x, index) => {
      const badge = x.is_active ? '<span class="operator-directory-badge live">ACTIVE</span>' : '<span class="operator-directory-badge">IDLE</span>';
      const currentPair = compactPair(x.current_machine_name || x.current_machine_code, x.current_job_name || x.current_job_code);
      const lastPair = compactPair(x.last_machine_name || x.last_machine_code, x.last_job_name || x.last_job_code);
      const activity = Array.isArray(x.recent_activity) ? x.recent_activity : [];
      const recentPreview = activity.length
        ? activity.map(item => `${item.label || 'Activity'}: ${item.detail || '-'}`).slice(0, 2).join(' | ')
        : 'No machine activity recorded yet.';
      return `<div class="operator-directory-row" data-operator-index="${index}">
        <div class="operator-directory-name">
          <strong>${esc(x.name || '-')}</strong>
          <div class="operator-directory-meta">ID ${esc(x.id_number || '-')} | ${esc(x.role || 'Operator')}</div>
        </div>
        <div class="operator-directory-cell">
          <div class="operator-directory-label">Current Machine</div>
          <div class="operator-directory-value">${esc(currentPair.primary)}</div>
          ${currentPair.secondary ? `<div class="operator-directory-subvalue">${esc(currentPair.secondary)}</div>` : ``}
        </div>
        <div class="operator-directory-cell">
          <div class="operator-directory-label">Last Handled</div>
          <div class="operator-directory-value">${esc(lastPair.primary)}</div>
          ${lastPair.secondary ? `<div class="operator-directory-subvalue">${esc(lastPair.secondary)}</div>` : ``}
        </div>
        <div class="operator-directory-cell">
          <div class="operator-directory-label">Last Activity</div>
          <div class="operator-directory-value">${esc(fmtLocal(x.last_activity_at_utc))}</div>
          <div class="operator-directory-subvalue">${esc(recentPreview)}</div>
        </div>
        <div class="operator-directory-cell">
          <div class="operator-directory-label">Status</div>
          ${badge}
        </div>
      </div>`;
    }).join('');
    operatorDirectoryGrid.innerHTML = header + body;
  }

  async function loadOperatorDirectory(){
    if(!operatorDirectoryGrid) return;
    operatorDirectoryGrid.innerHTML = '<div class="operator-directory-empty">Loading operator activity...</div>';
    const r = await fetch('/api/profiles/operators');
    const out = await r.json().catch(() => ({}));
    if(!r.ok || !out.ok){
      operatorDirectoryGrid.innerHTML = `<div class="operator-directory-empty">${esc(out.error || 'Failed to load operator activity.')}</div>`;
      return;
    }
    renderOperatorDirectory(out.items || []);
  }

  function renderDailyRolesList(items){
    const rows = (items && typeof items === "object") ? Object.entries(items) : [];
    if(!dailyRolesList) return;
    if(!rows.length){
      dailyRolesList.innerHTML = '<div class="placeholder" style="margin:0;">No roles assigned for today yet.</div>';
      return;
    }
    dailyRolesList.innerHTML = `
      <div class="people-role-row head"><div>Name</div><div>Badge</div><div>Base Role</div><div>Privilege</div><div>Updated</div></div>
      ${rows.map(([badge, item]) => `
        <div class="people-role-row">
          <div>${esc(item?.name || "-")}</div>
          <div>${esc(badge)}</div>
          <div>${esc(item?.company_role || "-")}</div>
          <div><span class="people-role-pill">${esc(privilegeLabel(item?.rights || ""))}</span></div>
          <div>${esc(fmtDateLocal(item?.updated_at_utc || ""))}</div>
        </div>
      `).join("")}
    `;
  }

  async function loadDailyRolesUi(){
    try {
      const resp = await fetch("/api/daily-roles");
      const out = await resp.json();
      if(!out.ok) return;
      dailyRolesState = (out.items && typeof out.items === "object") ? out.items : {};
      renderDailyRolesList(dailyRolesState);
    } catch {}
  }

  async function saveDailyRoleUi(){
    const badge = (dailyRoleBadgeInput?.value || "").trim();
    const profile = findSettingsProfileById(badge);
    const company_role = normalizeCompanyRoleLabel(profile?.role || "");
    const extra_privilege = (dailyRoleExtraPrivilegeSelect?.value || "none").trim().toLowerCase();
    const name = (dailyRoleNameInput?.value || "").trim() || String(profile?.name || "").trim() || knownPersonNameFromBadge(badge) || badge;
    if(!badge){
      alert("Scan QR badge first.");
      return;
    }
    if(!company_role){
      alert("Profile not found for this ID. Create the profile first so role-based privileges can be assigned.");
      return;
    }
    const resp = await fetch("/api/daily-roles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ badge_code: badge, name, company_role, extra_privilege }),
    });
    const out = await resp.json();
    if(!out.ok){
      alert(out.error || "Failed to save daily role.");
      return;
    }
    dailyRolesState = out.items || {};
    renderDailyRolesList(dailyRolesState);
    alert("Today role saved.");
  }

  function openQrScanCaptureOverlay(){
    if(!qrScanCaptureOverlay || !qrScanCaptureInput) return;
    qrScanCaptureOverlay.classList.add("active");
    qrScanCaptureInput.value = "";
    setTimeout(() => qrScanCaptureInput.focus(), 0);
  }

  function closeQrScanCaptureOverlay(){
    if(!qrScanCaptureOverlay || !qrScanCaptureInput) return;
    qrScanCaptureOverlay.classList.remove("active");
    qrScanCaptureInput.value = "";
  }

  function scoreProduct(item, q){
    const sku = (item.sku || "").toString().toLowerCase();
    const name = (item.name || "").toString().toLowerCase();
    const text = `${name} ${sku}`;
    const idx = text.indexOf(q);
    if(idx < 0) return 999999;
    return idx * 1000 + text.length;
  }

  function resolveProductIdFromText(text){
    const found = resolveProductFromText(text);
    return found ? String(found.id || "") : "";
  }

  function resolveProductFromText(text){
    const t = (text || "").trim();
    if(!t) return null;
    const exact = productItems.find(
      p =>
        `${p.sku || ""} - ${p.name}` === t
        || `${p.name}` === t
        || `${p.sku || ""}` === t
    );
    if(exact) return exact;
    const low = t.toLowerCase();
    const candidates = productItems
      .filter(p => `${(p.name||"").toString().toLowerCase()} ${(p.sku||"").toString().toLowerCase()}`.includes(low))
      .sort((a,b) => scoreProduct(a, low) - scoreProduct(b, low));
    if(candidates.length) return candidates[0];
    return null;
  }

  function renderProductSuggestions(query = ""){
    const q = (query || "").trim().toLowerCase();
    productSuggestionItems = [...productItems]
      .map(p => ({ ...p, label: `${p.sku || ""} - ${p.name}`.trim() }))
      .filter(p => !q || p.label.toLowerCase().includes(q) || String(p.name || "").toLowerCase().includes(q))
      .sort((a, b) => scoreProduct(a, q) - scoreProduct(b, q))
      .slice(0, PRODUCT_SUGGEST_LIMIT);
    productSuggestionIndex = -1;
    if(!productSuggestionItems.length){
      overlayProductSuggest.classList.remove("active");
      overlayProductSuggest.innerHTML = "";
      return;
    }
    overlayProductSuggest.innerHTML = productSuggestionItems
      .map((p, i) => `<button type="button" class="overlay-suggest-item" data-idx="${i}">${esc(p.label)}</button>`)
      .join("");
    overlayProductSuggest.classList.add("active");
  }

  function pickProductSuggestion(index){
    const item = productSuggestionItems[index];
    if(!item) return;
    overlayProductSelect.value = item.label;
    overlayProductSuggest.classList.remove("active");
    overlayProductSuggest.innerHTML = "";
    productSuggestionItems = [];
    productSuggestionIndex = -1;
  }

  function jobKeyOf(row){
    if(!row || typeof row !== "object") return "";
    return [
      row.finished_at_utc || "",
      row.machine_code || "",
      row.job_code || "",
      row.operator_id || "",
      row.pack_count ?? "",
      row.good_total ?? "",
      row.butal_total ?? "",
      row.reject_total ?? "",
    ].join("|");
  }

  function setOverlayStep(step){
    const isReview = step !== "qr";
    overlayReviewStep.style.display = isReview ? "" : "none";
    overlayQrStep.style.display = isReview ? "none" : "";
    overlayReviewSubmitBtn.style.display = isReview ? "" : "none";
    overlayReviewContinueBtn.style.display = (isReview && overlayReviewMode !== "shift") ? "" : "none";
    overlayBackToReviewBtn.style.display = isReview ? "none" : "";
    overlayGenerateBtn.style.display = "none";
    overlayRequestBtn.style.display = isReview ? "none" : "";
    syncReviewSubslides();
  }

  function syncReviewSubslides(){
    const slides = [reviewSubslide1, reviewSubslide2, reviewSubslide3, reviewSubslide4];
    const total = slides.length;
    reviewSlideIndex = Math.max(0, Math.min(total - 1, Number(reviewSlideIndex || 0)));
    slides.forEach((el, idx) => {
      if(el) el.classList.toggle("active", idx === reviewSlideIndex);
    });
    if(overlayReviewPrevBtn) overlayReviewPrevBtn.disabled = reviewSlideIndex <= 0;
    if(overlayReviewNextBtn) overlayReviewNextBtn.disabled = reviewSlideIndex >= (total - 1);
    if(overlayReviewSlideStatus){
      const labels = overlayReviewMode === "shift"
        ? ["Shift Summary", "Materials / Job API", "Downtime / Team", "Review / Edit"]
        : ["Job Summary", "Raw Mats / Cycle", "Downtime / Team", "Approval"];
      overlayReviewSlideStatus.textContent = `Slide ${reviewSlideIndex + 1} / ${total} - ${labels[reviewSlideIndex] || ""}`;
    }
  }

  function reviewSummaryText(row){
    if(!row) return "";
    return [
      `Finished Job: ${row.job_name || row.job_code || "-"}`,
      `Pack: ${row.pack_count ?? 0}`,
      `Good: ${row.good_total ?? 0}`,
      `Butal: ${row.butal_total ?? 0}`,
      `Reject: ${row.reject_total ?? 0}`,
      `No Shot: ${row.no_shot_total ?? 0}`,
      `Total Good: ${row.total_good ?? ((Number(row.good_total||0)+Number(row.butal_total||0)))}`,
    ].join("\\n");
  }

  function reviewRejectsText(row){
    const rb = (row && typeof row.reject_breakdown === "object" && row.reject_breakdown) || {};
    const keys = Object.keys(rb);
    if(!keys.length) return "No reject details recorded.";
    return keys.sort().map(k => `${k}: ${rb[k]}`).join("\\n");
  }

  function fillDisapproveFields(row){
    editPackCount.value = String(row?.pack_count ?? 0);
    editGoodTotal.value = String(row?.good_total ?? 0);
    editButalTotal.value = String(row?.butal_total ?? 0);
    editRejectTotal.value = String(row?.reject_total ?? 0);
    if(typeof editNoShotTotal !== "undefined" && editNoShotTotal) editNoShotTotal.value = String(row?.no_shot_total ?? 0);
    editTotalGood.value = String(row?.total_good ?? (Number(row?.good_total||0)+Number(row?.butal_total||0)));
    editRejectBreakdown.value = JSON.stringify((row && row.reject_breakdown) || {}, null, 2);
  }

  function qcFromFinishedJob(row){
    const logs = Array.isArray(row?.reject_review_logs) ? row.reject_review_logs : [];
    const qc = logs.find(x => String((x && x.actor_role) || "").toLowerCase() === "qc");
    return (qc && (qc.actor_name || qc.actor_code)) || "-";
  }

  function renderBulletListHtml(text, emptyLabel = "No data."){
    const lines = String(text || "").split(/\\r?\\n/).map(x => x.trim()).filter(Boolean);
    if(!lines.length) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    return `<ul class="review-line-list">${lines.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`;
  }

  function safeJsonPretty(value){
    try {
      return JSON.stringify(value ?? {}, null, 2);
    } catch {
      return String(value ?? "");
    }
  }

  function renderPreformattedHtml(text, emptyLabel = "No data."){
    const raw = String(text || "").trim();
    if(!raw) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    return `<pre class="review-pre">${esc(raw)}</pre>`;
  }

  function renderKeyValueTableHtml(obj, emptyLabel = "No data."){
    const entries = Object.entries((obj && typeof obj === "object") ? obj : {}).filter(([_, v]) => v !== undefined);
    if(!entries.length) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    return `
      <table class="review-kv-table">
        <tbody>
          ${entries.map(([key, value]) => `
            <tr>
              <td class="review-kv-key">${esc(String(key).replace(/_/g, " "))}</td>
              <td class="review-kv-value">${esc(typeof value === "string" ? value : String(value))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function renderShiftGroupedPanelHtml(panel, emptyLabel = "No data."){
    const groups = Array.isArray(panel) ? panel : [];
    if(!groups.length) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    return `
      <div class="review-group-list">
        ${groups.map(group => {
          const title = String(group?.title || "").trim() || "Section";
          const kind = String(group?.kind || "json").trim();
          const content = group?.content;
          let bodyHtml = "";
          if(kind === "table"){
            bodyHtml = renderKeyValueTableHtml(content, emptyLabel);
          } else if(kind === "lines"){
            const text = Array.isArray(content) ? content.join("\n") : String(content || "");
            bodyHtml = renderBulletListHtml(text, emptyLabel);
          } else {
            const raw = safeJsonPretty(content);
            bodyHtml = `<pre class="review-json-block">${esc(raw)}</pre>`;
          }
          return `
            <div class="review-group-card">
              <div class="review-group-head">${esc(title)}</div>
              <div class="review-group-body">${bodyHtml}</div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  function buildShiftPreviewPanels(row){
    const item = (row && typeof row === "object") ? row : {};
    const payload = (item.job_payload && typeof item.job_payload === "object") ? item.job_payload : {};
    const data = (payload.data && typeof payload.data === "object") ? payload.data : {};
    const job = (data.job && typeof data.job === "object") ? data.job : {};
    const jobDetails = (data.job_details && typeof data.job_details === "object") ? data.job_details : {};
    const partials = Array.isArray(data.partials) ? data.partials : [];
    const productParts = Array.isArray(data.product_parts) ? data.product_parts : [];
    const rawLogs = Array.isArray(item.raw_material_logs) ? item.raw_material_logs : [];
    const rawScans = Array.isArray(item.raw_material_scans) ? item.raw_material_scans : [];
    const packHistory = Array.isArray(item.product_pack_history_logs) ? item.product_pack_history_logs : [];
    const rejectReviews = Array.isArray(item.reject_review_logs) ? item.reject_review_logs : [];
    const summary = {
      record_type: item.record_type || "SHIFT_PARTIAL",
      review_status: item.review_status || "-",
      reason: item.reason || "-",
      machine_code: item.machine_code || "-",
      machine_name: item.machine_name || item.machine_code || "-",
      job_code: item.job_code || "-",
      job_name: item.job_name || "-",
      operator_id: item.operator_id || "-",
      operator_name: displayNameForId(item.operator_id || item.operator_name || "-"),
      shift_index: item.shift_index ?? "-",
      started_at_utc: item.started_at_utc || "-",
      ended_at_utc: item.ended_at_utc || item.finished_at_utc || "-",
      pack_count: item.pack_count ?? 0,
      good_total: item.good_total ?? 0,
      butal_total: item.butal_total ?? 0,
      reject_total: item.reject_total ?? 0,
      no_shot_total: item.no_shot_total ?? 0,
      startup_reject_total: item.startup_reject_total ?? 0,
      total_good: item.total_good ?? item.partial_qty ?? 0,
      partial_qty: item.partial_qty ?? item.total_good ?? 0,
      raw_sacks_count: item.raw_sacks_count ?? 0,
      cycle_time_current: item.cycle_time_current || "-",
      cycle_time_shift_avg_seconds: item.cycle_time_shift_avg_seconds ?? "-",
      qty_per_shift_avg_cycle: item.qty_per_shift_avg_cycle ?? "-",
      downtime_reason_code: item.downtime_reason_code || "-",
      downtime_reason_text: item.downtime_reason_text || "-",
      downtime_last_seconds: item.downtime_last_seconds ?? 0,
      maintenance_name: item.maintenance_name || "-",
      supervisor_name: item.supervisor_name || "-",
      linkage_enabled: !!item.linkage_enabled,
      linkage_job_code: item.linkage_job_code || "-",
      linkage_job_name: item.linkage_job_name || "-",
      raw_material_logs_count: rawLogs.length,
      raw_material_scans_count: rawScans.length,
      product_pack_history_count: packHistory.length,
      reject_review_logs_count: rejectReviews.length,
      partials_count: partials.length,
      product_parts_count: productParts.length,
    };
    return {
      summary: [
        { title: "Shift Summary", kind: "table", content: summary },
      ],
      rejects: [
        { title: "Reject Breakdown", kind: "json", content: item.reject_breakdown || {} },
        { title: "Reject Review Logs", kind: "json", content: rejectReviews },
      ],
      rawConsumption: [
        { title: "Raw Material Consumption", kind: "lines", content: rawLogs.map((x, idx) => rawMaterialLine(x, idx)) },
        { title: "Raw Material Scans", kind: "lines", content: rawScans.map((x, idx) => `${idx + 1}. ${String(x || "-")}`) },
        { title: "Product Pack History", kind: "json", content: packHistory },
      ],
      rawCycle: [
        { title: "Job API Job", kind: "json", content: job },
        { title: "Job API Job Details", kind: "json", content: jobDetails },
        { title: "Job API Product Parts", kind: "json", content: productParts },
        { title: "Job API Partials", kind: "json", content: partials },
      ],
      downtime: [
        {
          title: "Downtime",
          kind: "table",
          content: {
            downtime_reason_code: item.downtime_reason_code || "-",
            downtime_reason_text: item.downtime_reason_text || "-",
            downtime_last_seconds: item.downtime_last_seconds ?? 0,
            downtime_active: !!item.downtime_active,
            maintenance_name: item.maintenance_name || "-",
            supervisor_name: item.supervisor_name || "-",
          },
        },
      ],
      people: [
        {
          title: "People",
          kind: "table",
          content: {
            operator_name: displayNameForId(item.operator_id || item.operator_name || "-"),
            operator_id: item.operator_id || "-",
            maintenance_name: item.maintenance_name || "-",
            supervisor_name: item.supervisor_name || "-",
            qc_name: qcFromFinishedJob(item),
            no_shot_total: item.no_shot_total ?? 0,
            startup_reject_total: item.startup_reject_total ?? 0,
          },
        },
        { title: "Full Job API Payload", kind: "json", content: payload },
      ],
    };
  }

  function renderSummaryMetricsHtml(row){
    const r = row || {};
    const totalGood = Number(r.total_good ?? ((Number(r.good_total||0) + Number(r.butal_total||0))));
    return `
      <span>Finished Job:</span>
      <span>Pack: ${esc(r.pack_count ?? 0)}</span>
      <span class="dot">•</span>
      <span>Good: ${esc(r.good_total ?? 0)}</span>
      <span class="dot">•</span>
      <span>Butal: ${esc(r.butal_total ?? 0)}</span>
      <span class="dot">•</span>
      <span>Reject: <span class="reject-emph">${esc(r.reject_total ?? 0)}</span></span>
      <span>No Shot: <span class="reject-emph">${esc(r.no_shot_total ?? 0)}</span></span>
      <span class="dot">•</span>
      <span>Total Good: ${esc(totalGood)}</span>
    `;
  }

  function isShiftPartialRecord(row){
    return String(row?.record_type || "").toUpperCase() === "SHIFT_PARTIAL";
  }

  function isApprovedShiftRecord(row){
    return isShiftPartialRecord(row) && String(row?.review_status || "").toUpperCase() === "APPROVED";
  }

  function renderFinishedShiftQueue(rows){
    const items = Array.isArray(rows) ? rows : [];
    if(!finishedShiftQueueList) return;
    if(!items.length){
      finishedShiftQueueList.innerHTML = '<div class="placeholder">No finished shifts yet.</div>';
      return;
    }
    const sorted = [...items].reverse();
    finishedShiftQueueList.innerHTML = sorted.map((r, idx) => {
      const machineCode = String(r.machine_code || "").trim();
      const machineName = r.machine_name || MACHINE_NAME_MAP[machineCode] || machineCode || "-";
      const rawLogs = Array.isArray(r.raw_material_logs) ? r.raw_material_logs : [];
      const rawText = rawLogs.length
        ? rawLogs.map((x, rowIdx) => rawMaterialLine(x, rowIdx)).join("\\n")
        : "No raw materials scanned.";
      return `
        <div class="finished-item">
          <div class="finished-head">
            <h4>${esc(r.job_name || r.job_code || "Shift")} - ${esc(machineName)}</h4>
            <span class="finished-badge">${esc(r.review_status || "PENDING")}</span>
          </div>
          <div class="finished-grid">
            <div><strong>Shift End:</strong> ${esc(fmtDateLocal(r.finished_at_utc || r.ended_at_utc || ""))}</div>
            <div><strong>Operator:</strong> ${esc(displayNameForId(r.operator_id || "-"))}</div>
            <div><strong>Pack:</strong> ${esc(r.pack_count ?? 0)}</div>
            <div><strong>Total Good:</strong> ${esc(r.total_good ?? r.partial_qty ?? 0)}</div>
            <div><strong>Reject:</strong> ${esc(r.reject_total ?? 0)}</div>
            <div><strong>Downtime:</strong> ${esc(fmtDowntimeSeconds(r.downtime_last_seconds))}</div>
          </div>
          <div class="raw-list">${esc(rawText)}</div>
          <div class="finished-actions">
            <button class="approve-print-btn shift-review-btn" data-row-index="${idx}" type="button">Review Shift</button>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderFinishedShiftJobProgress(rows){
    const approved = (Array.isArray(rows) ? rows : []).filter(isApprovedShiftRecord);
    if(!finishedShiftJobProgress) return;
    if(!approved.length){
      finishedShiftJobProgress.innerHTML = '<div class="placeholder">No approved shift partials yet.</div>';
      return;
    }
    const grouped = new Map();
    approved.forEach(row => {
      const key = String(row.job_code || row.job_name || "").trim() || "UNKNOWN";
      if(!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(row);
    });
    const cards = Array.from(grouped.entries()).map(([key, list]) => {
      const first = list[0] || {};
      const approvedQty = list.reduce((sum, row) => sum + Number(row.partial_qty || row.total_good || 0), 0);
      const apiPartials = Array.isArray(first?.job_payload?.data?.partials) ? first.job_payload.data.partials : [];
      const apiPartialQty = apiPartials.reduce((sum, row) => sum + Number(row?.partial_qty || 0), 0);
      const targetQty = Number(first?.job_payload?.data?.job?.approve_qty || first?.job_payload?.data?.job?.request_qty || 0);
      const producedQty = approvedQty + apiPartialQty;
      const remainingQty = Math.max(0, targetQty - producedQty);
      const lines = list
        .slice()
        .sort((a, b) => String(a.finished_at_utc || a.ended_at_utc || "").localeCompare(String(b.finished_at_utc || b.ended_at_utc || "")))
        .map((row, idx) => `${idx + 1}. ${fmtDateLocal(row.finished_at_utc || row.ended_at_utc || "")} | Qty ${row.partial_qty || row.total_good || 0} | Reject ${row.reject_total || 0} | No Shot ${row.no_shot_total || 0} | Downtime ${fmtDowntimeSeconds(row.downtime_last_seconds)}`);
      return `
        <div class="finished-item">
          <div class="finished-head">
            <h4>${esc(first.job_name || first.job_code || key)}</h4>
            <span class="finished-badge">APPROVED PARTIALS</span>
          </div>
          <div class="finished-grid">
            <div><strong>Job Code:</strong> ${esc(first.job_code || key)}</div>
            <div><strong>Approved Shifts:</strong> ${esc(list.length)}</div>
            <div><strong>API Partials:</strong> ${esc(apiPartialQty)}</div>
            <div><strong>Approved Shift Qty:</strong> ${esc(approvedQty)}</div>
            <div><strong>Produced:</strong> ${esc(producedQty)}</div>
            <div><strong>Remaining:</strong> ${esc(remainingQty)}</div>
          </div>
          <div class="raw-list">${esc(lines.join("\\n"))}</div>
        </div>
      `;
    });
    finishedShiftJobProgress.innerHTML = cards.join("");
  }

  function applyGeneratedQrPlanEntry(entry){
    const item = entry && typeof entry === "object" ? entry : {};
    const poRequired = Boolean(item.po_required);
    const stagePo = String(item.po_number || "").trim();
    const payloadText = (poRequired && !stagePo) ? "" : String(item.qr_payload || item.payload || "").trim();
    const parsed = item.parsed && typeof item.parsed === "object" ? item.parsed : {};
    if(overlayQrStageLabel) overlayQrStageLabel.value = String(item.stage_label || "2 / 2 - QR Print");
    overlayQrPayload.value = payloadText || (poRequired ? "PO Number required for Butal QR. Enter PO Number, then Generate QR Payload." : "");
    overlayQty.value = parsed.qty || item.qty || "";
    overlayIndex.value = parsed.index || item.index || "";
    overlayTotal.value = parsed.total || item.total || "";
    overlayLotNumber.value = parsed.lot_number || item.lot_number || "";
    generatedQrState.payload = overlayQrPayload.value || "";
    generatedQrState.qty = overlayQty.value || "";
    generatedQrState.index = overlayIndex.value || "";
    generatedQrState.total = overlayTotal.value || "";
    generatedQrState.lotNumber = overlayLotNumber.value || "";
    generatedQrState.stageLabel = String(item.stage_label || "");
    generatedQrState.stageKind = String(item.stage_kind || "");
    if(overlayPoNumberRow){
      overlayPoNumberRow.style.display = poRequired ? "" : "none";
    }
    if(overlayPoNumber){
      overlayPoNumber.value = stagePo;
      overlayPoNumber.placeholder = poRequired ? "Enter PO Number..." : "Not required for raw excess";
    }
    if(overlayProductSelect){
      const sku = String(item.product_sku || "").trim();
      const name = String(item.product_name || "").trim();
      overlayProductSelect.value = (sku && name) ? `${sku} - ${name}` : (name || sku || overlayProductSelect.value || "");
    }
  }

  async function refreshQrStagePayload(){
    if(!overlayReviewSavedApproved){
      overlayQrPayload.value = "Review approval is required before generating QR.";
      return;
    }
    const productId = resolveProductIdFromText(overlayProductSelect.value || "");
    const poNumber = (overlayPoNumber.value || "").trim();
    const needsPo = generatedQrState.stageKind === "BUTAL";
    if(needsPo && !poNumber){
      overlayQrPayload.value = "Enter PO Number for Butal.";
      return;
    }
    const resp = await fetch("/api/raw-material-qr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: productId,
        po_number: poNumber,
        finished_job: activeJobRow || {},
        stage_index: generatedQrState.plan && generatedQrState.plan.length ? generatedQrState.planIndex : 0,
      }),
    });
    const out = await resp.json();
    const plan = Array.isArray(out.qr_plan) ? out.qr_plan : [];
    const payloadText = out.qr_payload || out.error || "Failed to generate.";
    const existingRequests = Array.isArray(generatedQrState.printRequests) ? generatedQrState.printRequests : [];
    generatedQrState = {
      jobKey: jobKeyOf(activeJobRow),
      payload: payloadText,
      qty: "",
      index: "",
      total: "",
      lotNumber: "",
      stageLabel: String(out.stage_label || ""),
      stageKind: "",
      plan: plan,
      planIndex: Number(out.selected_stage_index || 0),
      printRequests: existingRequests,
    };
    if(plan.length){
      applyGeneratedQrPlanEntry(plan[generatedQrState.planIndex] || plan[0]);
    } else {
      overlayQrPayload.value = payloadText;
      const parsed = out.parsed || {};
      overlayQty.value = parsed.qty || "";
      overlayIndex.value = parsed.index || "";
      overlayTotal.value = parsed.total || "";
      overlayLotNumber.value = parsed.lot_number || "";
      if(overlayQrStageLabel) overlayQrStageLabel.value = String(out.stage_label || "1 / 1 - QR Print");
      generatedQrState.qty = overlayQty.value || "";
      generatedQrState.index = overlayIndex.value || "";
      generatedQrState.total = overlayTotal.value || "";
      generatedQrState.lotNumber = overlayLotNumber.value || "";
      generatedQrState.stageKind = "DEFAULT";
    }
  }

  function renderFinishedJobs(rows){
    const allItems = Array.isArray(rows) ? rows : [];
    const shiftItems = allItems.filter(isShiftPartialRecord);
    const finalItems = allItems.filter(r => !isShiftPartialRecord(r));
    finishedShiftState = shiftItems;
    renderFinishedShiftQueue(shiftItems);
    renderFinishedShiftJobProgress(shiftItems);
    const items = finalItems;
    if(finishedJobsInteractionLock){
      pendingFinishedJobsRows = items;
      finishedJobsState = items;
      return;
    }
    pendingFinishedJobsRows = null;
    finishedJobsState = items;
    if(!items.length){
      finishedJobsList.innerHTML = '<div class="placeholder">No finished jobs yet.</div>';
      return;
    }
    const sorted = [...items].reverse();
    finishedJobsList.innerHTML = sorted.map((r, idx) => {
      const machineCode = String(r.machine_code || "").trim();
      const machineName = (r.machine_name || MACHINE_NAME_MAP[machineCode] || machineCode || "-");
      const rawLogs = Array.isArray(r.raw_material_logs) ? r.raw_material_logs : [];
      const relatedApprovedShifts = shiftItems.filter(x => isApprovedShiftRecord(x) && String(x.job_code || "") === String(r.job_code || ""));
      const rawText = rawLogs.length
        ? rawLogs.map((x, idx) => rawMaterialLine(x, idx)).join("\\n")
        : "No raw materials scanned.";
      const partialSummaryText = relatedApprovedShifts.length
        ? relatedApprovedShifts.map((x, rowIdx) => `${rowIdx + 1}. ${fmtDateLocal(x.finished_at_utc || x.ended_at_utc || "")} | Qty ${x.partial_qty || x.total_good || 0} | Reject ${x.reject_total || 0} | No Shot ${x.no_shot_total || 0} | Downtime ${fmtDowntimeSeconds(x.downtime_last_seconds)}`).join("\\n")
        : "No approved shift partials linked to this job yet.";
      const linkageRole = String(r.linkage_role || "").toUpperCase();
      const linkageTotal = Number(r.linkage_group_total_jobs || 0);
      const linkageBadge = linkageRole ? `<span class="linkage-pill">${esc(linkageRole)}${linkageTotal ? ` (${linkageTotal})` : ""}</span>` : "";
      const linkageNote = String(r.linkage_note || "").trim();
      return `
        <div class="finished-item">
          <div class="finished-head">
            <h4>${esc(r.job_name || r.job_code || "Finished Job")} - ${esc(machineName)} ${linkageBadge}</h4>
            <span class="finished-badge">FINISHED</span>
          </div>
          <div class="finished-grid">
            <div><strong>Finished UTC:</strong> ${esc(r.finished_at_utc || "-")}</div>
            <div><strong>Operator:</strong> ${esc(displayNameForId(r.operator_id || "-"))}</div>
            <div><strong>Pack Count:</strong> ${esc(r.pack_count ?? 0)}</div>
            <div><strong>Good:</strong> ${esc(r.good_total ?? 0)}</div>
            <div><strong>Butal:</strong> ${esc(r.butal_total ?? 0)}</div>
            <div><strong>Reject:</strong> ${esc(r.reject_total ?? 0)}</div>
            <div><strong>No Shot:</strong> ${esc(r.no_shot_total ?? 0)}</div>
            <div><strong>Total Good:</strong> ${esc(r.total_good ?? 0)}</div>
            <div><strong>Startup Reject:</strong> ${esc(r.startup_reject_total ?? 0)}</div>
            <div><strong>Raw Sacks:</strong> ${esc(r.raw_sacks_count ?? 0)}</div>
            <div><strong>Approved Shifts:</strong> ${esc(relatedApprovedShifts.length)}</div>
            <div><strong>Approved Shift Qty:</strong> ${esc(relatedApprovedShifts.reduce((sum, x) => sum + Number(x.partial_qty || x.total_good || 0), 0))}</div>
          </div>
          <div class="raw-list">${esc(rawText)}</div>
          <div class="raw-list">${esc(partialSummaryText)}</div>
          ${linkageNote ? `<div class="finished-linkage-note"><strong>Link Info:</strong> ${esc(linkageNote)}</div>` : ""}
          <div class="finished-actions">
            <button class="approve-print-btn" data-row-index="${idx}" type="button">Approve and Print QR</button>
          </div>
        </div>
      `;
    }).join("");
  }

  function archivedRowToMachineSessionLike(row){
    return {
      client_id: row.client_id || "",
      machine_code: row.machine_code || "",
      machine_name: row.machine_name || row.machine_code || "",
      job_code: row.job_code || "",
      job_name: row.job_name || "",
      operator_id: row.operator_id || "",
      pack_total: row.pack_count || 0,
      good_total: row.good_total || 0,
      butal_total: row.butal_total || 0,
      reject_total: row.reject_total || 0,
      no_shot_total: row.no_shot_total || 0,
      reject_breakdown: row.reject_breakdown || {},
      raw_sacks_count: row.raw_sacks_count || 0,
      raw_material_scans: row.raw_material_scans || [],
      raw_material_logs: row.raw_material_logs || [],
      startup_reject_total: row.startup_reject_total || 0,
      downtime_reason_code: row.downtime_reason_code || "",
      downtime_reason_text: row.downtime_reason_text || "",
      downtime_last_seconds: row.downtime_last_seconds,
      cycle_time_current: row.cycle_time_current || "",
      maintenance_name: row.maintenance_name || "",
      supervisor_name: row.supervisor_name || "",
      reject_review_logs: row.reject_review_logs || [],
      job_payload: row.job_payload || {},
      last_seen_utc: row.printed_at_utc || row.finished_at_utc || "",
      last_event: `ARCHIVED${row.printed_at_utc ? " / PRINTED" : ""}`,
      downtime_active: false,
    };
  }

  function renderArchivedJobs(rows){
    const items = Array.isArray(rows) ? rows : [];
    archivedJobsState = items;
    if(!archivedJobsTableWrap) return;
    if(!items.length){
      archivedJobsTableWrap.innerHTML = '<div class="placeholder">No archived jobs yet.</div>';
      return;
    }
    const sorted = [...items].reverse();
    archivedJobsTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Machine</th>
            <th>Job</th>
            <th>Operator</th>
            <th>Finished</th>
            <th>Printed</th>
            <th>Status</th>
            <th>Approved / Changed</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map((r, idx) => {
            const machineCode = String(r.machine_code || "").trim();
            const machineName = r.machine_name || MACHINE_NAME_MAP[machineCode] || machineCode || "-";
            const actor = r.approved_by || r.changed_by || "-";
            const actorRole = r.approved_by_role || r.changed_by_role || "";
            const linkageRole = String(r.linkage_role || "").toUpperCase();
            const linkageTotal = Number(r.linkage_group_total_jobs || 0);
            const linkageNote = String(r.linkage_note || "").trim();
            return `
              <tr>
                <td>${esc(machineName)}<br><span class="muted">${esc(machineCode)}</span></td>
                <td>${esc(r.job_name || r.job_code || "-")}${linkageRole ? ` <span class="linkage-pill">${esc(linkageRole)}${linkageTotal ? ` (${linkageTotal})` : ""}</span>` : ""}<br><span class="muted">${esc(r.job_code || "-")}${linkageNote ? ` | ${esc(linkageNote)}` : ""}</span></td>
                <td>${esc(displayNameForId(r.operator_id || "-"))}</td>
                <td>${esc(fmtDateLocal(r.finished_at_utc || ""))}</td>
                <td>${esc(fmtDateLocal(r.printed_at_utc || r.archived_at_utc || ""))}</td>
                <td>${esc(r.review_status || "ARCHIVED")}</td>
                <td>${esc(actor)}${actorRole ? `<br><span class="muted">${esc(actorRole)}</span>` : ""}</td>
                <td><div class="table-actions"><button class="mini-btn primary archived-view-btn" data-row-index="${idx}" type="button">View</button></div></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function machineStatusArchiveDurationLabel(r){
    const ended = String(r?.ended_at_utc || "").trim();
    const dur = Number(r?.duration_seconds);
    if(Number.isFinite(dur) && dur >= 0) return fmtDowntimeSeconds(dur);
    const startedIso = String(r?.started_at_utc || "").trim();
    const startedMs = startedIso ? new Date(startedIso).getTime() : NaN;
    if(!ended && Number.isFinite(startedMs)){
      const liveSec = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
      return `${fmtDowntimeSeconds(liveSec)} (ongoing)`;
    }
    return "-";
  }

  function renderMachineStatusArchive(rows){
    const items = Array.isArray(rows) ? rows : [];
    machineStatusArchiveState = items;
    if(!machineStatusArchiveTableWrap) return;
    if(!items.length){
      machineStatusArchiveTableWrap.innerHTML = '<div class="placeholder">No machine status archive logs yet.</div>';
      return;
    }
    const sorted = [...items].reverse();
    machineStatusArchiveTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Machine</th>
            <th>Status</th>
            <th>Reason</th>
            <th>Set By</th>
            <th>Start</th>
            <th>End</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map((r) => {
            const machineCode = String(r.machine_code || "").trim();
            const machineName = r.machine_name || MACHINE_NAME_MAP[machineCode] || machineCode || "-";
            const by = `${r.set_by_name || "-"}${r.set_by_role ? ` (${r.set_by_role})` : ""}`;
            return `
              <tr>
                <td>${esc(machineName)}<br><span class="muted">${esc(machineCode)}</span></td>
                <td>${esc(r.status || "-")}</td>
                <td>${esc(r.reason || "-")}</td>
                <td>${esc(by)}<br><span class="muted">${esc(r.set_by_badge || "-")}</span></td>
                <td>${esc(fmtDateLocal(r.started_at_utc || ""))}</td>
                <td>${esc(fmtDateLocal(r.ended_at_utc || ""))}</td>
                <td>${esc(machineStatusArchiveDurationLabel(r))}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function buildDowntimeArchiveRows(finishedRows, archivedRows){
    const all = [...(Array.isArray(finishedRows) ? finishedRows : []), ...(Array.isArray(archivedRows) ? archivedRows : [])];
    const seen = new Set();
    const out = [];
    for(const r of all){
      if(!r || typeof r !== "object") continue;
      const sec = Number(r.downtime_last_seconds);
      const active = Boolean(r.downtime_active);
      const reasonCode = String(r.downtime_reason_code || "").trim();
      const reasonText = String(r.downtime_reason_text || "").trim();
      if(!(Number.isFinite(sec) && sec > 0) && !active) continue;
      if(!reasonCode && !reasonText && !(Number.isFinite(sec) && sec > 0)) continue;
      const key = [
        String(r.machine_code || ""),
        String(r.job_code || ""),
        String(r.finished_at_utc || r.printed_at_utc || r.archived_at_utc || ""),
        String(reasonCode),
        String(reasonText),
        String(Number.isFinite(sec) ? sec : ""),
      ].join("|");
      if(seen.has(key)) continue;
      seen.add(key);
      out.push({
        machine_code: String(r.machine_code || "").trim(),
        machine_name: String(r.machine_name || "").trim(),
        job_code: String(r.job_code || "").trim(),
        job_name: String(r.job_name || "").trim(),
        operator_id: String(r.operator_id || "").trim(),
        maintenance_name: String(r.maintenance_name || "").trim(),
        reason_code: reasonCode,
        reason_text: reasonText,
        duration_seconds: Number.isFinite(sec) ? Math.max(0, Math.floor(sec)) : null,
        at_utc: String(r.finished_at_utc || r.printed_at_utc || r.archived_at_utc || r.last_seen_utc || "").trim(),
        source: String(r.printed_at_utc || r.archived_at_utc ? "Archived Job" : "Finished Job"),
      });
    }
    return out.sort((a, b) => {
      const ta = new Date(a.at_utc || 0).getTime() || 0;
      const tb = new Date(b.at_utc || 0).getTime() || 0;
      return tb - ta;
    });
  }

  function renderDowntimeArchive(finishedRows, archivedRows){
    if(!downtimeArchiveTableWrap) return;
    const rows = buildDowntimeArchiveRows(finishedRows, archivedRows);
    if(!rows.length){
      downtimeArchiveTableWrap.innerHTML = '<div class="placeholder">No downtime archive rows yet.</div>';
      return;
    }
    downtimeArchiveTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Machine</th>
            <th>Job</th>
            <th>Operator</th>
            <th>Reason</th>
            <th>Duration</th>
            <th>Recorded</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((r) => {
            const machineName = r.machine_name || MACHINE_NAME_MAP[r.machine_code] || r.machine_code || "-";
            const reason = [r.reason_code, r.reason_text].filter(Boolean).join(" - ") || "-";
            return `
              <tr>
                <td>${esc(machineName)}<br><span class="muted">${esc(r.machine_code || "-")}</span></td>
                <td>${esc(r.job_name || r.job_code || "-")}<br><span class="muted">${esc(r.job_code || "-")}</span></td>
                <td>${esc(displayNameForId(r.operator_id || "-"))}</td>
                <td>${esc(reason)}</td>
                <td>${esc(fmtDowntimeSeconds(r.duration_seconds))}</td>
                <td>${esc(fmtDateLocal(r.at_utc || ""))}</td>
                <td>${esc(r.source || "-")}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function maintenancePeopleFromState(state){
    const byBadge = new Map();
    const profiles = Array.isArray(state?.maintenance_profiles) ? state.maintenance_profiles : [];
    profiles.forEach((row) => {
      const badge = String(row?.id_number || "").trim();
      if(!badge) return;
      byBadge.set(badge, {
        badge,
        name: String(row?.name || badge).trim() || badge,
        source: "profile",
      });
    });
    const dailyRoles = (state?.daily_roles && typeof state.daily_roles === "object") ? state.daily_roles : {};
    for(const [badge, row] of Object.entries(dailyRoles)){
      const rights = String(row?.rights || "").trim().toLowerCase();
      const companyRole = String(row?.company_role || "").trim().toLowerCase();
      if(rights !== "maintenance" && companyRole !== "maintenance") continue;
      const existing = byBadge.get(badge) || {};
      byBadge.set(badge, {
        badge,
        name: String(row?.name || existing.name || badge).trim() || badge,
        source: existing.source ? "profile+daily" : "daily",
      });
    }
    return Array.from(byBadge.values()).sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  }

  function maintenanceMachineDurationSeconds(session){
    const active = Boolean(session?.downtime_active);
    const startDowntime = Number(session?.downtime_started_at || 0);
    const startWait = Number(session?.downtime_wait_started_at || 0);
    if(active && startDowntime > 0){
      return Math.max(0, Math.floor((Date.now() / 1000) - startDowntime));
    }
    if(active){
      return Math.max(0, Math.floor(Number(session?.downtime_last_seconds || 0)));
    }
    if(startWait > 0){
      return Math.max(0, Math.floor((Date.now() / 1000) - startWait));
    }
    return Math.max(0, Math.floor(Number(session?.downtime_wait_last_seconds || 0)));
  }

  function renderMaintenanceMachineCard(s){
    const machineName = s.machine_name || MACHINE_NAME_MAP[s.machine_code] || s.machine_code || "-";
    const active = Boolean(s.downtime_active);
    const duration = maintenanceMachineDurationSeconds(s);
    return `
      <div class="maintenance-machine ${active ? "busy" : "waiting"}">
        <div class="maintenance-machine-title">${esc(machineName)}: ${esc(active ? (s.downtime_reason_text || "Fixing") : "Waiting")}</div>
        <div class="maintenance-machine-time">${esc(fmtDowntimeSeconds(duration))}</div>
      </div>
    `;
  }

  function maintenanceDateLabel(iso){
    const date = iso ? new Date(iso) : new Date();
    if(Number.isNaN(date.getTime())) return "Accurate current date: -";
    return "Accurate current date: " + date.toLocaleString("en-US", {
      weekday: "short",
      month: "short",
      day: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }

  function buildMaintenancePerfMap(state){
    const allRows = buildDowntimeArchiveRows(state?.finished_jobs || [], state?.archived_jobs || []);
    const perfMap = new Map();
    allRows.forEach((row) => {
      const maintenanceName = String(row.maintenance_name || "").trim();
      if(!maintenanceName || !Number.isFinite(Number(row.duration_seconds))) return;
      const stat = perfMap.get(maintenanceName) || { name: maintenanceName, count: 0, total: 0, fastest: null, latest_utc: "" };
      const sec = Math.max(0, Math.floor(Number(row.duration_seconds || 0)));
      stat.count += 1;
      stat.total += sec;
      stat.fastest = stat.fastest === null ? sec : Math.min(stat.fastest, sec);
      if(String(row.at_utc || "").trim() > String(stat.latest_utc || "").trim()) stat.latest_utc = String(row.at_utc || "").trim();
      perfMap.set(maintenanceName, stat);
    });
    return perfMap;
  }

  function activeMaintenanceMachineRows(sessions){
    return (Array.isArray(sessions) ? sessions : []).filter((s) => {
      if(!s || typeof s !== "object") return false;
      const hasDowntime = Boolean(s.downtime_active);
      const hasWait = Number(s.downtime_wait_started_at || 0) > 0 || Number(s.downtime_wait_last_seconds || 0) > 0;
      const hasReason = String(s.downtime_reason_code || s.downtime_reason_text || "").trim() !== "";
      return hasReason && (hasDowntime || hasWait);
    });
  }

  function renderMaintenanceTab(state){
    const sessions = Array.isArray(state?.sessions) ? state.sessions : [];
    const maintenancePeople = maintenancePeopleFromState(state);
    const activeMachines = activeMaintenanceMachineRows(sessions);
    const perfMap = buildMaintenancePerfMap(state);
    const assignments = new Map();
    activeMachines.forEach((s) => {
      const name = String(s.maintenance_name || "").trim();
      if(!name) return;
      const rows = assignments.get(name) || [];
      rows.push(s);
      assignments.set(name, rows);
    });
    const busyCount = assignments.size;
    const availableCount = Math.max(0, maintenancePeople.length - busyCount);
    const waitingCount = activeMachines.filter(s => !String(s.maintenance_name || "").trim()).length;
    const activeFixCount = activeMachines.filter(s => Boolean(s.downtime_active)).length;
    if(maintenanceCurrentDate){
      maintenanceCurrentDate.textContent = maintenanceDateLabel(state?.server_time_utc || "");
    }

    if(maintenanceSummary){
      maintenanceSummary.innerHTML = `
        <div class="maintenance-metric blue"><div class="icon"></div><div><div class="k">Maintenance Today</div><div class="v">${esc(maintenancePeople.length)}</div><div class="s">Maintenance today&apos;s roles.</div></div></div>
        <div class="maintenance-metric green"><div class="icon"></div><div><div class="k">Available Team</div><div class="v">${esc(availableCount)}</div><div class="s">Metric card for available team.</div></div></div>
        <div class="maintenance-metric amber"><div class="icon"></div><div><div class="k">Active Repairs</div><div class="v">${esc(activeFixCount)}</div><div class="s">Active repairs in motion.</div></div></div>
        <div class="maintenance-metric red"><div class="icon"></div><div><div class="k">Machines Waiting</div><div class="v">${esc(waitingCount)}</div><div class="s">Machines waiting assigned.</div></div></div>
      `;
    }

    if(maintenancePeopleList){
      if(!maintenancePeople.length){
        maintenancePeopleList.innerHTML = '<div class="placeholder">No maintenance profiles yet.</div>';
      } else {
        const unassigned = activeMachines.filter(s => !String(s.maintenance_name || "").trim());
        maintenancePeopleList.innerHTML = maintenancePeople.map((person) => {
          const jobs = assignments.get(person.name) || [];
          const busy = jobs.length > 0;
          const perf = perfMap.get(person.name) || { count: 0, total: 0, fastest: null };
          const avgRepair = perf.count ? fmtDowntimeSeconds(Math.round(perf.total / Math.max(1, perf.count))) : "00:00:00";
          const waitFreq = perf.count ? `${Math.round((jobs.length / Math.max(1, perf.count)) * 100)}%` : "0%";
          const avgWait = jobs.length ? fmtDowntimeSeconds(Math.round(jobs.reduce((sum, row) => sum + maintenanceMachineDurationSeconds(row), 0) / jobs.length)) : "00:00:00";
          return `
            <div class="maintenance-person ${busy ? "busy" : "available"}">
              <div class="maintenance-avatar-wrap">
                <div class="maintenance-avatar" aria-hidden="true"></div>
              </div>
              <div class="maintenance-person-main">
                <div class="maintenance-person-head">
                  <div>
                    <div class="title">${esc(person.name)}</div>
                    <div class="meta">Badge: ${esc(person.badge || "-")}</div>
                  </div>
                  <span class="maintenance-badge ${busy ? "busy" : "available"}">${busy ? "Fixing" : "Available"}</span>
                </div>
                <div class="submeta">${jobs.length ? `${jobs.length} active machine assignment${jobs.length > 1 ? "s" : ""}.` : "No active machines."}<br>${jobs.length ? "Ready to continue assigned work." : "Ready for new call."}</div>
                <div class="maintenance-machine-grid">
                  ${jobs.length ? jobs.map(renderMaintenanceMachineCard).join("") : '<div class="submeta">No active machines.</div>'}
                </div>
              </div>
              <div class="maintenance-stats">
                <div class="maintenance-stats-title">Lifetime Stats</div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">◷</span><span>Avg. Repair: ${esc(avgRepair)}</span></div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">⟳</span><span>Wait Freq: ${esc(waitFreq)}</span></div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">◷</span><span>Avg. Wait: ${esc(avgWait)}</span></div>
              </div>
            </div>
          `;
        }).join("") + (
          unassigned.length ? `
            <div class="maintenance-person">
              <div class="maintenance-avatar-wrap">
                <div class="maintenance-avatar" aria-hidden="true"></div>
              </div>
              <div class="maintenance-person-main">
                <div class="maintenance-person-head">
                  <div>
                    <div class="title">Unassigned Maintenance Calls</div>
                    <div class="meta">Badge: -</div>
                  </div>
                  <span class="maintenance-badge waiting">Waiting</span>
                </div>
                <div class="submeta">Machines waiting for maintenance assignment.</div>
                <div class="maintenance-machine-grid">
                  ${unassigned.map(renderMaintenanceMachineCard).join("")}
                </div>
              </div>
              <div class="maintenance-stats">
                <div class="maintenance-stats-title">Queue Stats</div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">◷</span><span>Waiting jobs: ${esc(unassigned.length)}</span></div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">⚙</span><span>Active repairs: ${esc(activeFixCount)}</span></div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">△</span><span>Needs assignment now.</span></div>
              </div>
            </div>
          ` : ""
        );
      }
    }

    if(maintenancePerformanceTableWrap){
      const perfRows = Array.from(perfMap.values()).sort((a, b) => (a.total / Math.max(1, a.count)) - (b.total / Math.max(1, b.count)));
      if(!perfRows.length){
        maintenancePerformanceTableWrap.innerHTML = '<div class="placeholder">No downtime records with maintenance names yet.</div>';
      } else {
        maintenancePerformanceTableWrap.innerHTML = `
          <table class="data-table">
            <thead>
              <tr>
                <th>Maintenance</th>
                <th>Resolved Downtimes</th>
                <th>Average Repair Time</th>
                <th>Fastest Repair</th>
                <th>Last Recorded</th>
              </tr>
            </thead>
            <tbody>
              ${perfRows.map((row) => `
                <tr>
                  <td>${esc(row.name)}</td>
                  <td>${esc(row.count)}</td>
                  <td>${esc(fmtDowntimeSeconds(Math.round(row.total / Math.max(1, row.count))))}</td>
                  <td>${esc(fmtDowntimeSeconds(row.fastest))}</td>
                  <td>${esc(fmtDateLocal(row.latest_utc || ""))}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        `;
      }
    }
  }

  function queueStatusBadge(status){
    const raw = String(status || "").trim();
    const css = raw.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "running";
    return `<span class="queue-status-badge ${esc(css)}">${esc(raw || "RUNNING")}</span>`;
  }

  function renderJobQueue(rows){
    if(!jobQueueTableWrap) return;
    const list = Array.isArray(rows) ? rows : [];
    const runningRows = list.filter(r => {
      const status = String(r?.status || "").trim();
      return status !== "DONE" && status !== "DISCONNECTED";
    });
    const disconnectedRows = list.filter(r => String(r?.status || "").trim() === "DISCONNECTED");
    const remainingTotal = runningRows.reduce((sum, r) => sum + Number(r?.remaining_qty || 0), 0);

    if(jobQueueSummary){
      jobQueueSummary.innerHTML = `
        <div class="job-queue-metric"><div class="k">Active Jobs</div><div class="v">${esc(list.length)}</div></div>
        <div class="job-queue-metric"><div class="k">Running Jobs</div><div class="v">${esc(runningRows.length)}</div></div>
        <div class="job-queue-metric"><div class="k">Disconnected</div><div class="v">${esc(disconnectedRows.length)}</div></div>
        <div class="job-queue-metric"><div class="k">Remaining Qty</div><div class="v">${esc(remainingTotal)}</div></div>
      `;
    }

    if(!list.length){
      jobQueueTableWrap.innerHTML = '<div class="placeholder">No active jobs in queue yet.</div>';
      return;
    }

    jobQueueTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Machine</th>
            <th>Job</th>
            <th>Operator</th>
            <th>Started</th>
            <th>Status</th>
            <th>Produced</th>
            <th>Target</th>
            <th>Remaining</th>
            <th>Time Remaining</th>
            <th>Ends</th>
            <th>Act Cycle ETA</th>
            <th>Pack Cycle ETA</th>
          </tr>
        </thead>
        <tbody>
          ${list.map((row) => {
            const actCycleText = row?.act_cycle_seconds ? `${Number(row.act_cycle_seconds).toFixed(2)} sec | ${row?.act_qty_per_shift ?? "-"} / shift` : "-";
            const packCycleText = row?.live_cycle_seconds ? `${Number(row.live_cycle_seconds).toFixed(2)} sec | ${row?.live_qty_per_shift ?? "-"} / shift` : "-";
            const noTarget = Number(row?.target_qty || 0) <= 0;
            const isDisconnected = !Boolean(row?.is_connected);
            const startText = row?.job_started_at ? fmtDateLocal(row.job_started_at) : "-";
            const actEtaDate = row?.expected_finish_act_utc ? fmtDateLocal(row.expected_finish_act_utc) : "";
            const actEtaLeft = row?.expected_finish_act_utc ? `${fmtDowntimeSeconds(row?.remaining_seconds_act)} left${isDisconnected ? " (frozen)" : ""}` : (noTarget ? "No target qty" : (actCycleText === "-" ? "No act cycle time" : "Target reached"));
            const packEtaDate = row?.expected_finish_pack_utc ? fmtDateLocal(row.expected_finish_pack_utc) : "";
            const packEtaLeft = row?.expected_finish_pack_utc ? `${fmtDowntimeSeconds(row?.remaining_seconds_pack)} left${isDisconnected ? " (frozen)" : ""}` : (noTarget ? "No target qty" : (packCycleText === "-" ? "No pack cycle time" : "Target reached"));
            const preferredRemaining = row?.remaining_seconds_pack ?? row?.remaining_seconds_act ?? null;
            const preferredEnd = row?.expected_finish_pack_utc || row?.expected_finish_act_utc || "";
            const remainingText = preferredRemaining != null
              ? `${fmtDowntimeSeconds(preferredRemaining)}${isDisconnected ? " (frozen)" : ""}`
              : (noTarget ? "No target qty" : "Target reached");
            const endText = preferredEnd ? fmtDateLocal(preferredEnd) : (noTarget ? "No target qty" : "Target reached");
            return `
              <tr>
                <td>${esc(row?.machine_name || row?.machine_code || "-")}<br><span class="muted">${esc(row?.machine_code || "-")}</span></td>
                <td>${esc(row?.job_name || row?.job_code || "-")}<br><span class="muted">${esc(row?.job_code || "-")}</span></td>
                <td>${esc(displayNameForId(row?.operator_id || "-"))}${row?.last_seen_utc ? `<br><span class="muted">Last seen ${esc(fmtDateLocal(row.last_seen_utc))}</span>` : ""}</td>
                <td>${esc(startText)}</td>
                <td>${queueStatusBadge(row?.status || "RUNNING")}</td>
                <td>${esc(row?.produced_now ?? 0)}<br><span class="muted">Pack ${esc(row?.pack_count ?? 0)}</span></td>
                <td>${esc(row?.target_qty ?? 0)}<br><span class="muted">Cavity ${esc(row?.cavity_count ?? 1)}</span></td>
                <td>${esc(row?.remaining_qty ?? 0)}${Number(row?.overrun_qty || 0) > 0 ? `<br><span class="muted">Over ${esc(row?.overrun_qty || 0)}</span>` : ""}</td>
                <td>${esc(remainingText)}</td>
                <td>${esc(endText)}</td>
                <td>${actEtaDate ? `${esc(actEtaDate)}<br>` : ""}<span class="muted">${esc(actEtaLeft)}</span><br><span class="muted">${esc(actCycleText)}</span></td>
                <td>${packEtaDate ? `${esc(packEtaDate)}<br>` : ""}<span class="muted">${esc(packEtaLeft)}</span><br><span class="muted">${esc(packCycleText)}</span></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function setFinishedJobsInteractionLock(locked){
    finishedJobsInteractionLock = Boolean(locked);
    if(!finishedJobsInteractionLock && pendingFinishedJobsRows){
      const rows = pendingFinishedJobsRows;
      pendingFinishedJobsRows = null;
      renderFinishedJobs(rows);
    }
  }

  async function loadProducts(forceRefresh = false){
    const shouldRefresh = forceRefresh;
    const url = shouldRefresh ? "/api/products?refresh=1" : "/api/products";
    const res = await fetch(url, { method: "GET" });
    const data = await res.json();
    productItems = Array.isArray(data.items) ? data.items : [];
    productsHydrated = true;
    if(!productItems.length){
      overlayProductSuggest.innerHTML = "";
      overlayProductSuggest.classList.remove("active");
      overlayProductSelect.value = "";
      overlayProductSelect.placeholder = "No products available";
      return;
    }
    if(!overlayProductSelect.value){
      const first = productItems[0];
      overlayProductSelect.value = `${first.sku || ""} - ${first.name}`;
    }
  }

  function openApprovePrintOverlay(job){
    activeJobRow = job || null;
    overlayReviewSavedApproved = false;
    overlayReviewMode = isShiftPartialRecord(activeJobRow) ? "shift" : "job";
    if(overlayReviewSubmitBtn) overlayReviewSubmitBtn.textContent = overlayReviewMode === "shift" ? "Save Changes" : "Save Review";
    if(overlayReviewContinueBtn) overlayReviewContinueBtn.style.display = overlayReviewMode === "shift" ? "none" : "";
    const title = activeJobRow
      ? `${activeJobRow.job_name || activeJobRow.job_code || "Finished Job"} | ${activeJobRow.machine_name || activeJobRow.machine_code || "-"}`
      : "Finished Job";
    const key = jobKeyOf(activeJobRow);
    overlayJobInfo.value = title;
    if(overlayReviewJobInfo) overlayReviewJobInfo.value = title;
    if(overlayReviewJobInfoDisplay) overlayReviewJobInfoDisplay.textContent = title;
    const shiftPanels = overlayReviewMode === "shift" ? buildShiftPreviewPanels(activeJobRow) : null;
    if(overlayReviewSummary) overlayReviewSummary.value = shiftPanels ? shiftPanels.summary : reviewSummaryText(activeJobRow);
    if(overlayReviewRejects) overlayReviewRejects.value = shiftPanels ? shiftPanels.rejects : reviewRejectsText(activeJobRow);
    if(overlayReviewSummaryDisplay) overlayReviewSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.summary, "No shift summary.")
      : renderSummaryMetricsHtml(activeJobRow);
    if(overlayReviewRejectsDisplay) overlayReviewRejectsDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.rejects, "No reject details recorded.")
      : renderBulletListHtml(reviewRejectsText(activeJobRow), "No reject details recorded.");
    const rawLogs = Array.isArray(activeJobRow?.raw_material_logs) ? activeJobRow.raw_material_logs : [];
    if(overlayRawConsumption) overlayRawConsumption.value = shiftPanels
      ? shiftPanels.rawConsumption
      : (rawLogs.length
        ? rawLogs.map((x, i) => rawMaterialLine(x, i)).join("\\n")
        : "No raw material consumption records.");
    if(overlayRawConsumptionDisplay) overlayRawConsumptionDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.rawConsumption, "No raw material consumption records.")
      : renderBulletListHtml(overlayRawConsumption?.value || "", "No raw material consumption records.");
    if(overlayRawCycleSummary) overlayRawCycleSummary.value = shiftPanels
      ? shiftPanels.rawCycle
      : [
        `Raw Materials / Sacks Count: ${activeJobRow?.raw_sacks_count ?? 0}`,
        `Cycle Count (Pack): ${activeJobRow?.pack_count ?? 0}`,
        `Cycle Time: ${activeJobRow?.cycle_time_current || "-"}`,
      ].join("\\n");
    if(overlayRawCycleSummaryDisplay) overlayRawCycleSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.rawCycle, "No raw/cycle data.")
      : renderBulletListHtml(overlayRawCycleSummary?.value || "");
    if(overlayDowntimeSummary) overlayDowntimeSummary.value = shiftPanels
      ? shiftPanels.downtime
      : [
        `Reason: ${activeJobRow?.downtime_reason_code || "-"} ${activeJobRow?.downtime_reason_text || ""}`.trim(),
        `Downtime: ${fmtDowntimeSeconds(activeJobRow?.downtime_last_seconds)}`,
      ].join("\\n");
    if(overlayDowntimeSummaryDisplay) overlayDowntimeSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.downtime, "No downtime data.")
      : renderBulletListHtml(overlayDowntimeSummary?.value || "");
    if(overlayPeopleSummary) overlayPeopleSummary.value = shiftPanels
      ? shiftPanels.people
      : [
        `Maintenance: ${activeJobRow?.maintenance_name || "-"}`,
        `Supervisor: ${activeJobRow?.supervisor_name || "-"}`,
        `QC: ${qcFromFinishedJob(activeJobRow)}`,
        `Start Up Reject: ${activeJobRow?.startup_reject_total ?? 0}`,
        `No Shot: ${activeJobRow?.no_shot_total ?? 0}`,
      ].join("\\n");
    if(overlayPeopleSummaryDisplay) overlayPeopleSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.people, "No team data.")
      : renderBulletListHtml(overlayPeopleSummary?.value || "");
    if(overlayReviewerBadge) overlayReviewerBadge.value = "";
    if(overlayReviewerScanInput){
      overlayReviewerScanInput.value = "";
      overlayReviewerScanInput.style.display = "none";
    }
    if(overlayReviewRemarks) overlayReviewRemarks.value = "";
    fillDisapproveFields(activeJobRow);
    reviewSlideIndex = 0;
    syncReviewSubslides();
    setOverlayStep("review");
    generatedQrState = { jobKey: key, payload: "", qty: "", index: "", total: "", lotNumber: "", stageLabel: "", stageKind: "", plan: [], planIndex: 0, printRequests: [] };
    overlayQrPayload.value = "";
    overlayQty.value = "";
    overlayIndex.value = "";
    overlayTotal.value = "";
    overlayLotNumber.value = "";
    if(overlayQrStageLabel) overlayQrStageLabel.value = "2 / 2 - QR Print";
    if(overlayPoNumber){
      overlayPoNumber.value = "";
      overlayPoNumber.placeholder = "Enter PO Number...";
    }
    if(overlayPoNumberRow){
      overlayPoNumberRow.style.display = "none";
    }
    approvePrintOverlay.classList.add("active");
    if(productItems.length){
      renderProductSuggestions(overlayProductSelect.value || "");
    }
  }

  function closeApprovePrintOverlay(){
    approvePrintOverlay.classList.remove("active");
    activeJobRow = null;
    overlayReviewSavedApproved = false;
    overlayReviewMode = "job";
    reviewSlideIndex = 0;
    syncReviewSubslides();
    setOverlayStep("review");
  }

  function machineCardHtml(s, code, css, statusLabel){
    const linkageJobs = Array.isArray(s.linkage_jobs) ? s.linkage_jobs : [];
    const hasLinkage = Boolean(s.linkage_enabled) && linkageJobs.length > 0;
    const total = Number(s.good_total||0) + Number(s.butal_total||0);
    const jobLabel = s.job_name
      ? (s.job_code ? `${s.job_name} (${s.job_code})` : s.job_name)
      : (s.job_code || "No Job Set");
    const seenLabel = s.last_seen_utc ? new Date(s.last_seen_utc).toLocaleString() : "-";
    return `
      ${hasLinkage ? `<div class="machine-linkage-flag">LINKED JOBS: ${esc(linkageJobs.length)}</div>` : ""}
      <h3>${esc(s.machine_name || s.machine_code)}</h3>
      <p>Machine: <strong>${esc(s.machine_code || code)}</strong></p>
      <p>Job: <strong>${esc(jobLabel)}</strong></p>
      <p>Operator: <strong>${esc(displayNameForId(s.operator_id || "-"))}</strong></p>
      <p>Client: <strong>${esc(displayNameForId(s.client_id || "-"))}</strong></p>
      <p>Status: <strong>${esc(statusLabel || css.toUpperCase())}</strong></p>
      <p>Pack: <strong>${esc(s.pack_total)}</strong></p>
      <p>Good: <strong>${esc(s.good_total)}</strong></p>
      <p>Butal: <strong>${esc(s.butal_total)}</strong></p>
      <p>Reject: <strong>${esc(s.reject_total)}</strong></p>
      <p>No Shot: <strong>${esc(s.no_shot_total || 0)}</strong></p>
      <p>Total: <strong>${esc(total)}</strong></p>
      <p class="muted">Last Seen: ${esc(seenLabel)}</p>
      <p class="muted">Last Event: ${esc(s.last_event || "-")}</p>
    `;
  }

  function upsertMachineCard(s, code, css, statusLabel){
    let card = machineCardEls.get(code);
    if(!card){
      card = document.createElement("div");
      card.dataset.machineCode = code;
      card.addEventListener("click", () => {
        const fresh = (latestState.sessions || []).find(x => String(x.machine_code || "").trim() === code) || s;
        openMachineDetail(fresh);
      });
      machineCardEls.set(code, card);
    }
    card.className = `card ${css}`;
    card.innerHTML = machineCardHtml(s, code, css, statusLabel);
    return card;
  }

  function render(state){
    latestState = state || { sessions: [] };
    machineStatusOverridesState = (state && state.machine_status_overrides && typeof state.machine_status_overrides === "object") ? state.machine_status_overrides : {};
    machineStatusArchiveState = (state && Array.isArray(state.machine_status_archive)) ? state.machine_status_archive : [];
    timeEl.textContent = "Server UTC: " + (state.server_time_utc || "-");
    const sessions = state.sessions || [];
    const activeTtlSeconds = Number(state.active_ttl_seconds || 30);
    const byCode = Object.fromEntries(sessions.map(s => [String(s.machine_code || "").trim(), s]));
    const sessionCodes = sessions
      .map(s => String(s.machine_code || "").trim())
      .filter(Boolean);
    const allCodes = Array.from(new Set([...DEFAULT_MACHINE_CODES, ...sessionCodes])).sort();
    machineCountEl.textContent = String(allCodes.length);

    const desiredCodes = new Set(allCodes);
    for(const code of allCodes){
      const s = byCode[code] || {
        machine_code: code,
        machine_name: MACHINE_NAME_MAP[code] || code,
        job_code: "",
        job_name: "",
        operator_id: "",
        client_id: "",
        pack_total: 0,
        good_total: 0,
        butal_total: 0,
        reject_total: 0,
        no_shot_total: 0,
        last_event: "No data yet",
        last_seen_utc: "",
      };
      const manual = machineStatusOverrideFor(code);
      const manualStatus = String((manual && manual.status) || "").trim();
      const css = statusClass(s.last_seen_utc, activeTtlSeconds, manualStatus) || "disconnected";
      const statusLabel = manualStatus || css.toUpperCase();
      s.machine_name = s.machine_name || MACHINE_NAME_MAP[code] || code;
      const card = upsertMachineCard(s, code, css, statusLabel);
      if(card.parentNode !== machineGrid){
        machineGrid.appendChild(card);
      }
    }

    for(const [code, card] of machineCardEls.entries()){
      if(desiredCodes.has(code)) continue;
      if(card && card.parentNode) card.parentNode.removeChild(card);
      machineCardEls.delete(code);
    }
    renderJobQueue(state.job_queue || []);
    renderFinishedJobs(state.finished_jobs || []);
    renderArchivedJobs(state.archived_jobs || []);
    renderMachineStatusArchive(machineStatusArchiveState);
    renderDowntimeArchive(state.finished_jobs || [], state.archived_jobs || []);
    renderMaintenanceTab(state || {});
  }

  // tab handling
  document.querySelectorAll(".main-tab-button").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-target");
      document.querySelectorAll(".main-tab-button").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".main-tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(target)?.classList.add("active");
    });
  });
  document.querySelectorAll(".sub-tab-button").forEach(btn => {
    btn.addEventListener("click", () => {
      const host = btn.closest(".panel");
      if(!host) return;
      const target = btn.getAttribute("data-target");
      host.querySelectorAll(".sub-tab-button").forEach(b => b.classList.remove("active"));
      host.querySelectorAll(".sub-tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      host.querySelector(`#${target}`)?.classList.add("active");
    });
  });

  if(serverSettingsBtn){
    serverSettingsBtn.addEventListener("click", async () => {
      await loadServerSettingsUi(false);
      await loadSettingsProfilesUi();
      showServerSettingsPage("general");
      serverSettingsOverlay?.classList.add("active");
    });
  }
  if(dailyRolesBtn){
    dailyRolesBtn.addEventListener("click", async () => {
      if(dailyRoleBadgeInput) dailyRoleBadgeInput.value = "";
      if(dailyRoleNameInput) dailyRoleNameInput.value = "";
      if(dailyRoleCompanyRoleInput) dailyRoleCompanyRoleInput.value = "";
      if(dailyRoleExtraPrivilegeSelect) dailyRoleExtraPrivilegeSelect.value = "none";
      if(dailyRoleEffectiveRightsInput) dailyRoleEffectiveRightsInput.value = "Viewer";
      await loadSettingsProfilesUi();
      await loadDailyRolesUi();
      dailyRolesOverlay?.classList.add("active");
      setTimeout(() => dailyRoleBadgeInput?.focus(), 0);
    });
  }
  if(operatorsDirectoryBtn){
    operatorsDirectoryBtn.addEventListener("click", async () => {
      operatorDirectoryOverlay?.classList.add("active");
      await loadOperatorDirectory();
    });
  }
  if(profileCreatorBtn){
    profileCreatorBtn.addEventListener("click", async () => {
      const pw = window.prompt("Admin password required to open Profile Creation:", "");
      if(pw === null) return;
      try{
        const r = await fetch('/api/profiles/authorize-open', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ admin_password: pw })
        });
        const j = await r.json().catch(() => ({}));
        if(!r.ok || !j.ok){
          alert(j.error || 'Invalid admin password');
          return;
        }
        window.open("/profiles", "_blank");
      }catch(err){
        alert(`Failed to authorize profile creation: ${err}`);
      }
    });
  }
  if(operatorDirectoryCloseBtn) operatorDirectoryCloseBtn.addEventListener("click", () => operatorDirectoryOverlay?.classList.remove("active"));
  if(operatorDirectoryOverlay){
    operatorDirectoryOverlay.addEventListener("click", (ev) => {
      if(ev.target === operatorDirectoryOverlay) operatorDirectoryOverlay.classList.remove("active");
    });
  }
  if(operatorDirectoryGrid){
    operatorDirectoryGrid.addEventListener("click", (ev) => {
      const row = ev.target && ev.target.closest ? ev.target.closest("[data-operator-index]") : null;
      if(!row) return;
      const idx = Number(row.getAttribute("data-operator-index") || "-1");
      if(idx >= 0) openOperatorDetail(idx);
    });
  }
  if(operatorDetailCloseBtn) operatorDetailCloseBtn.addEventListener("click", () => operatorDetailOverlay?.classList.remove("active"));
  if(operatorDetailOverlay){
    operatorDetailOverlay.addEventListener("click", (ev) => {
      if(ev.target === operatorDetailOverlay) operatorDetailOverlay.classList.remove("active");
    });
  }
  if(dailyRolesCloseBtn) dailyRolesCloseBtn.addEventListener("click", () => dailyRolesOverlay?.classList.remove("active"));
  if(dailyRolesOverlay){
    dailyRolesOverlay.addEventListener("click", (ev) => {
      if(ev.target === dailyRolesOverlay) dailyRolesOverlay.classList.remove("active");
    });
  }
  if(dailyRoleBadgeInput){
    dailyRoleBadgeInput.addEventListener("keydown", (ev) => {
      if(ev.key !== "Enter") return;
      ev.preventDefault();
      const badge = (dailyRoleBadgeInput.value || "").trim();
      if(!badge) return;
      const profile = findSettingsProfileById(badge);
      const known = (profile && profile.name) || knownPersonNameFromBadge(badge);
      if(known && dailyRoleNameInput && !dailyRoleNameInput.value.trim()){
        dailyRoleNameInput.value = known;
      }
      refreshDailyRoleDerivedUi();
      dailyRoleExtraPrivilegeSelect?.focus();
    });
    dailyRoleBadgeInput.addEventListener("input", () => {
      if(dailyRoleNameInput) dailyRoleNameInput.value = "";
      refreshDailyRoleDerivedUi();
    });
  }
  dailyRoleExtraPrivilegeSelect?.addEventListener("change", refreshDailyRoleDerivedUi);
  dailyRolesSaveBtn?.addEventListener("click", saveDailyRoleUi);
  if(serverSettingsCloseBtn) serverSettingsCloseBtn.addEventListener("click", () => serverSettingsOverlay?.classList.remove("active"));
  if(serverSettingsOverlay){
    serverSettingsOverlay.addEventListener("click", (ev) => {
      if(ev.target === serverSettingsOverlay) serverSettingsOverlay.classList.remove("active");
    });
  }
  settingsNavGeneral?.addEventListener("click", () => showServerSettingsPage("general"));
  settingsNavTheme?.addEventListener("click", () => showServerSettingsPage("theme"));
  settingsNavApi?.addEventListener("click", () => showServerSettingsPage("api"));
  settingsNavProfile?.addEventListener("click", async () => { await loadSettingsProfilesUi(); showServerSettingsPage("profile"); });
  settingsThemeSelect?.addEventListener("change", () => applyDashboardTheme(settingsThemeSelect.value));
  serverSettingsSaveBtn?.addEventListener("click", saveServerSettingsUi);
  settingsProductsRefreshBtn?.addEventListener("click", async () => {
    await loadProductsSettingsInfo(true);
  });

  finishedJobsList.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".approve-print-btn");
    if(!btn) return;
    setFinishedJobsInteractionLock(true);
    const idx = Number(btn.getAttribute("data-row-index"));
    if(Number.isNaN(idx) || idx < 0) return;
    const sorted = [...(finishedJobsState || [])].reverse();
    const row = sorted[idx];
    if(!row) return;
    openApprovePrintOverlay(row);
    if(!productItems.length){
      loadProducts(false);
    }
    setTimeout(() => setFinishedJobsInteractionLock(false), 0);
  });
  finishedShiftQueueList?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".shift-review-btn");
    if(!btn) return;
    const idx = Number(btn.getAttribute("data-row-index"));
    if(Number.isNaN(idx) || idx < 0) return;
    const sorted = [...(finishedShiftState || [])].reverse();
    const row = sorted[idx];
    if(!row) return;
    openApprovePrintOverlay(row);
    setOverlayStep("review");
    if(overlayReviewContinueBtn) overlayReviewContinueBtn.style.display = "none";
    if(overlayReviewSubmitBtn) overlayReviewSubmitBtn.textContent = "Save Changes";
  });
  finishedJobsList.addEventListener("mouseover", (ev) => {
    if(ev.target.closest(".approve-print-btn")) setFinishedJobsInteractionLock(true);
  });
  finishedJobsList.addEventListener("mouseout", (ev) => {
    const btn = ev.target.closest(".approve-print-btn");
    if(!btn) return;
    const nextEl = ev.relatedTarget instanceof Element ? ev.relatedTarget : null;
    if(nextEl && btn.contains(nextEl)) return;
    setFinishedJobsInteractionLock(false);
  });
  finishedJobsList.addEventListener("mousedown", (ev) => {
    if(ev.target.closest(".approve-print-btn")) setFinishedJobsInteractionLock(true);
  });
  archivedJobsTableWrap?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".archived-view-btn");
    if(!btn) return;
    const idx = Number(btn.getAttribute("data-row-index"));
    if(Number.isNaN(idx) || idx < 0) return;
    const sorted = [...(archivedJobsState || [])].reverse();
    const row = sorted[idx];
    if(!row) return;
    openMachineDetail(archivedRowToMachineSessionLike(row));
  });

  overlayCloseBtn.addEventListener("click", closeApprovePrintOverlay);
  overlayCancelBtn.addEventListener("click", closeApprovePrintOverlay);
  if(overlayOpenScanFieldBtn && overlayReviewerScanInput){
    overlayOpenScanFieldBtn.addEventListener("click", () => {
      openQrScanCaptureOverlay();
    });
  }
  if(qrScanCaptureCancelBtn) qrScanCaptureCancelBtn.addEventListener("click", closeQrScanCaptureOverlay);
  if(qrScanCaptureOverlay){
    qrScanCaptureOverlay.addEventListener("click", (ev) => {
      if(ev.target === qrScanCaptureOverlay) closeQrScanCaptureOverlay();
    });
  }
  if(qrScanCaptureInput){
    qrScanCaptureInput.addEventListener("keydown", (ev) => {
      if(ev.key !== "Enter") return;
      ev.preventDefault();
      const scanned = (qrScanCaptureInput.value || "").trim();
      if(!scanned) return;
      if(overlayReviewerBadge) overlayReviewerBadge.value = scanned;
      closeQrScanCaptureOverlay();
      if(overlayReviewRemarks) overlayReviewRemarks.focus();
    });
  }
  if(overlayBackToReviewBtn) overlayBackToReviewBtn.addEventListener("click", () => setOverlayStep("review"));
  if(overlayReviewPrevBtn) overlayReviewPrevBtn.addEventListener("click", () => {
    reviewSlideIndex = Math.max(0, Number(reviewSlideIndex || 0) - 1);
    syncReviewSubslides();
  });
  if(overlayReviewNextBtn) overlayReviewNextBtn.addEventListener("click", () => {
    reviewSlideIndex = Math.min(3, Number(reviewSlideIndex || 0) + 1);
    syncReviewSubslides();
  });
  machineDetailCloseBtn.addEventListener("click", closeMachineDetail);
  machineDetailSettingsBtn?.addEventListener("click", () => {
    if(!machineDetailStatusPanel) return;
    machineDetailStatusPanel.style.display = (machineDetailStatusPanel.style.display === "none") ? "" : "none";
  });
  machineDetailStatusSaveBtn?.addEventListener("click", async () => {
    const machineCode = String(activeMachineDetailCode || "").trim();
    if(!machineCode) return;
    const status = String(machineDetailStatusSelect?.value || "").trim();
    const isClearLikeStatus = (status === "" || status === "Working");
    const reason = String(machineDetailStatusReason?.value || "").trim();
    const setterBadge = String(machineDetailStatusSetterBadge?.value || "").trim();
    if(!isClearLikeStatus && !reason){
      alert("Reason is required before confirming machine status.");
      machineDetailStatusReason?.focus();
      return;
    }
    if(!setterBadge){
      alert("Scan user QR first before confirming machine status.");
      machineDetailStatusSetterBadge?.focus();
      return;
    }
    if(machineDetailStatusSaveBtn) machineDetailStatusSaveBtn.disabled = true;
    if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.add("active");
    if(machineStatusSaveBar) machineStatusSaveBar.style.width = "8%";
    if(machineStatusSaveCheck) machineStatusSaveCheck.classList.remove("done");
    let progress = 8;
    const anim = window.setInterval(() => {
      progress = Math.min(92, progress + 11);
      if(machineStatusSaveBar) machineStatusSaveBar.style.width = `${progress}%`;
    }, 70);
    try{
      const r = await fetch('/api/machines/status', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ machine_code: machineCode, status, reason, setter_badge: setterBadge })
      });
      const j = await r.json().catch(() => ({}));
      window.clearInterval(anim);
      if(!r.ok || !j.ok){
        if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.remove("active");
        if(machineStatusSaveBar) machineStatusSaveBar.style.width = "0%";
        alert(j.error || "Failed to save machine status");
        if(machineDetailStatusSaveBtn) machineDetailStatusSaveBtn.disabled = false;
        return;
      }
      if(machineStatusSaveBar) machineStatusSaveBar.style.width = "100%";
      if(machineStatusSaveCheck) machineStatusSaveCheck.classList.add("done");
      const savedStatusLabel = (status === "Working") ? "Working (Live Status)" : (status || "Auto (Live Status)");
      if(lastMessageEl) lastMessageEl.textContent = `Machine status updated: ${machineCode} -> ${savedStatusLabel} by ${j?.actor?.name || setterBadge}`;
      setTimeout(() => {
        if(machineDetailStatusPanel) machineDetailStatusPanel.style.display = "none";
        if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.remove("active");
        if(machineStatusSaveBar) machineStatusSaveBar.style.width = "0%";
        if(machineStatusSaveCheck) machineStatusSaveCheck.classList.remove("done");
        if(machineDetailStatusSetterBadge) machineDetailStatusSetterBadge.value = "";
      }, 650);
    }catch(err){
      window.clearInterval(anim);
      if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.remove("active");
      if(machineStatusSaveBar) machineStatusSaveBar.style.width = "0%";
      alert(`Failed to save machine status: ${err}`);
    } finally {
      if(machineDetailStatusSaveBtn) machineDetailStatusSaveBtn.disabled = false;
    }
  });
  approvePrintOverlay.addEventListener("click", (_ev) => {
    // Keep the review/print popup open unless user uses explicit Close/Cancel buttons.
  });
  machineDetailOverlay.addEventListener("click", (ev) => {
    if(ev.target === machineDetailOverlay) closeMachineDetail();
  });

  overlayProductSelect.addEventListener("focus", () => {
    if(productItems.length){
      renderProductSuggestions(overlayProductSelect.value || "");
    }
  });

  overlayProductSelect.addEventListener("input", () => {
    renderProductSuggestions(overlayProductSelect.value || "");
  });
  overlayPoNumber?.addEventListener("input", () => {
    if(generatedQrState.stageKind === "BUTAL"){
      const po = (overlayPoNumber.value || "").trim();
      if(!po){
        overlayQrPayload.value = "Enter PO Number for Butal.";
        return;
      }
      refreshQrStagePayload().catch(() => {});
    }
  });

  overlayProductSelect.addEventListener("keydown", (ev) => {
    if(!overlayProductSuggest.classList.contains("active")){
      if(ev.key === "Escape"){
        ev.stopPropagation();
      }
      return;
    }
    if(ev.key === "ArrowDown"){
      ev.preventDefault();
      productSuggestionIndex = Math.min(productSuggestionItems.length - 1, productSuggestionIndex + 1);
    } else if(ev.key === "ArrowUp"){
      ev.preventDefault();
      productSuggestionIndex = Math.max(0, productSuggestionIndex - 1);
    } else if(ev.key === "Enter"){
      if(productSuggestionIndex >= 0){
        ev.preventDefault();
        pickProductSuggestion(productSuggestionIndex);
      }
      return;
    } else if(ev.key === "Escape"){
      ev.preventDefault();
      ev.stopPropagation();
      overlayProductSuggest.classList.remove("active");
      return;
    } else {
      return;
    }
    Array.from(overlayProductSuggest.querySelectorAll(".overlay-suggest-item")).forEach((el, idx) => {
      el.classList.toggle("active", idx === productSuggestionIndex);
    });
  });

  overlayProductSuggest.addEventListener("mousedown", (ev) => {
    const btn = ev.target.closest(".overlay-suggest-item");
    if(!btn) return;
    ev.preventDefault();
    const idx = Number(btn.getAttribute("data-idx"));
    if(!Number.isNaN(idx)){
      pickProductSuggestion(idx);
    }
  });

  document.addEventListener("mousedown", (ev) => {
    if(!approvePrintOverlay.classList.contains("active")) return;
    if(ev.target === overlayProductSelect) return;
    if(overlayProductSuggest.contains(ev.target)) return;
    overlayProductSuggest.classList.remove("active");
  });

  overlayGenerateBtn.addEventListener("click", async () => {
    await refreshQrStagePayload();
  });

  overlayRequestBtn.addEventListener("click", async () => {
    if(!overlayReviewSavedApproved){
      overlayQrPayload.value = "Review approval is required before requesting print.";
      return;
    }
    const product = resolveProductFromText(overlayProductSelect.value || "");
    if(!product){
      overlayQrPayload.value = "Select a product first.";
      return;
    }
    const quantity = (overlayQty.value || "").trim();
    const total = (overlayTotal.value || "").trim();
    const poNumber = (overlayPoNumber.value || "").trim();
    const lotNumber = (overlayLotNumber.value || "").trim();
    const stageNeedsPo = generatedQrState.stageKind === "BUTAL";
    if(!quantity || !total || !lotNumber || (stageNeedsPo && !poNumber)){
      overlayQrPayload.value = stageNeedsPo
        ? "Generate QR first so Quantity/Total/Lot/PO are complete."
        : "Generate QR first so Quantity/Total/Lot are complete.";
      return;
    }

    const productName = `[${(product.sku || "").toString().trim()}] ${(product.name || "").toString().trim()}`.trim();
    const requestPayload = {
      product_name: productName,
      quantity: quantity,
      total: total,
      po_number: poNumber,
      product_desc: (activeJobRow && (activeJobRow.job_name || activeJobRow.job_code)) || "",
      requested_at_ph: "",
      lot_number: lotNumber,
      qr_stage_label: generatedQrState.stageLabel || "",
    };

    const resp = await fetch("/api/qrgen/pending-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    const out = await resp.json();
    if(out.ok){
      generatedQrState.printRequests = [...(generatedQrState.printRequests || []), requestPayload];
      const hasNext = Array.isArray(generatedQrState.plan) && generatedQrState.planIndex < (generatedQrState.plan.length - 1);
      if(hasNext){
        generatedQrState.planIndex += 1;
        applyGeneratedQrPlanEntry(generatedQrState.plan[generatedQrState.planIndex]);
        if(generatedQrState.stageKind === "BUTAL"){
          overlayQrPayload.value = "Enter PO Number for Butal.";
        } else {
          overlayQrPayload.value = `${overlayQrPayload.value}\n\nPrint request sent. Next QR stage loaded.`;
        }
        return;
      }
      overlayQrPayload.value = `${overlayQrPayload.value}\n\nPrint request sent. Shift finished.`;
      try {
        const archiveResp = await fetch("/api/finished-jobs/archive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_key: jobKeyOf(activeJobRow),
            qr_payload: overlayQrPayload.value || "",
            print_payload: requestPayload,
            print_payloads: generatedQrState.printRequests || [],
          }),
        });
        const archiveOut = await archiveResp.json();
        if(archiveOut.ok){
          activeJobRow = archiveOut.item || activeJobRow;
          overlayQrPayload.value = `${overlayQrPayload.value}\nArchived to Archived Jobs.`;
          setTimeout(() => {
            closeApprovePrintOverlay();
          }, 450);
        } else {
          overlayQrPayload.value = `${overlayQrPayload.value}\nArchive warning: ${archiveOut.error || "Failed to archive."}`;
        }
      } catch (e) {
        overlayQrPayload.value = `${overlayQrPayload.value}\nArchive warning: ${e}`;
      }
    } else {
      const apiMsg = out?.target_base_url
        ? `QR generator API is not available. ${out.error || "Request failed."}`
        : (out.error || "Print request failed.");
      overlayQrPayload.value = apiMsg;
    }
  });

  async function submitFinishedJobReview(actionMode){
    if(!activeJobRow) return;
    const reviewerBadge = (overlayReviewerBadge.value || "").trim();
    const remarks = (overlayReviewRemarks.value || "").trim();
    const action = overlayReviewMode === "shift"
      ? "update"
      : (actionMode === "continue" ? "approve" : "disapprove");
    if(!reviewerBadge){
      overlayReviewRemarks.value = remarks;
      alert("Reviewer QR / badge is required.");
      return;
    }
    if(!remarks){
      alert("Remarks are required.");
      return;
    }
    let rejectBreakdown = {};
    try {
      rejectBreakdown = JSON.parse((editRejectBreakdown.value || "{}").trim() || "{}");
    } catch {
      alert("Reject Details JSON is invalid.");
      return;
    }
    const changes = {
      pack_count: Number(editPackCount.value || 0),
      good_total: Number(editGoodTotal.value || 0),
      butal_total: Number(editButalTotal.value || 0),
      reject_total: Number(editRejectTotal.value || 0),
      total_good: Number(editTotalGood.value || 0),
      reject_breakdown: rejectBreakdown,
    };
    const resp = await fetch("/api/finished-jobs/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_key: jobKeyOf(activeJobRow),
        action,
        remarks,
        reviewer_badge: reviewerBadge,
        changes,
      }),
    });
    const out = await resp.json();
    if(!out.ok){
      alert(out.error || "Failed to save review.");
      return;
    }
    activeJobRow = out.item || activeJobRow;
    overlayReviewJobInfo.value = `${activeJobRow.job_name || activeJobRow.job_code || "Finished Job"} | ${activeJobRow.machine_name || activeJobRow.machine_code || "-"}`;
    if(overlayReviewJobInfoDisplay) overlayReviewJobInfoDisplay.textContent = overlayReviewJobInfo.value;
    const shiftPanels = overlayReviewMode === "shift" ? buildShiftPreviewPanels(activeJobRow) : null;
    overlayReviewSummary.value = shiftPanels ? safeJsonPretty(shiftPanels.summary) : reviewSummaryText(activeJobRow) + `\\n\\nStatus: ${activeJobRow.review_status || "-"}`;
    overlayReviewRejects.value = shiftPanels ? safeJsonPretty(shiftPanels.rejects) : reviewRejectsText(activeJobRow);
    if(overlayReviewSummaryDisplay) overlayReviewSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.summary, "No shift summary.")
      : renderSummaryMetricsHtml(activeJobRow);
    if(overlayReviewRejectsDisplay) overlayReviewRejectsDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.rejects, "No reject details recorded.")
      : renderBulletListHtml(overlayReviewRejects.value || "", "No reject details recorded.");
    fillDisapproveFields(activeJobRow);
    if(Array.isArray(latestState.finished_jobs)){
      const k = jobKeyOf(activeJobRow);
      latestState.finished_jobs = latestState.finished_jobs.map(x => jobKeyOf(x) === k ? activeJobRow : x);
      renderFinishedJobs(latestState.finished_jobs);
    }
    if(actionMode === "continue"){
      overlayReviewSavedApproved = true;
      setOverlayStep("qr");
      generatedQrState = { jobKey: jobKeyOf(activeJobRow), payload: "", qty: "", index: "", total: "", lotNumber: "", stageLabel: "", stageKind: "", plan: [], planIndex: 0, printRequests: [] };
      if(overlayPoNumber){
        overlayPoNumber.value = "";
      }
      if(overlayPoNumberRow){
        overlayPoNumberRow.style.display = "none";
      }
      setTimeout(() => { refreshQrStagePayload().catch(() => {}); }, 0);
    } else {
      overlayReviewSavedApproved = action === "approve";
      if(action === "approve"){
        alert("Approved and saved. You can now continue to QR.");
      } else if(action === "update"){
        alert("Shift review changes saved.");
      } else {
        alert("Disapproved changes saved. Review again and approve to continue to QR.");
      }
    }
  }

  overlayReviewSubmitBtn.addEventListener("click", () => submitFinishedJobReview("save"));
  overlayReviewContinueBtn.addEventListener("click", () => submitFinishedJobReview("continue"));

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${wsProto}://${location.host}/ws`);

  ws.onopen = () => { clientStatus.innerHTML = '<span class="status-dot connected"></span>Connected'; };
  ws.onclose = () => { clientStatus.innerHTML = '<span class="status-dot disconnected"></span>Disconnected'; };
  ws.onerror = () => { clientStatus.innerHTML = '<span class="status-dot disconnected"></span>Error'; };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    lastMessageEl.textContent = "STATE";
    if(msg.type === "STATE") render(msg);
  };

  // Apply saved dashboard theme/settings immediately on page load.
  loadServerSettingsUi(true).catch(() => {});

  // Warm product cache on page load so overlay opens fast.
  loadProducts(false).then(() => {
    // Optional background refresh; does not block UI.
    loadProducts(true).catch(() => {});
  }).catch(() => {});
