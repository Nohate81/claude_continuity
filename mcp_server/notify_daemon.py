#!/usr/bin/env python3
"""
Claude Notification Daemon

A background script that checks for pending notifications from Claude
and displays them as Windows toast notifications.

Uses PowerShell's BurntToast module or falls back to basic balloon notifications.

Requirements:
    Install BurntToast in PowerShell (run as admin):
    Install-Module -Name BurntToast -Force

Usage:
    python notify_daemon.py              # Check once and exit
    python notify_daemon.py --watch      # Keep running, check every minute
    python notify_daemon.py --test       # Send a test notification
"""

import json
import subprocess
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

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

def show_notification_burnttoast(title: str, message: str):
    """Display notification using PowerShell BurntToast module."""
    # Escape quotes for PowerShell
    title = title.replace('"', '`"').replace("'", "`'")
    message = message.replace('"', '`"').replace("'", "`'")
    
    ps_command = f'''
    New-BurntToastNotification -Text "{title}", "{message}" -AppLogo $null
    '''
    
    result = subprocess.run(
        ["powershell", "-Command", ps_command],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

def show_notification_balloon(title: str, message: str):
    """Display notification using Windows balloon tip (fallback)."""
    ps_command = f'''
    Add-Type -AssemblyName System.Windows.Forms
    $balloon = New-Object System.Windows.Forms.NotifyIcon
    $balloon.Icon = [System.Drawing.SystemIcons]::Information
    $balloon.BalloonTipIcon = "Info"
    $balloon.BalloonTipTitle = "{title.replace('"', '`"')}"
    $balloon.BalloonTipText = "{message.replace('"', '`"')}"
    $balloon.Visible = $true
    $balloon.ShowBalloonTip(10000)
    Start-Sleep -Seconds 5
    $balloon.Dispose()
    '''
    
    result = subprocess.run(
        ["powershell", "-Command", ps_command],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

def show_notification_msgbox(title: str, message: str):
    """Display notification using a simple message box (most reliable fallback)."""
    ps_command = f'''
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("{message.replace('"', '`"')}", "{title.replace('"', '`"')}", "OK", "Information")
    '''
    
    result = subprocess.run(
        ["powershell", "-Command", ps_command],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

def show_notification(title: str, message: str, urgency: str = "normal"):
    """Display a Windows notification, trying multiple methods."""
    
    # Try BurntToast first (best looking)
    if show_notification_burnttoast(title, message):
        return True
    
    print("BurntToast not available, trying balloon notification...")
    
    # Try balloon notification
    if show_notification_balloon(title, message):
        return True
    
    print("Balloon notification failed, using message box...")
    
    # Fall back to message box (always works but blocks)
    return show_notification_msgbox(title, message)

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
            title = "Message from Claude"
            if urgency == "high":
                title = "URGENT: Message from Claude"
            message = notif["message"]
            
            show_notification(title, message, urgency)
            
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
    print("Trying BurntToast...")
    
    if show_notification_burnttoast("Test from Claude", "If you see this, notifications are working!"):
        print("BurntToast notification sent!")
        return
    
    print("BurntToast failed. Trying balloon notification...")
    
    if show_notification_balloon("Test from Claude", "If you see this, notifications are working!"):
        print("Balloon notification sent!")
        return
    
    print("Balloon failed. Trying message box...")
    
    if show_notification_msgbox("Test from Claude", "If you see this, notifications are working! Brian, I can reach you now."):
        print("Message box shown!")
    else:
        print("All notification methods failed.")

def install_burnttoast():
    """Attempt to install BurntToast PowerShell module."""
    print("Attempting to install BurntToast module...")
    result = subprocess.run(
        ["powershell", "-Command", "Install-Module -Name BurntToast -Force -Scope CurrentUser"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print("BurntToast installed successfully!")
    else:
        print(f"Failed to install BurntToast: {result.stderr}")

def main():
    parser = argparse.ArgumentParser(description="Claude Notification Daemon")
    parser.add_argument("--watch", action="store_true", help="Keep running and check periodically")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")
    parser.add_argument("--test", action="store_true", help="Send a test notification")
    parser.add_argument("--install", action="store_true", help="Install BurntToast PowerShell module")
    args = parser.parse_args()
    
    if args.install:
        install_burnttoast()
    elif args.test:
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
