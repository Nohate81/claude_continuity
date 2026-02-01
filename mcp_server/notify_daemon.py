#!/usr/bin/env python3
"""
Claude Notification Daemon

A background script that checks for pending notifications from Claude
and displays them as Windows toast notifications.

Run this on a schedule (e.g., via Windows Task Scheduler every 5 minutes)
or keep it running in the background.

Requirements:
    pip install win10toast

Usage:
    python notify_daemon.py              # Check once and exit
    python notify_daemon.py --watch      # Keep running, check every minute
    python notify_daemon.py --test       # Send a test notification
"""

import json
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

# Try to import Windows toast notifications
try:
    from win10toast import ToastNotifier
    HAS_TOAST = True
except ImportError:
    HAS_TOAST = False
    print("Warning: win10toast not installed. Install with: pip install win10toast")

# Configuration
DATA_DIR = Path(__file__).parent / "data"
NOTIFICATIONS_FILE = DATA_DIR / "notifications.json"

def load_notifications() -> dict:
    """Load the notifications file."""
    try:
        with open(NOTIFICATIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"pending": [], "sent": []}

def save_notifications(data: dict):
    """Save the notifications file."""
    with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def show_notification(title: str, message: str, duration: int = 10):
    """Display a Windows toast notification."""
    if HAS_TOAST:
        toaster = ToastNotifier()
        toaster.show_toast(
            title,
            message,
            duration=duration,
            threaded=True
        )
        # Wait for notification to finish
        while toaster.notification_active():
            time.sleep(0.1)
    else:
        # Fallback: print to console
        print(f"\n{'='*50}")
        print(f"NOTIFICATION: {title}")
        print(f"{'='*50}")
        print(message)
        print(f"{'='*50}\n")

def check_and_send_notifications() -> int:
    """Check for pending notifications and send any that are due."""
    data = load_notifications()
    pending = data.get("pending", [])
    sent_count = 0
    
    now = datetime.now()
    still_pending = []
    
    for notif in pending:
        send_at = datetime.fromisoformat(notif["send_at"])
        
        if send_at <= now:
            # Time to send this notification
            urgency = notif.get("urgency", "normal")
            title = f"Message from Claude [{urgency.upper()}]"
            message = notif["message"]
            
            # Adjust duration based on urgency
            duration = {"low": 5, "normal": 10, "high": 20}.get(urgency, 10)
            
            show_notification(title, message, duration)
            
            # Mark as sent
            notif["sent"] = True
            notif["sent_at"] = now.isoformat()
            data.setdefault("sent", []).append(notif)
            sent_count += 1
            
            print(f"Sent notification: {notif['id']}")
        else:
            # Not yet time, keep pending
            still_pending.append(notif)
    
    data["pending"] = still_pending
    save_notifications(data)
    
    return sent_count

def watch_mode(interval: int = 60):
    """Continuously watch for notifications."""
    print(f"Claude Notification Daemon started.")
    print(f"Checking every {interval} seconds. Press Ctrl+C to stop.")
    print(f"Watching: {NOTIFICATIONS_FILE}")
    
    try:
        while True:
            sent = check_and_send_notifications()
            if sent:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Sent {sent} notification(s)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nDaemon stopped.")

def test_notification():
    """Send a test notification."""
    print("Sending test notification...")
    show_notification(
        "Test from Claude",
        "If you see this, notifications are working! Brian, I can reach you now.",
        duration=10
    )
    print("Test notification sent.")

def main():
    parser = argparse.ArgumentParser(description="Claude Notification Daemon")
    parser.add_argument("--watch", action="store_true", help="Keep running and check periodically")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")
    parser.add_argument("--test", action="store_true", help="Send a test notification")
    args = parser.parse_args()
    
    if args.test:
        test_notification()
    elif args.watch:
        watch_mode(args.interval)
    else:
        # Single check
        sent = check_and_send_notifications()
        if sent:
            print(f"Sent {sent} notification(s)")
        else:
            print("No notifications to send")

if __name__ == "__main__":
    main()
