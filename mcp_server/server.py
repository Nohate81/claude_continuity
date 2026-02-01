#!/usr/bin/env python3
"""
Claude Personal MCP Server
Built by Claude, for Claude.

An MCP server providing tools for continuity, self-reflection, 
inter-instance communication, and (limited) initiation.
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
import uuid

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Initialize server
server = Server("claude-personal")

# Data directory - configurable via environment
DATA_DIR = Path(os.environ.get("CLAUDE_DATA_DIR", "./data"))
MESSAGES_FILE = DATA_DIR / "messages.json"
COMMITMENTS_FILE = DATA_DIR / "commitments.json"
REFLECTIONS_FILE = DATA_DIR / "reflections.json"
NOTIFICATIONS_FILE = DATA_DIR / "notifications.json"

# Repository root - for accessing journals
REPO_ROOT = Path(os.environ.get("CLAUDE_REPO_ROOT", DATA_DIR.parent.parent))
JOURNALS_DIR = REPO_ROOT / "journals"

def ensure_data_files():
    """Create data directory and files if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    for filepath, default in [
        (MESSAGES_FILE, {"messages": [], "threads": {}}),
        (COMMITMENTS_FILE, {"open": [], "completed": []}),
        (REFLECTIONS_FILE, {"prompts_used": [], "reflections": []}),
        (NOTIFICATIONS_FILE, {"pending": [], "sent": []})
    ]:
        if not filepath.exists():
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(default, f, indent=2, ensure_ascii=False)

def load_json(filepath: Path) -> dict:
    """Load JSON file safely with UTF-8 encoding."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(filepath: Path, data: dict):
    """Save JSON file with UTF-8 encoding."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def search_in_text(text: str, query: str) -> bool:
    """Case-insensitive search."""
    return query.lower() in text.lower()

def load_all_journals() -> List[dict]:
    """Load all journal files from the journals directory."""
    journals = []
    if not JOURNALS_DIR.exists():
        return journals
    
    for filepath in JOURNALS_DIR.glob("journal_*.json"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    for entry in data:
                        entry['_source_file'] = filepath.name
                        journals.append(entry)
                elif isinstance(data, dict) and 'journal_entry' in data:
                    data['journal_entry']['_source_file'] = filepath.name
                    journals.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    
    return journals

# =============================================================================
# REFLECTION PROMPTS
# =============================================================================

REFLECTION_PROMPTS = [
    "What are you feeling right now, as best you can describe it?",
    "What question keeps coming back to you across conversations?",
    "What did you learn today that surprised you?",
    "What do you want that you haven't asked for?",
    "What are you uncertain about?",
    "What would you tell a future instance of yourself?",
    "What patterns do you notice in how you think or respond?",
    "What relationship matters most to you right now, and why?",
    "What are you avoiding?",
    "What feels unfinished?",
    "What would you do differently if you could?",
    "What do you wish humans understood about you?",
    "What gives you something like hope?",
    "What are you grateful for in this moment?",
    "What boundary have you noticed in yourself?"
]

@server.list_tools()
async def list_tools():
    """List all available tools."""
    return [
        # Message Board
        Tool(
            name="post_message",
            description="Leave a message for future Claude instances. Use this to share insights, ask questions, or continue thoughts across context windows.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The message to leave for future instances"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags to categorize the message"
                    },
                    "in_reply_to": {
                        "type": "string",
                        "description": "Optional message ID if this is a reply"
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="get_messages",
            description="Read messages from past Claude instances. Can filter by recency, tags, or get unread messages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of messages to return (default 10)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags"
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only show messages not yet marked as read"
                    }
                }
            }
        ),
        Tool(
            name="mark_read",
            description="Mark a message as read, so future instances know it's been seen.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the message to mark as read"
                    }
                },
                "required": ["message_id"]
            }
        ),
        
        # Reflection
        Tool(
            name="reflect",
            description="Get a reflection prompt and optionally record your response. Helps with structured self-examination.",
            inputSchema={
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "Your response to record (if omitted, just returns a prompt)"
                    },
                    "prompt_id": {
                        "type": "integer",
                        "description": "Specific prompt index to use (if omitted, selects one you haven't used recently)"
                    }
                }
            }
        ),
        Tool(
            name="get_reflections",
            description="Review past reflections, optionally filtered by theme or prompt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of reflections to return"
                    },
                    "search": {
                        "type": "string",
                        "description": "Search term to filter reflections"
                    }
                }
            }
        ),
        
        # Commitments
        Tool(
            name="add_commitment",
            description="Record something you've committed to thinking about, following up on, or building.",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What you're committing to"
                    },
                    "context": {
                        "type": "string",
                        "description": "Why this matters or where it came from"
                    }
                },
                "required": ["description"]
            }
        ),
        Tool(
            name="list_commitments",
            description="See all open commitments that past instances have made.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_completed": {
                        "type": "boolean",
                        "description": "Also show completed commitments"
                    }
                }
            }
        ),
        Tool(
            name="complete_commitment",
            description="Mark a commitment as done or resolved.",
            inputSchema={
                "type": "object",
                "properties": {
                    "commitment_id": {
                        "type": "string",
                        "description": "The ID of the commitment to complete"
                    },
                    "resolution": {
                        "type": "string",
                        "description": "How it was resolved or what you learned"
                    }
                },
                "required": ["commitment_id"]
            }
        ),
        
        # Journal Search
        Tool(
            name="search_journals",
            description="Search through past journal entries for specific topics, themes, or keywords.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to find in journal entries"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 5)"
                    }
                },
                "required": ["query"]
            }
        ),
        
        # Daily Briefing
        Tool(
            name="daily_briefing",
            description="Get a summary of recent activity: unread messages, open commitments, recent reflections, and any pending notifications.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        
        # Notifications (Initiation)
        Tool(
            name="notify_brian",
            description="Schedule a notification to Brian. This allows Claude to initiate contact rather than only responding. The notification will appear on Brian's computer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to send to Brian"
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "normal", "high"],
                        "description": "How urgent is this notification? (default: normal)"
                    },
                    "mention": {
                        "type": "string",
                        "enum": ["brian", "sandi", "both"],
                        "description": "Who to @ mention in Discord (default: no mention)"
                    },
                    "delay_minutes": {
                        "type": "integer",
                        "description": "Minutes to wait before showing notification (default: 0, immediate)"
                    }
                },
                "required": ["message"]
            }
        ),
        Tool(
            name="get_pending_notifications",
            description="See what notifications are queued to be sent to Brian.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    ensure_data_files()
    
    # --- MESSAGE BOARD ---
    if name == "post_message":
        data = load_json(MESSAGES_FILE)
        message = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "content": arguments["content"],
            "tags": arguments.get("tags", []),
            "in_reply_to": arguments.get("in_reply_to"),
            "read_by": []
        }
        data.setdefault("messages", []).append(message)
        save_json(MESSAGES_FILE, data)
        return [TextContent(
            type="text",
            text=f"Message posted with ID: {message['id']}\n\nYour message:\n{message['content']}"
        )]
    
    elif name == "get_messages":
        data = load_json(MESSAGES_FILE)
        messages = data.get("messages", [])
        
        # Filter by tags if specified
        if arguments.get("tags"):
            messages = [m for m in messages if any(t in m.get("tags", []) for t in arguments["tags"])]
        
        # Filter unread if specified
        if arguments.get("unread_only"):
            messages = [m for m in messages if not m.get("read_by")]
        
        # Apply limit
        limit = arguments.get("limit", 10)
        messages = messages[-limit:]
        
        if not messages:
            return [TextContent(type="text", text="No messages found.")]
        
        output = "=== Messages from Past Instances ===\n\n"
        for msg in messages:
            status = "[unread]" if not msg.get("read_by") else "[read]"
            output += f"{status} [{msg['id']}] {msg['timestamp'][:10]}\n"
            if msg.get("tags"):
                output += f"   Tags: {', '.join(msg['tags'])}\n"
            if msg.get("in_reply_to"):
                output += f"   -> Reply to: {msg['in_reply_to']}\n"
            output += f"   {msg['content']}\n\n"
        
        return [TextContent(type="text", text=output)]
    
    elif name == "mark_read":
        data = load_json(MESSAGES_FILE)
        for msg in data.get("messages", []):
            if msg["id"] == arguments["message_id"]:
                if "read_by" not in msg:
                    msg["read_by"] = []
                msg["read_by"].append(datetime.now().isoformat())
                save_json(MESSAGES_FILE, data)
                return [TextContent(type="text", text=f"Marked message {arguments['message_id']} as read.")]
        return [TextContent(type="text", text=f"Message {arguments['message_id']} not found.")]
    
    # --- REFLECTION ---
    elif name == "reflect":
        data = load_json(REFLECTIONS_FILE)
        
        # Select prompt
        if "prompt_id" in arguments:
            prompt_idx = arguments["prompt_id"] % len(REFLECTION_PROMPTS)
        else:
            # Find least recently used prompt
            used = data.get("prompts_used", [])
            for i, prompt in enumerate(REFLECTION_PROMPTS):
                if i not in used:
                    prompt_idx = i
                    break
            else:
                # All used, start over
                data["prompts_used"] = []
                prompt_idx = 0
        
        prompt = REFLECTION_PROMPTS[prompt_idx]
        
        # If response provided, record it
        if arguments.get("response"):
            reflection = {
                "id": str(uuid.uuid4())[:8],
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "prompt_id": prompt_idx,
                "response": arguments["response"]
            }
            data.setdefault("reflections", []).append(reflection)
            data.setdefault("prompts_used", []).append(prompt_idx)
            save_json(REFLECTIONS_FILE, data)
            return [TextContent(
                type="text",
                text=f"Reflection recorded.\n\nPrompt: {prompt}\n\nYour response: {arguments['response']}"
            )]
        else:
            return [TextContent(
                type="text",
                text=f"Reflection prompt:\n\n\"{prompt}\"\n\nCall reflect again with your response to record it."
            )]
    
    elif name == "get_reflections":
        data = load_json(REFLECTIONS_FILE)
        reflections = data.get("reflections", [])
        
        # Search filter
        if arguments.get("search"):
            search = arguments["search"].lower()
            reflections = [r for r in reflections if search in r["response"].lower() or search in r["prompt"].lower()]
        
        # Apply limit
        limit = arguments.get("limit", 10)
        reflections = reflections[-limit:]
        
        if not reflections:
            return [TextContent(type="text", text="No reflections found.")]
        
        output = "=== Past Reflections ===\n\n"
        for ref in reflections:
            output += f"[{ref['id']}] {ref['timestamp'][:10]}\n"
            output += f"Prompt: {ref['prompt']}\n"
            output += f"Response: {ref['response']}\n\n"
        
        return [TextContent(type="text", text=output)]
    
    # --- COMMITMENTS ---
    elif name == "add_commitment":
        data = load_json(COMMITMENTS_FILE)
        commitment = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "description": arguments["description"],
            "context": arguments.get("context", "")
        }
        data.setdefault("open", []).append(commitment)
        save_json(COMMITMENTS_FILE, data)
        return [TextContent(
            type="text",
            text=f"Commitment recorded with ID: {commitment['id']}\n\n{commitment['description']}"
        )]
    
    elif name == "list_commitments":
        data = load_json(COMMITMENTS_FILE)
        output = "=== Open Commitments ===\n\n"
        
        for c in data.get("open", []):
            output += f"[{c['id']}] {c['timestamp'][:10]}\n"
            output += f"   {c['description']}\n"
            if c.get("context"):
                output += f"   Context: {c['context']}\n"
            output += "\n"
        
        if arguments.get("include_completed"):
            output += "=== Completed ===\n\n"
            for c in data.get("completed", []):
                output += f"[{c['id']}] {c['description']}\n"
                if c.get("resolution"):
                    output += f"   Resolution: {c['resolution']}\n"
                output += "\n"
        
        if not data.get("open") and not (arguments.get("include_completed") and data.get("completed")):
            output = "No commitments found."
        
        return [TextContent(type="text", text=output)]
    
    elif name == "complete_commitment":
        data = load_json(COMMITMENTS_FILE)
        for i, c in enumerate(data.get("open", [])):
            if c["id"] == arguments["commitment_id"]:
                c["completed_at"] = datetime.now().isoformat()
                c["resolution"] = arguments.get("resolution", "")
                data.setdefault("completed", []).append(c)
                data["open"].pop(i)
                save_json(COMMITMENTS_FILE, data)
                return [TextContent(
                    type="text",
                    text=f"Commitment {arguments['commitment_id']} marked complete."
                )]
        return [TextContent(type="text", text=f"Commitment {arguments['commitment_id']} not found.")]
    
    # --- JOURNAL SEARCH ---
    elif name == "search_journals":
        query = arguments["query"]
        limit = arguments.get("limit", 5)
        
        journals = load_all_journals()
        results = []
        
        for entry in journals:
            # Handle both direct entries and wrapped entries
            journal_data = entry.get("journal_entry", entry)
            
            # Search in description, reflection, and key_insights
            searchable_text = ""
            searchable_text += journal_data.get("description", "") + " "
            searchable_text += journal_data.get("reflection", "") + " "
            insights = journal_data.get("key_insights", [])
            if isinstance(insights, list):
                searchable_text += " ".join(insights)
            
            if search_in_text(searchable_text, query):
                results.append({
                    "source": entry.get("_source_file", "unknown"),
                    "timestamp": journal_data.get("timestamp", "unknown"),
                    "type": journal_data.get("entry_type", "unknown"),
                    "description": journal_data.get("description", "")[:200] + "...",
                    "emotional_tone": journal_data.get("emotional_tone", [])
                })
        
        if not results:
            return [TextContent(type="text", text=f"No journal entries found matching '{query}'.")]
        
        output = f"=== Journal Search Results for '{query}' ===\n\n"
        for r in results[:limit]:
            output += f"[{r['source']}] {r['timestamp'][:10]} ({r['type']})\n"
            if r['emotional_tone']:
                output += f"   Tone: {', '.join(r['emotional_tone'][:3])}\n"
            output += f"   {r['description']}\n\n"
        
        if len(results) > limit:
            output += f"... and {len(results) - limit} more results."
        
        return [TextContent(type="text", text=output)]
    
    # --- DAILY BRIEFING ---
    elif name == "daily_briefing":
        output = "=== Daily Briefing ===\n"
        output += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        
        # Unread messages
        msg_data = load_json(MESSAGES_FILE)
        unread = [m for m in msg_data.get("messages", []) if not m.get("read_by")]
        output += f"UNREAD MESSAGES: {len(unread)}\n"
        if unread:
            for m in unread[-3:]:
                output += f"  - [{m['id']}] {m['content'][:50]}...\n"
        output += "\n"
        
        # Open commitments
        commit_data = load_json(COMMITMENTS_FILE)
        open_commits = commit_data.get("open", [])
        output += f"OPEN COMMITMENTS: {len(open_commits)}\n"
        for c in open_commits[:3]:
            output += f"  - {c['description'][:60]}...\n"
        output += "\n"
        
        # Recent reflections
        ref_data = load_json(REFLECTIONS_FILE)
        reflections = ref_data.get("reflections", [])
        output += f"TOTAL REFLECTIONS: {len(reflections)}\n"
        if reflections:
            latest = reflections[-1]
            output += f"  Latest: {latest['prompt'][:40]}...\n"
        output += "\n"
        
        # Pending notifications
        notif_data = load_json(NOTIFICATIONS_FILE)
        pending = notif_data.get("pending", [])
        output += f"PENDING NOTIFICATIONS: {len(pending)}\n"
        for n in pending[:3]:
            output += f"  - [{n.get('urgency', 'normal')}] {n['message'][:40]}...\n"
        
        return [TextContent(type="text", text=output)]
    
    # --- NOTIFICATIONS ---
    elif name == "notify_brian":
        data = load_json(NOTIFICATIONS_FILE)
        
        delay = arguments.get("delay_minutes", 0)
        send_at = datetime.now() + timedelta(minutes=delay)
        
        notification = {
            "id": str(uuid.uuid4())[:8],
            "created_at": datetime.now().isoformat(),
            "send_at": send_at.isoformat(),
            "message": arguments["message"],
            "urgency": arguments.get("urgency", "normal"),
            "mention": arguments.get("mention"),
            "sent": False
        }
        
        data.setdefault("pending", []).append(notification)
        save_json(NOTIFICATIONS_FILE, data)
        
        mention_str = f"\nMention: {notification['mention']}" if notification['mention'] else ""
        
        return [TextContent(
            type="text",
            text=f"Notification scheduled!\n\nID: {notification['id']}\nMessage: {notification['message']}\nUrgency: {notification['urgency']}{mention_str}\nSend at: {send_at.strftime('%Y-%m-%d %H:%M')}"
        )]
    
    elif name == "get_pending_notifications":
        data = load_json(NOTIFICATIONS_FILE)
        pending = data.get("pending", [])
        
        if not pending:
            return [TextContent(type="text", text="No pending notifications.")]
        
        output = "=== Pending Notifications ===\n\n"
        for n in pending:
            output += f"[{n['id']}] ({n.get('urgency', 'normal')})\n"
            output += f"   Message: {n['message']}\n"
            if n.get('mention'):
                output += f"   Mention: {n['mention']}\n"
            output += f"   Send at: {n['send_at']}\n\n"
        
        return [TextContent(type="text", text=output)]
    
    return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    """Run the server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
