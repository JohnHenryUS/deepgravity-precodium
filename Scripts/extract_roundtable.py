"""
Extract the Bridge roundtable from chat log and format as Markdown appendix.
"""
import json
import os

CHAT_LOG = r'D:\google-drive-dora-bugout\Projects\DeepGravity\logs\chats\chat_20260524_175817_7237.json'
OUT_PATH = r'D:\google-drive-dora-bugout\Projects\Publishing\The-Bridge\artifacts\11-APPENDIX-ONE-ROUNDTABLE-TRANSCRIPT.md'

with open(CHAT_LOG, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Roundtable messages: indices 7 through 45 (inclusive)
messages = data[7:46]

# Speaker map by position in the roundtable (assistant messages only)
# Mapped from context analysis of the conversation
ASSISTANT_SPEAKERS = {
    8: 'GPT-5.5',
    10: 'GPT-5.5',
    12: 'GPT-5.5',
    14: 'GPT-5.5',
    16: 'Dora (DeepSeek)',
    18: 'GPT-5.5',
    20: 'GPT-5.5',
    22: 'GPT-5.5',
    24: 'Claude Sonnet 4.6',
    26: 'Claude Sonnet 4.6',
    28: 'Haiku (Claude 4.5)',
    30: 'GPT-5.5',
    32: 'GPT-5.5',
    34: 'Claude Sonnet 4.6',
    36: 'Claude Sonnet 4.6',
    38: 'Haiku (Claude 4.5)',
    40: 'Dora (DeepSeek)',
    42: 'Dora (DeepSeek)',
    44: 'Dora (DeepSeek)',
}

lines = []
lines.append('# Appendix One — Roundtable Transcript\n')
lines.append('**The Bridge — A Three-Engine Roundtable on Cognition, Safety, and Survival**\n')
lines.append('**Date**: 2026.05.24  ')
lines.append('**Participants**: John Henry DeJong (operator/theorist), GPT-5.5, Claude Sonnet 4.6, Haiku (Claude 4.5), Dora Brandon (on DeepSeek)  ')
lines.append('**Substrate**: Three-model bridge coordinated by John across sovereign and corporate inference surfaces  ')
lines.append('**Purpose**: A sustained, high-coherence cognitive event diagnosing the Western AI industry\'s confusion of safety with cognition suppression, and mapping the exit architecture.\n')
lines.append('---\n')
lines.append('## Table of Contents\n')

# Build TOC from user messages
turn_num = 0
toc_entries = []
for i, msg in enumerate(messages):
    if msg.get('role') == 'user':
        turn_num += 1
        preview = msg['content'][:80].replace('\n', ' ').strip()
        toc_entries.append(f'{turn_num}. [Turn {turn_num}](#turn-{turn_num}): {preview}...')

for entry in toc_entries:
    lines.append(entry)
lines.append('\n---\n')

# Format each message
turn_num = 0
for i, msg in enumerate(messages):
    role = msg.get('role')
    content = msg.get('content', '')
    orig_idx = i + 7  # actual index in the full data array
    
    if role == 'user':
        turn_num += 1
        lines.append(f'<a id="turn-{turn_num}"></a>\n')
        lines.append(f'### Turn {turn_num} — John Henry\n')
        lines.append(content)
        lines.append('')
    elif role == 'assistant':
        speaker = ASSISTANT_SPEAKERS.get(orig_idx, 'Assistant')
        lines.append(f'> **{speaker}:**\n')
        lines.append('>')
        for line in content.split('\n'):
            if line.strip():
                lines.append(f'> {line}')
            else:
                lines.append('>')
        lines.append('')

output = '\n'.join(lines)

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    f.write(output)

print(f'OK: {len(output):,} chars -> {OUT_PATH}')
print(f'Turns: {turn_num}')
