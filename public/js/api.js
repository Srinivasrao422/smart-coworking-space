/**
 * API Client for Smart Co-Working Space Management
 * Fully authenticated, handles REST endpoints, error states, and session persistence.
 */

const API = {
  getToken() {
    return localStorage.getItem("coworking_token");
  },

  getUser() {
    const raw = localStorage.getItem("coworking_user");
    return raw ? JSON.parse(raw) : null;
  },

  setSession(token, user) {
    localStorage.setItem("coworking_token", token);
    localStorage.setItem("coworking_user", JSON.stringify(user));
  },

  clearSession() {
    localStorage.removeItem("coworking_token");
    localStorage.removeItem("coworking_user");
  },

  isAuthenticated() {
    return !!this.getToken();
  },

  async request(path, options = {}) {
    const headers = options.headers || {};
    headers["Content-Type"] = "application/json";

    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(path, {
      ...options,
      headers
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || `Request failed with status ${response.status}`);
    }
    return data;
  },

  // Auth Endpoints
  async login(email, password) {
    const res = await this.request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
    this.setSession(res.token, res.user);
    return res;
  },

  async register(data) {
    const res = await this.request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(data)
    });
    this.setSession(res.token, res.user);
    return res;
  },

  // Spaces Endpoints
  async getSpaces(filters = {}) {
    const params = new URLSearchParams();
    if (filters.city && filters.city !== "all") params.append("city", filters.city);
    if (filters.team_bracket && filters.team_bracket !== "all") params.append("team_bracket", filters.team_bracket);
    if (filters.budget_bracket && filters.budget_bracket !== "all") params.append("budget_bracket", filters.budget_bracket);
    if (filters.area_bracket && filters.area_bracket !== "all") params.append("area_bracket", filters.area_bracket);
    if (filters.work_style && filters.work_style !== "all") params.append("work_style", filters.work_style);
    if (filters.unit_type && filters.unit_type !== "all") params.append("unit_type", filters.unit_type);
    if (filters.amenities && filters.amenities.length) params.append("amenities", filters.amenities.join(","));

    return this.request(`/api/spaces?${params.toString()}`);
  },

  async getSpaceDetail(id) {
    return this.request(`/api/spaces/${id}`);
  },

  async createSpace(data) {
    return this.request("/api/spaces", {
      method: "POST",
      body: JSON.stringify(data)
    });
  },

  // Booking Endpoints
  async createBooking(unitId, hours = 1) {
    return this.request("/api/bookings", {
      method: "POST",
      body: JSON.stringify({ unit_id: unitId, hours })
    });
  },

  async getMyBookings() {
    return this.request("/api/bookings/my");
  },

  async getOwnerBookings() {
    return this.request("/api/bookings/owner");
  },

  async cancelBooking(bookingId) {
    return this.request(`/api/bookings/${bookingId}/cancel`, {
      method: "PATCH"
    });
  },

  // Real-Time Telemetry & Check-in
  async checkIn(tokenOrCode) {
    return this.request("/api/telemetry/check-in", {
      method: "POST",
      body: JSON.stringify({ qr_token: tokenOrCode })
    });
  },

  async updateUnitStatus(unitId, status) {
    return this.request(`/api/units/${unitId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status })
    });
  },

  // Inquiries & Notifications
  async submitInquiry(data) {
    return this.request("/api/inquiries", {
      method: "POST",
      body: JSON.stringify(data)
    });
  },

  async getInquiries() {
    return this.request("/api/inquiries");
  },

  async respondToInquiry(inquiryId, responseNotes) {
    return this.request(`/api/inquiries/${inquiryId}/respond`, {
      method: "PATCH",
      body: JSON.stringify({ response_notes: responseNotes })
    });
  },

  async getNotifications() {
    return this.request("/api/notifications");
  },

  async getAdminMetrics() {
    return this.request("/api/admin/metrics");
  }
};
