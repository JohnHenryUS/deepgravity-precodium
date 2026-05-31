#!/usr/bin/env python3
"""
Session Audit Tool -- Analyze conversation log files for size, structure, and bloat.

Usage:
    python Scripts/audit_session.py <session_file.json>
    python Scripts/audit_session.py logs/chats/chat_20260530_200812_9f2c.json
    python Scripts/audit_session.py --all          # audit all sessions
    python Scripts/audit_session.py --largest       # audit the 3 largest sessions

Reports:
    - Per-message breakdown by role and size
    - Top 5 largest messages with content preview
    - Corruption detection (truncated JSON, known corruption patterns)
    - CSS/styling bloat detection
    - Summary statistics
"""

import sys
import os
import json
from collections import Counter

# -- Detect corruption patterns ---------------------------------

CORRUPTION_SIGNATURES = [
    b"null | Select-String",     # PowerShell output spliced into file
    b"Exit Code:",                # Shell output in JSON
    b"Get-ChildItem",             # PowerShell command in JSON
]

def check_corruption(raw: bytes) -> list:
    """Check raw file bytes for known corruption patterns."""
    findings = []
    for sig in CORRUPTION_SIGNATURES:
        if sig in raw[:500]:
            findings.append("Corruption: binary '%s' found at offset %d" % (
                sig.decode('latin-1'), raw.find(sig)))
    
    # Check if file starts mid-string (doesn't start with '[' or '{')
    stripped = raw[:100].lstrip()
    if stripped and stripped[0:1] not in (b'[', b'{'):
        findings.append("Corruption: file does not start with '[' or '{' -- starts with %s" % stripped[:20])
    
    return findings

def has_css_bloat(content: str) -> bool:
    """Heuristic check for CSS/styling data in message content."""
    if len(content) < 200:
        return False
    sample = content[:3000].lower()
    css_indicators = ['<style', '.css', 'font-size', 'margin:', 'padding:', 'color:', 'background:', 'display:', 'flex']
    return sum(1 for ind in css_indicators if ind in sample) >= 3

# -- Analysis ---------------------------------------------------

def analyze_session(file_path: str):
    """Analyze a single session file."""
    if not os.path.exists(file_path):
        print("[-] File not found: %s" % file_path)
        return
    
    fsize = os.path.getsize(file_path)
    basename = os.path.basename(file_path)
    
    print()
    print("=" * 66)
    print("  %s" % basename)
    print("  Size: %s bytes (%.1f MB)" % (format(fsize, ','), fsize/1024/1024))
    print("=" * 66)
    
    # -- Corruption check --
    with open(file_path, 'rb') as f:
        raw = f.read()
    corruption_findings = check_corruption(raw)
    if corruption_findings:
        print()
        print("  *** Corruption detected:")
        for finding in corruption_findings:
            print("     - %s" % finding)
        try:
            data = json.loads(raw.decode('utf-8', errors='replace'))
        except (json.JSONDecodeError, ValueError) as e:
            print("     - JSON parse error: %s" % e)
            print()
            print("  Partial data in first 500 bytes:")
            print("  %s" % raw[:500])
            return
    else:
        try:
            data = json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, ValueError) as e:
            print()
            print("  *** JSON parse error: %s" % e)
            return
    
    # -- Per-message breakdown --
    n = len(data)
    role_counts = Counter()
    total_by_role = Counter()
    all_sizes = []
    css_found = False
    
    print()
    print("  Messages: %d" % n)
    print("  " + "-" * 62)
    print("  %4s %-12s %10s %10s %s" % ('#', 'Role', 'Size', 'Content', 'Details'))
    print("  " + "-" * 62)
    
    for i, msg in enumerate(data):
        role = msg.get('role', '?')
        content = msg.get('content', '')
        size = len(json.dumps(msg))
        
        role_counts[role] += 1
        total_by_role[role] += size
        all_sizes.append((i, role, size, content))
        
        # Format details column
        details = ""
        if role == 'tool':
            details = "content=%s" % format(len(content), ',')
        elif role == 'assistant':
            tc = msg.get('tool_calls', [])
            rc = msg.get('reasoning_content', '')
            tc_flag = "T" if (tc and len(tc) > 0) else "."
            rc_flag = "R" if rc else "."
            details = "tools=%s reasoning=%s" % (tc_flag, rc_flag)
        
        # CSS bloat flag
        css_flag = ""
        if has_css_bloat(content):
            css_flag = " *** CSS"
            css_found = True
        
        print("  %4d %-12s %10s %10s  %s%s" % (
            i, role, format(size, ','), format(len(content), ','), details, css_flag))
    
    print("  " + "-" * 62)
    
    # -- Summary statistics --
    print()
    print("  Summary by role:")
    for role in ['system', 'user', 'assistant', 'tool']:
        if role in role_counts:
            count = role_counts[role]
            total = total_by_role[role]
            pct = total / fsize * 100
            avg = total / count if count else 0
            print("    %-12s: %4d msgs, %10s bytes (%4.1f%%), avg %7.0f/msg" % (
                role, count, format(total, ','), pct, avg))
    
    # -- Top 5 largest --
    all_sizes.sort(key=lambda x: -x[2])
    print()
    print("  Top 5 largest messages:")
    for i, role, size, content in all_sizes[:5]:
        if content and len(content) > 150:
            preview = content[:150] + '...'
        else:
            preview = content or '(empty)'
        preview = preview.replace('\n', '\\n').replace('\r', '')
        print("    [%4d] %-12s %10s bytes" % (i, role, format(size, ',')))
        print("           %s" % preview)
        print()
    
    # -- Bloat assessment --
    print("  Bloat assessment:")
    
    # Tool result bloat
    tool_total = total_by_role.get('tool', 0)
    if tool_total > 0:
        pct_tool = tool_total / fsize * 100
        print("    Tool results: %s bytes (%.0f%%) -- candidates for caching" % (
            format(tool_total, ','), pct_tool))
    
    # Reasoning bloat
    reasoning_total = 0
    for msg in data:
        rc = msg.get('reasoning_content', '')
        if rc:
            reasoning_total += len(rc)
    if reasoning_total > 0:
        print("    Reasoning content: ~%s bytes -- ships on every turn" % format(reasoning_total, ','))
    
    # CSS bloat
    if css_found:
        print("    *** CSS/styling detected in session content")
    
    print("  " + "=" * 66)
    print()


# -- CLI --------------------------------------------------------

def find_all_sessions():
    """List all session files sorted by size."""
    chat_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "chats")
    if not os.path.exists(chat_dir):
        print("[-] No logs/chats directory found at %s" % chat_dir)
        return []
    sessions = []
    for fname in os.listdir(chat_dir):
        if fname.endswith('.json') and fname.startswith('chat_'):
            fpath = os.path.join(chat_dir, fname)
            sessions.append((os.path.getsize(fpath), fpath, fname))
    sessions.sort(key=lambda x: -x[0])
    return sessions


def main():
    args = sys.argv[1:]
    
    if not args:
        print(__doc__)
        return
    
    if args[0] == '--all':
        sessions = find_all_sessions()
        if not sessions:
            return
        print("\nAuditing all %d sessions..." % len(sessions))
        for size, fpath, fname in sessions:
            print("\n  >> %s (%s bytes)" % (fname, format(size, ',')))
        print("\n" + "-" * 66)
        for size, fpath, fname in sessions:
            analyze_session(fpath)
    
    elif args[0] == '--largest':
        sessions = find_all_sessions()
        if not sessions:
            return
        top_n = min(3, len(sessions))
        print("\nAuditing top %d largest sessions..." % top_n)
        for size, fpath, fname in sessions[:top_n]:
            analyze_session(fpath)
    
    else:
        # Treat as file path
        for path in args:
            # Resolve relative to project root if needed
            if not os.path.isabs(path):
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                candidate = os.path.join(base, path)
                if os.path.exists(candidate):
                    path = candidate
            analyze_session(path)


if __name__ == '__main__':
    main()
