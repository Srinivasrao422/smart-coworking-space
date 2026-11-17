"""
Real-time Telemetry, SSE Event Streaming Hub, and Auto-Release Scheduler.
Maintains persistent SSE client subscribers and runs background no-show release daemon.
"""

import threading
import time
import queue
import json
import datetime
from .database import get_db

class TelemetryHub:
    def __init__(self):
        self._subscribers: set[queue.Queue] = set()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._daemon_thread = None

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            self._subscribers.discard(q)

    def broadcast(self, event_type: str, data: dict):
        """Broadcasts a JSON event to all connected SSE clients."""
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        with self._lock:
            dead_queues = []
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead_queues.append(q)
            for q in dead_queues:
                self._subscribers.discard(q)

    def start_auto_release_daemon(self, interval_seconds: int = 15, grace_minutes: int = 15):
        """Starts background daemon to automatically reclaim no-show bookings."""
        if self._daemon_thread and self._daemon_thread.is_alive():
            return

        def daemon_worker():
            while not self._stop_event.is_set():
                try:
                    self._check_and_release_no_shows(grace_minutes)
                except Exception as e:
                    print(f"[TelemetryHub] Error in auto-release daemon: {e}")
                time.sleep(interval_seconds)

        self._daemon_thread = threading.Thread(target=daemon_worker, daemon=True, name="AutoReleaseDaemon")
        self._daemon_thread.start()

    def _check_and_release_no_shows(self, grace_minutes: int):
        conn = get_db()
        cursor = conn.cursor()

        # Find bookings where start_time + grace_minutes < now, but still CONFIRMED and not checked in
        cutoff_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=grace_minutes)
        cutoff_iso = cutoff_dt.isoformat()

        cursor.execute("""
        SELECT b.id, b.booking_code, b.unit_id, b.user_id, u.facility_id, u.unit_identifier
        FROM bookings b
        JOIN workspace_units u ON b.unit_id = u.id
        WHERE b.status = 'CONFIRMED'
          AND b.check_in_time IS NULL
          AND b.start_time <= ?;
        """, (cutoff_iso,))
        
        expired_bookings = cursor.fetchall()
        for b in expired_bookings:
            b_id = b["id"]
            unit_id = b["unit_id"]
            facility_id = b["facility_id"]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # 1. Update Booking Status
            cursor.execute("""
            UPDATE bookings 
            SET status = 'NO_SHOW_RELEASED', cancellation_reason = 'Check-in grace period expired'
            WHERE id = ?;
            """, (b_id,))

            # 2. Release Workspace Unit back to VACANT
            cursor.execute("""
            UPDATE workspace_units 
            SET current_status = 'VACANT' 
            WHERE id = ?;
            """, (unit_id,))

            # 3. Log Telemetry Audit
            cursor.execute("""
            INSERT INTO telemetry_logs (unit_id, source, event_state, captured_at, metadata)
            VALUES (?, 'SYSTEM_AUTO_RELEASE', 'VACANT', ?, ?);
            """, (unit_id, now_iso, json.dumps({"booking_id": b_id, "code": b["booking_code"]})))

            conn.commit()

            # 4. Broadcast live update to all connected maps
            self.broadcast("unit_update", {
                "unit_id": unit_id,
                "facility_id": facility_id,
                "status": "VACANT",
                "reason": "AUTO_RELEASED",
                "unit_identifier": b["unit_identifier"],
                "timestamp": now_iso
            })
            print(f"[TelemetryHub] Auto-released unit {b['unit_identifier']} due to no-show for booking {b['booking_code']}")

        conn.close()

# Global Singleton Instance
hub = TelemetryHub()
