/**
 * Smart Co-Working Space Management | Executive Enterprise Client Application
 */

let currentSpaces = [];
let selectedFacility = null;
let selectedUnitForBooking = null;
let activeInquiryForResponse = null;

// Filter state (Curated segmented brackets - zero range sliders)
let activeFilters = {
  city: "all",
  team_bracket: "all",
  budget_bracket: "all",
  area_bracket: "all",
  work_style: "all",
  unit_type: "all",
  amenities: []
};

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
  initAuthUI();
  initNavigationTabs();
  initFilterControls();
  initModalDismissListeners();
  initSSEListener();

  // Connect to persistent Server-Sent Events (SSE) telemetry pipe
  TelemetryStream.connect();

  // Load initial spaces
  loadSpaces();

  // Update notification badge count if authenticated
  refreshNotificationsBadge();
});

// ==========================================================================
// Modal Dismiss Listeners (Escape key & backdrop click)
// ==========================================================================
function initModalDismissListeners() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-overlay.active").forEach(m => m.classList.remove("active"));
    }
  });

  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        overlay.classList.remove("active");
      }
    });
  });
}

// ==========================================================================
// Toast Notifications
// ==========================================================================
function showToast(message, type = "info") {
  const stack = document.getElementById("toast-stack");
  if (!stack) return;

  const toast = document.createElement("div");
  toast.className = "toast-pill";
  if (type === "success") toast.style.borderLeftColor = "var(--telemetry-vacant)";
  if (type === "error") toast.style.borderLeftColor = "var(--telemetry-occupied)";
  if (type === "warn") toast.style.borderLeftColor = "var(--telemetry-reserved)";

  toast.innerHTML = `<span>${message}</span>`;
  stack.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, 4200);
}

// ==========================================================================
// Authentication UI & Session Control
// ==========================================================================
function initAuthUI() {
  const container = document.getElementById("auth-profile-container");
  const user = API.getUser();

  if (user) {
    container.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="text-align: right;">
          <div style="font-weight: 800; font-size: 0.9rem; color: var(--brand-navy);">${user.full_name}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">${user.role} ${user.company_name ? '• ' + user.company_name : ''}</div>
        </div>
        <button class="btn btn-outline btn-sm" onclick="handleLogout()">Sign Out</button>
      </div>
    `;
    updateRoleVisibility(user.role);
    refreshNotificationsBadge();
  } else {
    container.innerHTML = `
      <button class="btn btn-primary btn-sm" onclick="openAuthModal('login')">Sign In</button>
      <button class="btn btn-outline btn-sm" onclick="openAuthModal('register')">Register</button>
    `;
    updateRoleVisibility("GUEST");
  }
}

function updateRoleVisibility(role) {
  const hostNav = document.getElementById("nav-item-host");
  const adminNav = document.getElementById("nav-item-admin");
  const bookingsNav = document.getElementById("nav-item-bookings");

  if (hostNav) hostNav.style.display = (role === "SPACE_OWNER" || role === "ADMIN") ? "flex" : "none";
  if (adminNav) adminNav.style.display = (role === "ADMIN") ? "flex" : "none";
  if (bookingsNav) bookingsNav.style.display = (role !== "GUEST") ? "flex" : "none";
}

function openAuthModal(mode = 'login') {
  const modal = document.getElementById("auth-modal");
  const title = document.getElementById("auth-modal-title");
  const regFields = document.getElementById("auth-register-fields");
  const submitBtn = document.getElementById("auth-submit-btn");

  // Keep admin and all user credentials blank by default
  const emailInput = document.getElementById("auth-email");
  const pwdInput = document.getElementById("auth-password");
  if (emailInput) {
    emailInput.value = "";
    emailInput.placeholder = "user@company.com";
  }
  if (pwdInput) {
    pwdInput.value = "";
    pwdInput.type = "password";
  }
  const btnToggle = document.getElementById("btn-toggle-pwd");
  if (btnToggle) btnToggle.textContent = "Show Password";

  // Clear any active button states
  document.querySelectorAll(".quick-role-btn").forEach(b => b.classList.remove("active"));

  if (mode === 'register') {
    title.innerText = "Create Your Account";
    regFields.style.display = "block";
    submitBtn.innerText = "Create Account";
    submitBtn.dataset.mode = "register";
  } else {
    title.innerText = "Executive Sign In";
    regFields.style.display = "none";
    submitBtn.innerText = "Sign In";
    submitBtn.dataset.mode = "login";
  }
  modal.classList.add("active");
}

function closeAuthModal() {
  document.getElementById("auth-modal").classList.remove("active");
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const mode = document.getElementById("auth-submit-btn").dataset.mode;
  const email = document.getElementById("auth-email").value;
  const password = document.getElementById("auth-password").value;

  try {
    if (mode === 'register') {
      const full_name = document.getElementById("auth-fullname").value;
      const role = document.getElementById("auth-role").value;
      const company = document.getElementById("auth-company").value;
      await API.register({ email, password, full_name, role, company_name: company });
      showToast("Account successfully registered! Welcome to SmartCoWork.", "success");
    } else {
      await API.login(email, password);
      showToast("Authentication confirmed. Welcome back!", "success");
    }
    closeAuthModal();
    initAuthUI();
    loadSpaces();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function handleLogout() {
  API.clearSession();
  initAuthUI();
  showToast("You have been signed out.", "info");
  switchTab("explore");
  loadSpaces();
}

function quickLoginAs(role) {
  const emailInput = document.getElementById("auth-email");
  const pwdInput = document.getElementById("auth-password");

  // Clear previous button active states
  document.querySelectorAll(".quick-role-btn").forEach(b => b.classList.remove("active"));

  if (role === 'ADMIN') {
    const adminBtn = document.getElementById("btn-quick-admin");
    if (adminBtn) adminBtn.classList.add("active");

    // Secure Admin Portal: DO NOT auto-fill or expose admin credentials in the client
    if (emailInput) {
      emailInput.value = "";
      emailInput.placeholder = "admin@company.com";
      emailInput.focus();
    }
    if (pwdInput) {
      pwdInput.value = "";
    }
  } else if (role === 'OWNER') {
    const hostBtn = document.getElementById("btn-quick-host");
    if (hostBtn) hostBtn.classList.add("active");

    if (emailInput) emailInput.value = "vikram.malhotra@nexusworkspaces.com";
    if (pwdInput) pwdInput.value = "NexusHost@2026!";
  } else if (role === 'USER') {
    const seekerBtn = document.getElementById("btn-quick-seeker");
    if (seekerBtn) seekerBtn.classList.add("active");

    if (emailInput) emailInput.value = "alex.rivera@techventures.io";
    if (pwdInput) pwdInput.value = "AlexSeeker@2026!";
  }
}

function togglePasswordVisibility() {
  const pwdInput = document.getElementById("auth-password");
  const btn = document.getElementById("btn-toggle-pwd");
  if (!pwdInput) return;
  if (pwdInput.type === "password") {
    pwdInput.type = "text";
    if (btn) btn.textContent = "Hide Password";
  } else {
    pwdInput.type = "password";
    if (btn) btn.textContent = "Show Password";
  }
}

// ==========================================================================
// Navigation & Tabs
// ==========================================================================
function initNavigationTabs() {
  const navBtns = document.querySelectorAll(".nav-link-btn");
  navBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      switchTab(tab);
    });
  });
}

function switchTab(tabId) {
  // Authorization guards for restricted administrative and space host portals
  if (tabId === "admin") {
    if (!API.currentUser || API.currentUser.role !== "ADMIN") {
      showToast("Access Restricted: System Administrator authorization required.", "error");
      openAuthModal("login");
      return;
    }
  }

  if (tabId === "host") {
    if (!API.currentUser || (API.currentUser.role !== "SPACE_OWNER" && API.currentUser.role !== "ADMIN")) {
      showToast("Access Restricted: Space Host authorization required.", "error");
      openAuthModal("login");
      return;
    }
  }

  if (tabId === "bookings") {
    if (!API.currentUser) {
      showToast("Please sign in to view your reservations.", "info");
      openAuthModal("login");
      return;
    }
  }

  document.querySelectorAll(".nav-link-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(p => p.style.display = "none");

  const targetBtn = document.querySelector(`.nav-link-btn[data-tab="${tabId}"]`);
  const targetPane = document.getElementById(`pane-${tabId}`);

  if (targetBtn) targetBtn.classList.add("active");
  if (targetPane) targetPane.style.display = "block";

  if (tabId === "floor-map") {
    loadFloorMapTab();
  } else if (tabId === "bookings") {
    loadMyBookings();
  } else if (tabId === "host") {
    loadHostHub();
  } else if (tabId === "admin") {
    loadAdminMetrics();
  }
}

// ==========================================================================
// Classy Segmented Filter Controls
// ==========================================================================
function initFilterControls() {
  // City Quick Pills
  document.querySelectorAll(".city-pill-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".city-pill-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilters.city = btn.dataset.city;
      loadSpaces();
    });
  });

  // Team Size Segmented Group
  setupSegmentedButtons("seg-team", (val) => {
    activeFilters.team_bracket = val;
    loadSpaces();
  });

  // Budget Segmented Group
  setupSegmentedButtons("seg-budget", (val) => {
    activeFilters.budget_bracket = val;
    loadSpaces();
  });

  // Area Size Segmented Group
  setupSegmentedButtons("seg-area", (val) => {
    activeFilters.area_bracket = val;
    loadSpaces();
  });

  // Work Style Dropdown
  const styleSelect = document.getElementById("filter-work-style");
  if (styleSelect) {
    styleSelect.addEventListener("change", (e) => {
      activeFilters.work_style = e.target.value;
      loadSpaces();
    });
  }

  // Workspace Type Dropdown
  const typeSelect = document.getElementById("filter-unit-type");
  if (typeSelect) {
    typeSelect.addEventListener("change", (e) => {
      activeFilters.unit_type = e.target.value;
      loadSpaces();
    });
  }

  // Amenity Checkboxes
  document.querySelectorAll(".filter-amenity-checkbox").forEach(cb => {
    cb.addEventListener("change", () => {
      const checked = [];
      document.querySelectorAll(".filter-amenity-checkbox:checked").forEach(c => checked.push(c.value));
      activeFilters.amenities = checked;
      loadSpaces();
    });
  });
}

function setupSegmentedButtons(groupId, callback) {
  const buttons = document.querySelectorAll(`.${groupId}-btn`);
  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      buttons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      callback(btn.dataset.val);
    });
  });
}

function resetAllFilters() {
  activeFilters = {
    city: "all",
    team_bracket: "all",
    budget_bracket: "all",
    area_bracket: "all",
    work_style: "all",
    unit_type: "all",
    amenities: []
  };

  document.querySelectorAll(".city-pill-btn").forEach(b => b.classList.remove("active"));
  document.querySelector('.city-pill-btn[data-city="all"]')?.classList.add("active");

  document.querySelectorAll(".segmented-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll('.segmented-btn[data-val="all"]').forEach(b => b.classList.add("active"));

  if (document.getElementById("filter-work-style")) document.getElementById("filter-work-style").value = "all";
  if (document.getElementById("filter-unit-type")) document.getElementById("filter-unit-type").value = "all";
  document.querySelectorAll(".filter-amenity-checkbox").forEach(c => c.checked = false);

  loadSpaces();
  showToast("Filters reset to default view.", "info");
}

// ==========================================================================
// Spaces Catalog & Smart Matching
// ==========================================================================
async function loadSpaces() {
  const grid = document.getElementById("spaces-grid");
  const countTitle = document.getElementById("spaces-results-count");
  if (!grid) return;

  grid.innerHTML = `
    <div style="grid-column: 1/-1; text-align: center; padding: 60px; color: var(--text-muted);">
      <div class="pulse-circle" style="margin: 0 auto 16px auto; width: 14px; height: 14px;"></div>
      <div style="font-weight: 700;">Querying facilities and computing real-time match rankings...</div>
    </div>
  `;

  try {
    const spaces = await API.getSpaces(activeFilters);
    currentSpaces = spaces;

    if (countTitle) {
      countTitle.innerText = `${spaces.length} Executive Workspaces Available`;
    }

    renderSpaces(spaces);
    populateFacilitySelect(spaces);
  } catch (err) {
    grid.innerHTML = `<div style="grid-column: 1/-1; color: var(--telemetry-occupied); text-align: center; padding: 40px;">
      Error fetching workspaces: ${err.message}
    </div>`;
  }
}

function renderSpaces(spaces) {
  const grid = document.getElementById("spaces-grid");
  if (!grid) return;

  if (spaces.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 70px 20px; background: white; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
        <h3 style="font-size: 1.4rem; color: var(--brand-navy); margin-bottom: 8px;">No Workspaces Match Your Specific Filter Criteria</h3>
        <p style="color: var(--text-muted); margin-bottom: 20px;">Try selecting 'All Sizes' or clearing some amenity filters to discover available hubs.</p>
        <button class="btn btn-outline" onclick="resetAllFilters()">Reset All Filters</button>
      </div>
    `;
    return;
  }

  grid.innerHTML = spaces.map(space => {
    const match = space.match_metrics || { overall_score: 90 };
    const totalUnits = space.total_units_count || 1;
    const occupiedPct = Math.round(((space.occupied_units_count || 0) / totalUnits) * 100);
    const reservedPct = Math.round(((space.reserved_units_count || 0) / totalUnits) * 100);
    const vacantPct = Math.round(((space.vacant_units_count || 0) / totalUnits) * 100);

    const minHourly = Math.min(...(space.units || []).map(u => u.hourly_price || 999), 12);
    const minDaily = Math.min(...(space.units || []).map(u => u.daily_price || 999), 60);

    return `
      <div class="space-card" data-space-id="${space.id}">
        <div class="card-media-wrap">
          <img src="${space.image_url}" alt="${space.name}" class="card-img" />
          <div class="match-score-pill">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="#38bdf8"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            ${match.overall_score}% Match
          </div>
          <div class="atmosphere-badge">${space.work_style.replace('_', ' ')}</div>
        </div>

        <div class="card-body">
          <h3 class="space-card-name">${space.name}</h3>
          <div class="space-card-address">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            ${space.address}, ${space.city} • ${space.total_area_sqft.toLocaleString()} sq ft
          </div>
          <p class="space-card-overview">${space.description}</p>

          <!-- Live Real-Time Telemetry Bar -->
          <div class="space-telemetry-panel">
            <div class="telemetry-row">
              <span style="font-weight: 800; color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase;">Live Availability</span>
              <span class="telemetry-status-pill" style="color: ${space.vacant_units_count > 0 ? 'var(--telemetry-vacant)' : 'var(--telemetry-occupied)'};">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: ${space.vacant_units_count > 0 ? 'var(--telemetry-vacant)' : 'var(--telemetry-occupied)'};"></span>
                ${space.vacant_units_count} Units Available
              </span>
            </div>
            <div class="telemetry-bar-track">
              <div class="telemetry-bar-occupied" style="width: ${occupiedPct}%;" title="Occupied: ${space.occupied_units_count}"></div>
              <div class="telemetry-bar-reserved" style="width: ${reservedPct}%;" title="Reserved: ${space.reserved_units_count}"></div>
              <div class="telemetry-bar-vacant" style="width: ${vacantPct}%;" title="Vacant: ${space.vacant_units_count}"></div>
            </div>
          </div>

          <div class="card-amenities-row">
            ${(space.amenities || []).slice(0, 4).map(a => `<span class="amenity-tag">${a.name}</span>`).join('')}
            ${(space.amenities || []).length > 4 ? `<span class="amenity-tag">+${space.amenities.length - 4} more</span>` : ''}
          </div>

          <div class="card-footer">
            <div class="rate-display">
              <div class="rate-amount">$${minHourly}<span style="font-size: 0.85rem; font-weight: 500; color: var(--text-muted);">/hr</span></div>
              <div class="rate-period">From $${minDaily}/day</div>
            </div>
            <div class="card-action-group">
              <button class="btn btn-outline btn-sm" onclick="openSpaceDetailsModal('${space.id}')">Details</button>
              <button class="btn btn-primary btn-sm" onclick="openFloorMapForSpace('${space.id}')">Live Map</button>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// ==========================================================================
// Interactive Architectural Floor Map Canvas
// ==========================================================================
function populateFacilitySelect(spaces) {
  const select = document.getElementById("blueprint-facility-select");
  if (!select) return;
  select.innerHTML = spaces.map(s => `<option value="${s.id}">${s.name} (${s.city})</option>`).join('');
  if (spaces.length > 0 && !selectedFacility) {
    selectedFacility = spaces[0];
  }
}

function openFloorMapForSpace(facilityId) {
  const fac = currentSpaces.find(s => s.id === facilityId);
  if (fac) {
    selectedFacility = fac;
    const select = document.getElementById("blueprint-facility-select");
    if (select) select.value = facilityId;
  }
  switchTab("floor-map");
}

async function loadFloorMapTab() {
  const select = document.getElementById("blueprint-facility-select");
  const facId = select ? select.value : (selectedFacility ? selectedFacility.id : "fac-01");

  try {
    const spaceData = await API.getSpaceDetail(facId);
    selectedFacility = spaceData;
    renderSVGBlueprint(spaceData);
  } catch (err) {
    console.error("Error loading blueprint data:", err);
  }
}

function renderSVGBlueprint(facility) {
  const wrapper = document.getElementById("blueprint-svg-wrapper");
  const spaceInfo = document.getElementById("blueprint-facility-info");
  if (!wrapper) return;

  if (spaceInfo) {
    spaceInfo.innerHTML = `
      <div style="font-size: 1.25rem; font-weight: 800; color: var(--brand-navy);">${facility.name}</div>
      <div style="font-size: 0.85rem; color: var(--text-muted); font-weight: 600;">
        ${facility.address}, ${facility.city} • Floor ${facility.units && facility.units[0] ? facility.units[0].floor_number : 1} Executive Architectural Blueprint
      </div>
    `;
  }

  const units = facility.units || [];

  let svg = `
    <svg class="blueprint-svg" viewBox="0 0 660 410" xmlns="http://www.w3.org/2000/svg">
      <!-- Exterior Walls -->
      <rect x="8" y="8" width="644" height="394" rx="14" fill="#0b132b" stroke="#334155" stroke-width="4" />
      
      <!-- Interior Zone Divisions & Markings -->
      <line x1="360" y1="8" x2="360" y2="260" stroke="#1e293b" stroke-width="2" stroke-dasharray="6,6" />
      <line x1="8" y1="260" x2="652" y2="260" stroke="#1e293b" stroke-width="2" stroke-dasharray="6,6" />

      <!-- Architectural Zone Headers -->
      <text x="180" y="36" fill="#64748b" font-size="11" font-weight="800" letter-spacing="1.5">ZONE A • HOT DESK BAY</text>
      <text x="500" y="36" fill="#64748b" font-size="11" font-weight="800" letter-spacing="1.5">ZONE B • TEAM CABINS</text>
      <text x="180" y="286" fill="#64748b" font-size="11" font-weight="800" letter-spacing="1.5">ZONE C • BOARDROOMS & AV</text>

      <!-- Main Security Entry / Reception -->
      <rect x="20" y="375" width="90" height="22" rx="4" fill="#1d4ed8" />
      <text x="65" y="390" fill="#ffffff" font-size="9" font-weight="800" text-anchor="middle" letter-spacing="0.5">NFC RECEPTION</text>
  `;

  units.forEach(u => {
    const x = u.x_pos || 60;
    const y = u.y_pos || 60;
    let width = 68;
    let height = 50;
    let rx = 8;

    if (u.type === "PRIVATE_CABIN") {
      width = 114;
      height = 76;
    } else if (u.type === "MEETING_ROOM") {
      width = 124;
      height = 80;
    }

    svg += `
      <g id="unit-node-${u.id}" class="desk-node status-${u.current_status}" onclick="handleUnitClick('${u.id}')">
        <rect x="${x}" y="${y}" width="${width}" height="${height}" rx="${rx}" stroke-width="2" />
        <text x="${x + width/2}" y="${y + height/2 - 3}" class="node-title-text">${u.unit_identifier}</text>
        <text x="${x + width/2}" y="${y + height/2 + 12}" class="node-sub-text">
          ${u.type === 'HOT_DESK' ? '1 Pax' : u.type === 'PRIVATE_CABIN' ? `${u.capacity} Pax Cabin` : `${u.capacity} Pax Suite`}
        </text>
        <title>${u.unit_identifier} (${u.type})\nStatus: ${u.current_status}\nRate: $${u.hourly_price}/hr\nClick to Reserve Instant Slot</title>
      </g>
    `;
  });

  svg += `</svg>`;
  wrapper.innerHTML = svg;
}

function handleUnitClick(unitId) {
  if (!selectedFacility) return;
  const unit = (selectedFacility.units || []).find(u => u.id === unitId);
  if (!unit) return;

  if (unit.current_status === "OCCUPIED") {
    showToast(`Unit ${unit.unit_identifier} is currently in session by an active tenant.`, "error");
    return;
  }

  if (unit.current_status === "MAINTENANCE") {
    showToast(`Unit ${unit.unit_identifier} is undergoing routine inspection.`, "warn");
    return;
  }

  openBookingModal(unit);
}

// ==========================================================================
// Instant Booking Modal & Reservation Flow
// ==========================================================================
function openBookingModal(unit) {
  selectedUnitForBooking = unit;
  const modal = document.getElementById("booking-modal");
  document.getElementById("booking-unit-title").innerText = `${unit.unit_identifier} (${unit.type.replace('_', ' ')})`;
  document.getElementById("booking-facility-title").innerText = selectedFacility ? selectedFacility.name : "Co-Working Hub";
  document.getElementById("booking-hourly-rate").innerText = `$${unit.hourly_price}/hr`;
  document.getElementById("booking-duration-select").value = "1";
  calculateBookingTotal();
  modal.classList.add("active");
}

function closeBookingModal() {
  document.getElementById("booking-modal").classList.remove("active");
}

function calculateBookingTotal() {
  if (!selectedUnitForBooking) return;
  const hours = parseInt(document.getElementById("booking-duration-select").value, 10);
  const total = (selectedUnitForBooking.hourly_price || 15) * hours;
  document.getElementById("booking-calc-total").innerText = `$${total.toFixed(2)}`;
}

async function confirmBooking() {
  if (!API.isAuthenticated()) {
    closeBookingModal();
    openAuthModal('login');
    showToast("Please sign in or register to complete your reservation.", "info");
    return;
  }

  if (!selectedUnitForBooking) return;
  const hours = parseInt(document.getElementById("booking-duration-select").value, 10);

  try {
    const booking = await API.createBooking(selectedUnitForBooking.id, hours);
    closeBookingModal();
    showToast(`Reservation Confirmed! Reference: ${booking.booking_code}`, "success");
    openQRPassModal(booking);
    refreshNotificationsBadge();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ==========================================================================
// Luxury Digital QR Boarding Pass
// ==========================================================================
function openQRPassModal(booking) {
  const modal = document.getElementById("qr-modal");
  document.getElementById("pass-code").innerText = booking.booking_code;
  document.getElementById("pass-unit").innerText = booking.unit_identifier;
  document.getElementById("pass-facility").innerText = booking.facility_name || (selectedFacility ? selectedFacility.name : "Workspace Hub");
  document.getElementById("pass-time").innerText = `${new Date(booking.start_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} – ${new Date(booking.end_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
  document.getElementById("pass-token-string").innerText = booking.qr_token;

  const checkInBtn = document.getElementById("btn-trigger-checkin");
  checkInBtn.onclick = () => simulateDeskCheckIn(booking.qr_token);

  modal.classList.add("active");
}

function closeQRModal() {
  document.getElementById("qr-modal").classList.remove("active");
}

async function simulateDeskCheckIn(qrToken) {
  try {
    const res = await API.checkIn(qrToken);
    showToast(res.message, "success");
    closeQRModal();
    refreshNotificationsBadge();
    if (selectedFacility) {
      loadFloorMapTab();
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ==========================================================================
// Space Details Modal
// ==========================================================================
async function openSpaceDetailsModal(facilityId) {
  try {
    const space = await API.getSpaceDetail(facilityId);
    const modal = document.getElementById("space-details-modal");
    document.getElementById("modal-detail-name").innerText = space.name;
    document.getElementById("modal-detail-address").innerText = `${space.address}, ${space.city}`;
    document.getElementById("modal-detail-img").src = space.image_url;
    document.getElementById("modal-detail-desc").innerText = space.description;
    document.getElementById("modal-detail-area").innerText = `${space.total_area_sqft.toLocaleString()} sq ft`;
    document.getElementById("modal-detail-hours").innerText = `${space.opening_time} – ${space.closing_time} ${space.is_24x7 ? '(24/7 Access)' : ''}`;

    const amenitiesList = document.getElementById("modal-detail-amenities");
    amenitiesList.innerHTML = (space.amenities || []).map(a => `
      <div style="background: #f8fafc; border: 1px solid var(--border-subtle); padding: 8px 12px; border-radius: var(--radius-sm); font-size: 0.85rem; font-weight: 600;">
        ✓ ${a.name}
      </div>
    `).join('');

    const unitsList = document.getElementById("modal-detail-units");
    unitsList.innerHTML = (space.units || []).map(u => `
      <tr>
        <td><strong>${u.unit_identifier}</strong></td>
        <td>${u.type.replace('_', ' ')} (${u.capacity} Pax)</td>
        <td><span class="badge badge-${u.current_status.toLowerCase()}">${u.current_status}</span></td>
        <td><strong>$${u.hourly_price}/hr</strong></td>
        <td>
          ${u.current_status === 'VACANT' ? 
            `<button class="btn btn-primary btn-sm" onclick="closeSpaceDetailsModal(); openFloorMapForSpace('${space.id}'); openBookingModal(${JSON.stringify(u).replace(/"/g, '&quot;')});">Reserve</button>` : 
            `<span style="color: var(--text-muted); font-size: 0.8rem;">In Use</span>`
          }
        </td>
      </tr>
    `).join('');

    modal.classList.add("active");
  } catch (err) {
    showToast(err.message, "error");
  }
}

function closeSpaceDetailsModal() {
  document.getElementById("space-details-modal").classList.remove("active");
}

// ==========================================================================
// Compare Spaces Modal
// ==========================================================================
function openCompareModal() {
  const modal = document.getElementById("compare-modal");
  const container = document.getElementById("compare-matrix-container");

  if (currentSpaces.length === 0) {
    showToast("No spaces loaded to compare.", "info");
    return;
  }

  let tableHtml = `
    <table class="enterprise-table">
      <thead>
        <tr>
          <th>Metric / Amenity</th>
          ${currentSpaces.map(s => `<th>${s.name}<br><small style="font-weight: 500;">${s.city}</small></th>`).join('')}
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Total Area Size</strong></td>
          ${currentSpaces.map(s => `<td>${s.total_area_sqft.toLocaleString()} sq ft</td>`).join('')}
        </tr>
        <tr>
          <td><strong>Atmosphere & Vibe</strong></td>
          ${currentSpaces.map(s => `<td><span class="badge">${s.work_style}</span></td>`).join('')}
        </tr>
        <tr>
          <td><strong>Live Available Units</strong></td>
          ${currentSpaces.map(s => `<td style="color: var(--telemetry-vacant); font-weight: 800;">${s.vacant_units_count} Vacant Desks</td>`).join('')}
        </tr>
        <tr>
          <td><strong>Min Hourly Pricing</strong></td>
          ${currentSpaces.map(s => `<td><strong>$${Math.min(...(s.units||[]).map(u => u.hourly_price||999), 12)}/hr</strong></td>`).join('')}
        </tr>
        <tr>
          <td><strong>Enterprise Gigabit Wi-Fi</strong></td>
          ${currentSpaces.map(s => `<td>${(s.amenities||[]).some(a=>a.code==='GIGABIT_WIFI') ? '✅ Yes (500+ Mbps)' : '❌'}</td>`).join('')}
        </tr>
        <tr>
          <td><strong>100% DG Power Backup</strong></td>
          ${currentSpaces.map(s => `<td>${(s.amenities||[]).some(a=>a.code==='POWER_BACKUP') ? '✅ Yes' : '❌'}</td>`).join('')}
        </tr>
        <tr>
          <td><strong>Acoustic Phone Booths</strong></td>
          ${currentSpaces.map(s => `<td>${(s.amenities||[]).some(a=>a.code==='PHONE_BOOTHS') ? '✅ Yes' : '❌'}</td>`).join('')}
        </tr>
        <tr>
          <td><strong>Valet & EV Parking</strong></td>
          ${currentSpaces.map(s => `<td>${(s.amenities||[]).some(a=>a.code==='VALET_PARKING') ? '✅ Yes' : '❌'}</td>`).join('')}
        </tr>
      </tbody>
    </table>
  `;

  container.innerHTML = tableHtml;
  modal.classList.add("active");
}

function closeCompareModal() {
  document.getElementById("compare-modal").classList.remove("active");
}

// ==========================================================================
// Notification Center (Simulated Email & SMS Alerts)
// ==========================================================================
async function openNotificationsDrawer() {
  const modal = document.getElementById("notifications-modal");
  const list = document.getElementById("notifications-list");

  if (!API.isAuthenticated()) {
    openAuthModal('login');
    showToast("Sign in to review your dispatched notifications.", "info");
    return;
  }

  try {
    const notifs = await API.getNotifications();
    if (notifs.length === 0) {
      list.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted);">No notification logs found.</div>`;
    } else {
      list.innerHTML = notifs.map(n => `
        <div style="background: #f8fafc; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 14px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span class="badge ${n.type === 'SMS' ? 'badge-reserved' : 'badge-vacant'}">${n.channel}</span>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${new Date(n.created_at).toLocaleTimeString()}</span>
          </div>
          <div style="font-weight: 800; font-size: 0.95rem; color: var(--brand-navy); margin-bottom: 4px;">${n.title}</div>
          <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">${n.message}</p>
        </div>
      `).join('');
    }
    modal.classList.add("active");
  } catch (err) {
    showToast(err.message, "error");
  }
}

function closeNotificationsModal() {
  document.getElementById("notifications-modal").classList.remove("active");
}

async function refreshNotificationsBadge() {
  const badge = document.getElementById("nav-bell-badge");
  if (!badge) return;

  if (API.isAuthenticated()) {
    try {
      const notifs = await API.getNotifications();
      badge.innerText = notifs.length;
      badge.style.display = notifs.length > 0 ? "flex" : "none";
    } catch {
      badge.style.display = "none";
    }
  } else {
    badge.style.display = "none";
  }
}

// ==========================================================================
// User Bookings Tab
// ==========================================================================
async function loadMyBookings() {
  const container = document.getElementById("my-bookings-container");
  if (!container) return;

  try {
    const bookings = await API.getMyBookings();
    if (bookings.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 60px 20px; background: white; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
          <h3>No Active Reservations</h3>
          <p style="color: var(--text-muted); margin-top: 8px;">Explore workspaces and reserve your next desk on the Explore tab.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <table class="enterprise-table">
        <thead>
          <tr>
            <th>Booking Reference</th>
            <th>Workspace Unit</th>
            <th>Facility & Location</th>
            <th>Schedule</th>
            <th>Live Status</th>
            <th>Total Cost</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${bookings.map(b => `
            <tr>
              <td><strong style="color: var(--brand-blue);">${b.booking_code}</strong></td>
              <td>${b.unit_identifier} (${b.unit_type})</td>
              <td>${b.facility_name}</td>
              <td>${new Date(b.start_time).toLocaleDateString()} ${new Date(b.start_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</td>
              <td><span class="badge badge-${b.status.toLowerCase()}">${b.status.replace('_', ' ')}</span></td>
              <td><strong>$${b.total_amount}</strong></td>
              <td>
                <div style="display: flex; gap: 6px;">
                  <button class="btn btn-outline btn-sm" onclick='openQRPassModal(${JSON.stringify(b)})'>View Keycard</button>
                  ${b.status === 'CONFIRMED' ? `<button class="btn btn-outline btn-sm" style="color: var(--telemetry-occupied);" onclick="cancelBooking('${b.id}')">Cancel</button>` : ''}
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (err) {
    container.innerHTML = `<div style="color: red; padding: 20px;">${err.message}</div>`;
  }
}

async function cancelBooking(id) {
  if (!confirm("Are you sure you want to release this workspace reservation?")) return;
  try {
    await API.cancelBooking(id);
    showToast("Booking cancelled and workspace released immediately.", "info");
    loadMyBookings();
    refreshNotificationsBadge();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ==========================================================================
// Space Owner Operations Hub & Customer Inquiry Response
// ==========================================================================
async function loadHostHub() {
  const container = document.getElementById("host-hub-container");
  if (!container) return;

  try {
    const bookings = await API.getOwnerBookings();
    const inquiries = await API.getInquiries();

    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
        <h3 style="font-size: 1.3rem; font-weight: 800; color: var(--brand-navy);">Incoming Reservations & Floor Controls</h3>
        <button class="btn btn-primary btn-sm" onclick="openNewSpaceModal()">+ Add New Space Listing</button>
      </div>

      <table class="enterprise-table" style="margin-bottom: 40px;">
        <thead>
          <tr>
            <th>Reference</th>
            <th>Client</th>
            <th>Unit</th>
            <th>Facility</th>
            <th>Scheduled Slot</th>
            <th>Current Status</th>
            <th>Live Desk State Controls</th>
          </tr>
        </thead>
        <tbody>
          ${bookings.length === 0 ? `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No current bookings for your spaces.</td></tr>` : 
            bookings.map(b => `
            <tr>
              <td><strong>${b.booking_code}</strong></td>
              <td>${b.client_name}<br><small style="color: var(--text-muted);">${b.client_email}</small></td>
              <td>${b.unit_identifier}</td>
              <td>${b.facility_name}</td>
              <td>${new Date(b.start_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</td>
              <td><span class="badge badge-reserved">${b.status}</span></td>
              <td>
                <div style="display: flex; gap: 4px;">
                  <button class="btn btn-outline btn-sm" onclick="toggleUnitMaintenance('${b.unit_id}', 'MAINTENANCE')">Maintenance</button>
                  <button class="btn btn-outline btn-sm" onclick="toggleUnitMaintenance('${b.unit_id}', 'VACANT')">Force Vacant</button>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>

      <!-- Meeting & Expectation Matching Queue -->
      <h3 style="font-size: 1.3rem; font-weight: 800; color: var(--brand-navy); margin-bottom: 14px;">
        Customer Inquiries & Expectation Matching Queue
      </h3>
      <table class="enterprise-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Seeker</th>
            <th>Facility Destination</th>
            <th>Team Size</th>
            <th>Requirements & Style</th>
            <th>Status</th>
            <th>Manager Action</th>
          </tr>
        </thead>
        <tbody>
          ${inquiries.length === 0 ? `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No inquiries submitted yet.</td></tr>` : 
            inquiries.map(inq => `
            <tr>
              <td>${new Date(inq.created_at).toLocaleDateString()}</td>
              <td><strong>${inq.user_name || 'Prospect'}</strong><br><small style="color: var(--text-muted);">${inq.user_email || ''}</small></td>
              <td>${inq.facility_name}</td>
              <td><strong>${inq.team_size} Pax</strong></td>
              <td>
                <div style="font-weight: 600; font-size: 0.85rem;">${inq.subject}</div>
                <div style="color: var(--text-secondary); font-size: 0.8rem; margin-top: 2px;">${inq.message}</div>
                ${inq.response_notes ? `<div style="background: #ecfdf5; border: 1px solid #a7f3d0; padding: 4px 8px; border-radius: 4px; font-size: 0.78rem; color: #065f46; margin-top: 6px;"><strong>Your Response:</strong> ${inq.response_notes}</div>` : ''}
              </td>
              <td>
                <span class="badge ${inq.status === 'RESPONDED' ? 'badge-vacant' : 'badge-reserved'}">
                  ${inq.status}
                </span>
              </td>
              <td>
                ${inq.status === 'OPEN' ? 
                  `<button class="btn btn-primary btn-sm" onclick='openRespondInquiryModal(${JSON.stringify(inq)})'>Reply & Quote</button>` : 
                  `<span style="color: var(--telemetry-vacant); font-weight: 700; font-size: 0.8rem;">✓ Resolved</span>`
                }
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (err) {
    container.innerHTML = `<div style="color: red; padding: 20px;">${err.message}</div>`;
  }
}

function openRespondInquiryModal(inquiry) {
  activeInquiryForResponse = inquiry;
  const modal = document.getElementById("respond-inquiry-modal");
  document.getElementById("resp-inq-seeker").innerText = `${inquiry.user_name || 'Prospect'} (${inquiry.user_email || 'Email'})`;
  document.getElementById("resp-inq-facility").innerText = inquiry.facility_name;
  document.getElementById("resp-inq-request").innerText = inquiry.message;
  document.getElementById("resp-inq-notes").value = "";
  modal.classList.add("active");
}

function closeRespondInquiryModal() {
  document.getElementById("respond-inquiry-modal").classList.remove("active");
}

async function handleRespondInquirySubmit(e) {
  e.preventDefault();
  if (!activeInquiryForResponse) return;
  const notes = document.getElementById("resp-inq-notes").value.trim();

  try {
    await API.respondToInquiry(activeInquiryForResponse.id, notes);
    showToast("Response and formal quotation transmitted to prospect via Email and SMS!", "success");
    closeRespondInquiryModal();
    loadHostHub();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function toggleUnitMaintenance(unitId, status) {
  try {
    await API.updateUnitStatus(unitId, status);
    showToast(`Workspace unit status manually set to ${status}. Live telemetry updated.`, "success");
    loadHostHub();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function openNewSpaceModal() {
  document.getElementById("new-space-modal").classList.add("active");
}

function closeNewSpaceModal() {
  document.getElementById("new-space-modal").classList.remove("active");
}

async function handleCreateSpace(e) {
  e.preventDefault();
  const name = document.getElementById("new-space-name").value;
  const address = document.getElementById("new-space-address").value;
  const city = document.getElementById("new-space-city").value;
  const area = parseInt(document.getElementById("new-space-area").value, 10);
  const work_style = document.getElementById("new-space-style").value;
  const desc = document.getElementById("new-space-desc").value;

  try {
    await API.createSpace({ name, address, city, total_area_sqft: area, work_style, description: desc });
    showToast("Co-working facility listing published into directory!", "success");
    closeNewSpaceModal();
    loadSpaces();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ==========================================================================
// Admin Telemetry & Platform KPI Monitor
// ==========================================================================
async function loadAdminMetrics() {
  const container = document.getElementById("admin-metrics-container");
  if (!container) return;

  try {
    const data = await API.getAdminMetrics();
    container.innerHTML = `
      <div class="kpi-grid">
        <div class="kpi-stat-card">
          <div class="kpi-stat-label">REGISTERED USERS</div>
          <div class="kpi-stat-value">${data.total_users}</div>
        </div>
        <div class="kpi-stat-card">
          <div class="kpi-stat-label">ACTIVE HUBS</div>
          <div class="kpi-stat-value">${data.total_facilities}</div>
        </div>
        <div class="kpi-stat-card">
          <div class="kpi-stat-label">FLOOR OCCUPANCY</div>
          <div class="kpi-stat-value" style="color: var(--telemetry-occupied);">${data.occupancy_rate_percent}%</div>
        </div>
        <div class="kpi-stat-card">
          <div class="kpi-stat-label">RECLAIMED NO-SHOWS</div>
          <div class="kpi-stat-value" style="color: var(--telemetry-vacant);">${data.no_show_released_count}</div>
        </div>
      </div>

      <h3 style="font-size: 1.25rem; font-weight: 800; color: var(--brand-navy); margin-top: 30px; margin-bottom: 14px;">
        Live Telemetry Ingestion Log (Sub-Second Audit Trail)
      </h3>
      <table class="enterprise-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Workspace Unit</th>
            <th>Facility</th>
            <th>Telemetry Ingestion Source</th>
            <th>Resulting State</th>
          </tr>
        </thead>
        <tbody>
          ${data.recent_telemetry.map(t => `
            <tr>
              <td>${new Date(t.captured_at).toLocaleTimeString()}</td>
              <td><strong>${t.unit_identifier}</strong></td>
              <td>${t.facility_name}</td>
              <td><code>${t.source}</code></td>
              <td><span class="badge badge-${t.event_state.toLowerCase()}">${t.event_state}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (err) {
    container.innerHTML = `<div style="color: red; padding: 20px;">${err.message}</div>`;
  }
}

// ==========================================================================
// Inquiries & Expectation Matching
// ==========================================================================
function openInquiryModal(facilityId, facilityName) {
  document.getElementById("inquiry-facility-id").value = facilityId;
  document.getElementById("inquiry-space-name").innerText = facilityName;
  document.getElementById("inquiry-modal").classList.add("active");
}

function closeInquiryModal() {
  document.getElementById("inquiry-modal").classList.remove("active");
}

async function handleInquirySubmit(e) {
  e.preventDefault();
  if (!API.isAuthenticated()) {
    closeInquiryModal();
    openAuthModal('login');
    showToast("Please sign in to submit formal inquiries.", "info");
    return;
  }

  const facilityId = document.getElementById("inquiry-facility-id").value;
  const teamSize = parseInt(document.getElementById("inquiry-team-size").value, 10);
  const message = document.getElementById("inquiry-message").value;

  try {
    await API.submitInquiry({
      facility_id: facilityId,
      team_size: teamSize,
      message,
      subject: `Enterprise Workspace Inquiry (${teamSize} persons)`
    });
    closeInquiryModal();
    showToast("Custom inquiry transmitted! Space community manager will reply promptly.", "success");
    refreshNotificationsBadge();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ==========================================================================
// Real-Time SSE Telemetry Event Handler
// ==========================================================================
function initSSEListener() {
  window.addEventListener("coworking:unit_update", (e) => {
    const update = e.detail;
    showToast(`Telemetry Event: Unit ${update.unit_identifier || update.unit_id} is now ${update.status}`, "info");

    if (selectedFacility && selectedFacility.id === update.facility_id) {
      const node = document.getElementById(`unit-node-${update.unit_id}`);
      if (node) {
        node.className.baseVal = `desk-node status-${update.status}`;
        node.style.transform = "scale(1.08)";
        setTimeout(() => { node.style.transform = "none"; }, 300);
      }
    }

    loadSpaces();
    refreshNotificationsBadge();
  });
}
