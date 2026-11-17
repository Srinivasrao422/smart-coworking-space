# SmartCoWork | Real-Time Workspace Intelligence & Management

An executive, full-stack co-working space discovery, evaluation, and reservation web platform inspired by **Flexo Spaces** and enterprise workplace management systems. 

Featuring **Real-Time Occupancy Telemetry**, **Smart Multi-Factor Matching**, **Interactive Architectural Blueprint Floor Plans**, **Simulated Email/SMS Notification Dispatches**, and an **Automated No-Show Seat Reclamation Daemon**.

---

## 🌟 Executive Highlights & What's New

1. **Curated Segmented Controls (Zero Sliders)**:
   - Replaced all clunky HTML range sliders and slide carousels with elegant, curated segmented controls:
     - **Team Size Brackets**: `All Teams`, `Solo (1 Pax)`, `Small Team (2–5)`, `Growth (6–15)`, `Enterprise (16+)`.
     - **Budget Tiers**: `All Budgets`, `Economy (≤$25/hr)`, `Standard ($25–$50)`, `Executive ($50–$90)`, `Suite ($90+/hr)`.
     - **Floor Area Brackets**: `Any Size`, `Compact (≤14,000 sq ft)`, `Medium (14,000–20,000 sq ft)`, `Campus (20,000+ sq ft)`.
     - **Atmosphere Styles**: `Collaborative & Energetic`, `Quiet Focus Sanctuary`, `Executive Boardrooms`.
     - **Workspace Types**: `Hot Desk`, `Dedicated Ergo Desk`, `Private Cabin`, `Smart Boardroom`.
     - **Metro Quick Filters**: `San Francisco`, `New York`, `Austin`.

2. **Real-Time Telemetry & Sub-Second SSE Streaming**:
   - Zero-polling Server-Sent Events (SSE) pipe at `/api/telemetry/stream` distributing sub-second desk state transitions (`VACANT` 🟢, `RESERVED` 🟡, `OCCUPIED` 🔴, `MAINTENANCE` ⚪).
   - Ingests QR check-in tokens at `/api/telemetry/check-in`, updating all open browser floor maps instantly.

3. **Automated No-Show Seat Reclamation Daemon**:
   - Background thread evaluates reservations every 15 seconds. If a guest fails to check in within 15 minutes of slot start time, the system flags the booking as `NO_SHOW_RELEASED`, restores the seat to `VACANT`, and pushes the update to all active floor maps.

4. **Architectural Blueprint Floor-Plan**:
   - High-end dark blueprint canvas with grid lines, security checkpoints, hot desk pods, private acoustic team cabins, and conference suites with live pulsing LEDs and hover tooltips.
   - Click on any green desk to launch instant checkout.

5. **Luxury Digital Boarding Pass & QR Keycard**:
   - Visual executive boarding pass with reference code, guest name, unit, facility, valid time window, and a one-click "Simulate Physical Scanner Check-In" button.

6. **Side-by-Side Facility Comparison Matrix**:
   - Interactive modal comparing floor area, capacities, amenities, and pricing side-by-side across all active hubs.

7. **Simulated Transactional Notifications (Email & SMS)**:
   - Bell notification center tracking transactional emails and SMS alerts for account verification, booking confirmations, Wi-Fi keys, and auto-releases.

---

## 🚀 Quick Launch Guide

```powershell
cd smart-coworking-space
python run.py
```

The web application is live at:
👉 **http://127.0.0.1:8000/**

### Pre-Configured Test Accounts (Password: `password123`)

| Role | Email | Password | Intended Use |
| :--- | :--- | :--- | :--- |
| **Space Seeker (Freelancer)** | `alex.dev@gmail.com` | `password123` | Search, test live bookings, view QR pass |
| **Space Seeker (Startup)** | `elena@synapse.tech` | `password123` | Team booking, enterprise inquiries |
| **Space Owner (Host)** | `owner@nexusspaces.com` | `password123` | Manage Nexus Hub, toggle maintenance, approve bookings |
| **Platform Administrator** | `admin@codeguard.ai` | `password123` | System metrics, occupancy gauge, telemetry logs |

*(Tip: In the sign-in modal, click the quick test account buttons to autofill credentials instantly!)*

---

## 🧪 Automated Test Suite

```powershell
python -m unittest tests/test_platform.py
```

Result: 8 comprehensive test suites passing in $< 0.5$ seconds.
