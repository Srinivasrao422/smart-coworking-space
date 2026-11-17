/**
 * Real-Time Server-Sent Events (SSE) Client
 * Establishes persistent telemetry stream to receive sub-second workspace status transitions.
 */

const TelemetryStream = {
  eventSource: null,
  reconnectDelay: 2000,

  connect() {
    if (this.eventSource) {
      this.eventSource.close();
    }

    console.log("[TelemetryStream] Connecting to /api/telemetry/stream...");
    this.eventSource = new EventSource("/api/telemetry/stream");

    this.eventSource.onopen = () => {
      console.log("[TelemetryStream] Connected to live telemetry feed.");
      const badge = document.getElementById("live-telemetry-badge");
      if (badge) {
        badge.style.display = "inline-flex";
      }
    };

    this.eventSource.addEventListener("unit_update", (e) => {
      try {
        const data = JSON.parse(e.data);
        console.log("[TelemetryStream] Live unit update:", data);
        window.dispatchEvent(new CustomEvent("coworking:unit_update", { detail: data }));
      } catch (err) {
        console.error("[TelemetryStream] Parse error:", err);
      }
    });

    this.eventSource.onerror = (err) => {
      console.warn("[TelemetryStream] Connection dropped, reconnecting in", this.reconnectDelay, "ms...");
      this.eventSource.close();
      setTimeout(() => this.connect(), this.reconnectDelay);
    };
  }
};
