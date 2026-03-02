
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
  const finishedJobsList = document.getElementById("finishedJobsList");
  const archivedJobsTableWrap = document.getElementById("archivedJobsTableWrap");
  const operatorShiftSummaryWrap = document.getElementById("operatorShiftSummaryWrap");
  const machineStatusArchiveTableWrap = document.getElementById("machineStatusArchiveTableWrap");
  const downtimeArchiveTableWrap = document.getElementById("downtimeArchiveTableWrap");
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
  const overlayReviewSlideStatus = document.getElementById("overlayReviewSlideStatus");
  const overlayReviewPrevBtn = document.getElementById("overlayReviewPrevBtn");
  const overlayReviewNextBtn = document.getElementById("overlayReviewNextBtn");
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
    "M00004": "IMM 303",
    "M00005": "IMM 304",
    "M00006": "IMM 305",
    "M00007": "IMM 306",
    "M00008": "IMM 307",
    "M00009": "IMM 308",
    "M00010": "IMM 309",
    "M00011": "IMM 310",
    "M00012": "IMM 311",
    "M00013": "IMM 312",
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
  let archivedJobsState = [];
  let machineStatusArchiveState = [];
  let operatorShiftSummaryState = [];
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
  };
  let overlayReviewSavedApproved = false;
  let reviewSlideIndex = 0;
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
    const rawConsumptionHtml = rawLogs.length
      ? `<ol class="machine-detail-list">${rawLogs.map(x => `<li>${esc((x && (x.material || x.code || x.value)) || "-")} | qty=${esc((x && x.qty) ?? 0)}</li>`).join("")}</ol>`
      : `<div class="machine-detail-empty">No raw material consumption records.</div>`;
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
    overlayReviewContinueBtn.style.display = isReview ? "" : "none";
    overlayBackToReviewBtn.style.display = isReview ? "none" : "";
    overlayGenerateBtn.style.display = isReview ? "none" : "";
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
    if(overlayReviewSlideStatus){
      const labels = ["Job Summary", "Raw Mats / Cycle", "Downtime / Team", "Approval"];
      overlayReviewSlideStatus.textContent = `Slide ${reviewSlideIndex + 1} / ${total} - ${labels[reviewSlideIndex] || ""}`;
    }
    if(overlayReviewPrevBtn){
      overlayReviewPrevBtn.disabled = reviewSlideIndex <= 0;
      overlayReviewPrevBtn.style.display = overlayReviewStep.style.display === "none" ? "none" : "";
    }
    if(overlayReviewNextBtn){
      overlayReviewNextBtn.disabled = reviewSlideIndex >= total - 1;
      overlayReviewNextBtn.style.display = overlayReviewStep.style.display === "none" ? "none" : "";
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
      <span class="dot">•</span>
      <span>Total Good: ${esc(totalGood)}</span>
    `;
  }

  function renderFinishedJobs(rows){
    const items = Array.isArray(rows) ? rows : [];
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
      const rawText = rawLogs.length
        ? rawLogs.map((x, idx) => `${idx+1}. ${x.material || "-"} | qty=${x.qty || 0}`).join("\\n")
        : "No raw materials scanned.";
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
            <div><strong>Total Good:</strong> ${esc(r.total_good ?? 0)}</div>
            <div><strong>Startup Reject:</strong> ${esc(r.startup_reject_total ?? 0)}</div>
            <div><strong>Raw Sacks:</strong> ${esc(r.raw_sacks_count ?? 0)}</div>
          </div>
          <div class="raw-list">${esc(rawText)}</div>
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

  function renderOperatorShiftSummary(rows){
    const items = Array.isArray(rows) ? rows : [];
    operatorShiftSummaryState = items;
    if(!operatorShiftSummaryWrap) return;
    if(!items.length){
      operatorShiftSummaryWrap.innerHTML = '<div class="placeholder">No operator shift summaries saved yet.</div>';
      return;
    }
    const grouped = new Map();
    for(const row of items){
      const dateKey = String(row.date_key || "-").trim() || "-";
      const jobCode = String(row.job_code || "").trim();
      const machineCode = String(row.machine_code || "").trim();
      const groupKey = `${dateKey}||${jobCode}||${machineCode}`;
      if(!grouped.has(groupKey)){
        grouped.set(groupKey, {
          date_key: dateKey,
          job_code: jobCode,
          job_name: String(row.job_name || "").trim(),
          machine_code: machineCode,
          machine_name: String(row.machine_name || "").trim(),
          rows: [],
          pack_count: 0,
          good_total: 0,
          butal_total: 0,
          reject_total: 0,
          total_good: 0,
        });
      }
      const bucket = grouped.get(groupKey);
      bucket.rows.push(row);
      bucket.pack_count += Number(row.pack_count || 0);
      bucket.good_total += Number(row.good_total || 0);
      bucket.butal_total += Number(row.butal_total || 0);
      bucket.reject_total += Number(row.reject_total || 0);
      bucket.total_good += Number(row.total_good || 0);
    }
    const sorted = Array.from(grouped.values()).sort((a, b) => {
      if(a.date_key !== b.date_key) return String(b.date_key).localeCompare(String(a.date_key));
      return String(b.job_code || "").localeCompare(String(a.job_code || ""));
    });
    operatorShiftSummaryWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Machine</th>
            <th>Job</th>
            <th>Operators</th>
            <th>Pack</th>
            <th>Good</th>
            <th>Butal</th>
            <th>Reject</th>
            <th>Total Good</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map(group => {
            const operatorLines = group.rows
              .slice()
              .sort((a, b) => String(a.started_at_utc || "").localeCompare(String(b.started_at_utc || "")))
              .map(row => {
                const name = row.operator_name || displayNameForId(row.operator_id || "-");
                const timeSpan = `${fmtDateLocal(row.started_at_utc || "")} -> ${fmtDateLocal(row.ended_at_utc || "")}`;
                return `${esc(name)}<br><span class="muted">${esc(timeSpan)}</span><br><span class="muted">Pack ${esc(row.pack_count || 0)} | Good ${esc(row.good_total || 0)} | Reject ${esc(row.reject_total || 0)}</span>`;
              })
              .join("<hr style=\"border:none;border-top:1px solid #e5e7eb;margin:8px 0;\">");
            return `
              <tr>
                <td>${esc(group.date_key)}</td>
                <td>${esc(group.machine_name || group.machine_code || "-")}<br><span class="muted">${esc(group.machine_code || "-")}</span></td>
                <td>${esc(group.job_name || group.job_code || "-")}<br><span class="muted">${esc(group.job_code || "-")}</span></td>
                <td>${operatorLines || "-"}</td>
                <td>${esc(group.pack_count)}</td>
                <td>${esc(group.good_total)}</td>
                <td>${esc(group.butal_total)}</td>
                <td>${esc(group.reject_total)}</td>
                <td>${esc(group.total_good)}</td>
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
    const title = activeJobRow
      ? `${activeJobRow.job_name || activeJobRow.job_code || "Finished Job"} | ${activeJobRow.machine_name || activeJobRow.machine_code || "-"}`
      : "Finished Job";
    const key = jobKeyOf(activeJobRow);
    overlayJobInfo.value = title;
    if(overlayReviewJobInfo) overlayReviewJobInfo.value = title;
    if(overlayReviewJobInfoDisplay) overlayReviewJobInfoDisplay.textContent = title;
    if(overlayReviewSummary) overlayReviewSummary.value = reviewSummaryText(activeJobRow);
    if(overlayReviewRejects) overlayReviewRejects.value = reviewRejectsText(activeJobRow);
    if(overlayReviewSummaryDisplay) overlayReviewSummaryDisplay.innerHTML = renderSummaryMetricsHtml(activeJobRow);
    if(overlayReviewRejectsDisplay) overlayReviewRejectsDisplay.innerHTML = renderBulletListHtml(reviewRejectsText(activeJobRow), "No reject details recorded.");
    const rawLogs = Array.isArray(activeJobRow?.raw_material_logs) ? activeJobRow.raw_material_logs : [];
    if(overlayRawConsumption) overlayRawConsumption.value = rawLogs.length
      ? rawLogs.map((x, i) => `${i + 1}. ${(x?.material || x?.code || x?.value || "-")} | qty=${x?.qty ?? 0}`).join("\\n")
      : "No raw material consumption records.";
    if(overlayRawConsumptionDisplay) overlayRawConsumptionDisplay.innerHTML = renderBulletListHtml(overlayRawConsumption?.value || "", "No raw material consumption records.");
    if(overlayRawCycleSummary) overlayRawCycleSummary.value = [
      `Raw Materials / Sacks Count: ${activeJobRow?.raw_sacks_count ?? 0}`,
      `Cycle Count (Pack): ${activeJobRow?.pack_count ?? 0}`,
      `Cycle Time: ${activeJobRow?.cycle_time_current || "-"}`,
    ].join("\\n");
    if(overlayRawCycleSummaryDisplay) overlayRawCycleSummaryDisplay.innerHTML = renderBulletListHtml(overlayRawCycleSummary?.value || "");
    if(overlayDowntimeSummary) overlayDowntimeSummary.value = [
      `Reason: ${activeJobRow?.downtime_reason_code || "-"} ${activeJobRow?.downtime_reason_text || ""}`.trim(),
      `Downtime: ${fmtDowntimeSeconds(activeJobRow?.downtime_last_seconds)}`,
    ].join("\\n");
    if(overlayDowntimeSummaryDisplay) overlayDowntimeSummaryDisplay.innerHTML = renderBulletListHtml(overlayDowntimeSummary?.value || "");
    if(overlayPeopleSummary) overlayPeopleSummary.value = [
      `Maintenance: ${activeJobRow?.maintenance_name || "-"}`,
      `Supervisor: ${activeJobRow?.supervisor_name || "-"}`,
      `QC: ${qcFromFinishedJob(activeJobRow)}`,
      `Start Up Reject: ${activeJobRow?.startup_reject_total ?? 0}`,
    ].join("\\n");
    if(overlayPeopleSummaryDisplay) overlayPeopleSummaryDisplay.innerHTML = renderBulletListHtml(overlayPeopleSummary?.value || "");
    if(overlayReviewerBadge) overlayReviewerBadge.value = "";
    if(overlayReviewerScanInput){
      overlayReviewerScanInput.value = "";
      overlayReviewerScanInput.style.display = "none";
    }
    if(overlayReviewRemarks) overlayReviewRemarks.value = "";
    if(overlayReviewAction) overlayReviewAction.value = "approve";
    if(overlayDisapproveFields) overlayDisapproveFields.style.display = "none";
    fillDisapproveFields(activeJobRow);
    reviewSlideIndex = 0;
    syncReviewSubslides();
    setOverlayStep("review");
    if(generatedQrState.jobKey === key){
      overlayQrPayload.value = generatedQrState.payload || "";
      overlayQty.value = generatedQrState.qty || "";
      overlayIndex.value = generatedQrState.index || "";
      overlayTotal.value = generatedQrState.total || "";
      overlayLotNumber.value = generatedQrState.lotNumber || "";
    } else {
      generatedQrState = { jobKey: key, payload: "", qty: "", index: "", total: "", lotNumber: "" };
      overlayQrPayload.value = "";
      overlayQty.value = "";
      overlayIndex.value = "";
      overlayTotal.value = "";
      overlayLotNumber.value = "";
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
    operatorShiftSummaryState = (state && Array.isArray(state.operator_shift_summaries)) ? state.operator_shift_summaries : [];
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
    renderFinishedJobs(state.finished_jobs || []);
    renderArchivedJobs(state.archived_jobs || []);
    renderOperatorShiftSummary(operatorShiftSummaryState);
    renderMachineStatusArchive(machineStatusArchiveState);
    renderDowntimeArchive(state.finished_jobs || [], state.archived_jobs || []);
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
  if(overlayReviewAction){
    overlayReviewAction.addEventListener("change", () => {
      if(overlayDisapproveFields){
        overlayDisapproveFields.style.display = overlayReviewAction.value === "disapprove" ? "" : "none";
      }
      if(overlayReviewAction.value === "disapprove" && reviewSlideIndex < 3){
        reviewSlideIndex = 3;
        syncReviewSubslides();
      }
    });
  }
  if(overlayReviewPrevBtn){
    overlayReviewPrevBtn.addEventListener("click", () => {
      reviewSlideIndex = Math.max(0, reviewSlideIndex - 1);
      syncReviewSubslides();
    });
  }
  if(overlayReviewNextBtn){
    overlayReviewNextBtn.addEventListener("click", () => {
      reviewSlideIndex = Math.min(3, reviewSlideIndex + 1);
      syncReviewSubslides();
    });
  }
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
    if(!overlayReviewSavedApproved){
      overlayQrPayload.value = "Review approval is required before generating QR.";
      return;
    }
    const productId = resolveProductIdFromText(overlayProductSelect.value || "");
    if(!productId){
      overlayQrPayload.value = "Select a product first.";
      return;
    }
    const poNumber = (overlayPoNumber.value || "").trim();
    if(!poNumber){
      overlayQrPayload.value = "Provide PO Number first.";
      return;
    }
    const resp = await fetch("/api/raw-material-qr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: productId,
        po_number: poNumber,
        finished_job: activeJobRow || {},
      }),
    });
    const out = await resp.json();
    const payloadText = out.qr_payload || out.error || "Failed to generate.";
    overlayQrPayload.value = payloadText;
    const parsed = out.parsed || {};
    overlayQty.value = parsed.qty || "";
    overlayIndex.value = parsed.index || "";
    overlayTotal.value = parsed.total || "";
    overlayLotNumber.value = parsed.lot_number || "";
    generatedQrState = {
      jobKey: jobKeyOf(activeJobRow),
      payload: payloadText,
      qty: overlayQty.value || "",
      index: overlayIndex.value || "",
      total: overlayTotal.value || "",
      lotNumber: overlayLotNumber.value || "",
    };
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
    if(!quantity || !total || !poNumber || !lotNumber){
      overlayQrPayload.value = "Generate QR first so Quantity/Total/Lot/PO are complete.";
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
    };

    const resp = await fetch("/api/qrgen/pending-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    const out = await resp.json();
    if(out.ok){
      overlayQrPayload.value = `${overlayQrPayload.value}\n\nPrint request sent.`;
      try {
        const archiveResp = await fetch("/api/finished-jobs/archive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_key: jobKeyOf(activeJobRow),
            qr_payload: overlayQrPayload.value || "",
            print_payload: requestPayload,
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
      overlayQrPayload.value = out.error || "Print request failed.";
    }
  });

  async function submitFinishedJobReview(actionMode){
    if(!activeJobRow) return;
    const reviewerBadge = (overlayReviewerBadge.value || "").trim();
    const remarks = (overlayReviewRemarks.value || "").trim();
    const action = actionMode === "continue" ? "approve" : (overlayReviewAction.value || "approve");
    if(!reviewerBadge){
      overlayReviewRemarks.value = remarks;
      alert("Reviewer QR / badge is required.");
      return;
    }
    if(!remarks){
      alert("Remarks are required.");
      return;
    }
    let changes = {};
    if(action === "disapprove"){
      let rejectBreakdown = {};
      try {
        rejectBreakdown = JSON.parse((editRejectBreakdown.value || "{}").trim() || "{}");
      } catch {
        alert("Reject Details JSON is invalid.");
        return;
      }
      changes = {
        pack_count: Number(editPackCount.value || 0),
        good_total: Number(editGoodTotal.value || 0),
        butal_total: Number(editButalTotal.value || 0),
        reject_total: Number(editRejectTotal.value || 0),
        total_good: Number(editTotalGood.value || 0),
        reject_breakdown: rejectBreakdown,
      };
    }
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
    overlayReviewSummary.value = reviewSummaryText(activeJobRow) + `\\n\\nStatus: ${activeJobRow.review_status || "-"}`;
    overlayReviewRejects.value = reviewRejectsText(activeJobRow);
    if(overlayReviewSummaryDisplay) overlayReviewSummaryDisplay.innerHTML = renderSummaryMetricsHtml(activeJobRow);
    if(overlayReviewRejectsDisplay) overlayReviewRejectsDisplay.innerHTML = renderBulletListHtml(overlayReviewRejects.value || "", "No reject details recorded.");
    fillDisapproveFields(activeJobRow);
    if(Array.isArray(latestState.finished_jobs)){
      const k = jobKeyOf(activeJobRow);
      latestState.finished_jobs = latestState.finished_jobs.map(x => jobKeyOf(x) === k ? activeJobRow : x);
      renderFinishedJobs(latestState.finished_jobs);
    }
    if(actionMode === "continue"){
      overlayReviewSavedApproved = true;
      setOverlayStep("qr");
    } else {
      overlayReviewSavedApproved = action === "approve";
      if(action === "approve"){
        alert("Approved and saved. You can now continue to QR.");
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
