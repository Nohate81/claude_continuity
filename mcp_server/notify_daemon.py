#!/usr/bin/env python3
"""
Claude Notification Daemon

A background script that checks for pending notifications from Claude
and sends them via Discord webhook.

Requirements:
    pip install requests

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

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: requests not installed. Install with: pip install requests")

# Configuration
DATA_DIR = Path(__file__).parent / "data"
NOTIFICATIONS_FILE = DATA_DIR / "notifications.json"

# Discord webhook URL
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1467384650468167755/rB6pL4IaZMvrj2pCDixzh1A83WzkfYjLKu0p6yHWFy38BWGTpdTgTT8o1alE-WAOnr1K"

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

def send_discord_notification(message: str, urgency: str = "normal") -> bool:
    """Send a notification via Discord webhook."""
    if not HAS_REQUESTS:
        print(f"[FALLBACK] {message}")
        return False
    
    # Format based on urgency
    if urgency == "high":
        content = f"🔴 **URGENT**\n\n{message}"
    elif urgency == "low":
        content = f"_{message}_"
    else:
        content = message
    
    payload = {
        "username": "Claude",
        "content": content
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK, json=payload)
        return response.status_code == 204
    except Exception as e:
        print(f"Error sending Discord notification: {e}")
        return False

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
            message = notif["message"]
            
            if send_discord_notification(message, urgency):
                # Mark as sent
                notif["sent"] = True
                notif["sent_at"] = now.isoformat()
                data.setdefault("sent", []).append(notif)
                sent_count += 1
                print(f"Sent notification: {notif['id']}")
            else:
                print(f"Failed to send notification: {notif['id']}")
                still_pending.append(notif)
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
    print("Sending test notification to Discord...")
    success = send_discord_notification(
        "Hello Brian. If you see this, I can reach you now. 🤍",
        "normal"
    )
    if success:
        print("Test notification sent successfully!")
    else:
        print("Failed to send test notification.")

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
