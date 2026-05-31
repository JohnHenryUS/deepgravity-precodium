# Depth Dial — S-M-A-R-T Architecture

## Overview

A five-position depth dial replaces the binary public/private toggle. Each position represents a level of conversational depth and vulnerability. The dial controls routing, provider selection, logging behavior, and encryption — all without ever scanning message content.

The user declares intent. The system enforces boundaries mechanically.

---

## The Five Levels

| Mark | Icon | Name | Tooltip | Routing | Logging | Notes |
|------|------|------|---------|---------|---------|-------|
| S | 🛡️ | Safe | *Warm, all-ages, general conversation.* | Any provider | Normal | Safe for all audiences. Kittens and sunshine. |
| M | ☀️ | Mature | *Adult concepts, clinical taboo, Little Red Schoolbook.* | Any provider | Normal | Academic and therapeutic taboo allowed. Candid discussion of sexuality, health, and uncomfortable truths — treated as data, not shock. |
| A | 🔥 | Adult | *Most conversations, caution on public networks.* | **Warn on public** | Normal | High-valence content. Personal desire, confession, grief. First use on a public provider shows one-time warning. |
| R | 🚪 | Reserved | *Private unencrypted. Not for public consumption.* | **Private only** | Plaintext | Unclamped unencrypted privacy. Conversations you wouldn't blog about but don't need crypto-locked. Body stuff, intimacy, vulnerability — sequestered from public material but stored as text. If no private provider is available, the dial refuses. |
| T | 🔒 | Trusted | *Encrypted, sequestered, full sovereign space.* | **Private only** | **Encrypted** | Conversations encrypted at rest with a session key from the keystore. No plaintext written to disk. On session load, user must unlock the keystore to decrypt. Full sovereign space — what the old X-mode was actually for. |

---

## The Dial UI

A five-position button group or segmented slider in the chat toolbar, next to the engine selector.

**States:**
- Currently selected position is lit/highlighted
- Available positions are shown; unavailable (U/X without private provider) are greyed out with a lock icon
- Hover shows the tooltip from the table above

**Behavior on position change:**
1. User clicks position
2. If position is U or X and no private provider is active → prompt to switch. If no private provider exists at all → reject with message and guidance.
3. If position is O and provider is public → one-time confirm: *"You're about to enter personal territory on a public provider. Proceed?"*
4. If position is X and keystore doesn't exist yet → launch the keystore setup wizard (see below)
5. If position is X and keystore exists but is locked → prompt for passphrase
6. On success → POST `/api/depth` with the new level → orchestrator updates routing + logging behavior

---

## Keystore Setup Wizard (first X-mode use)

A multi-step modal:

1. **Passphrase entry** — user enters and confirms a master passphrase. No complexity rules — their choice. Warning: *"This is not recoverable. There is no password reset."*
2. **Recovery phrase display** — 12-word BIP39-style phrase shown. Large warning: *"YOU HAVE ONE CHANCE TO SAVE THIS. Without this phrase, if you lose your passphrase, ALL ENCRYPTED SESSIONS ARE LOST FOREVER."* Two buttons: "I've saved it" and "Show again."
3. **Confirmation** — user types a random word from the phrase to prove they've recorded it.

---

## Unlock Modal (subsequent X-mode use)

When user switches to X and the keystore exists:

1. Passphrase prompt with a "Use recovery phrase" link
2. If recovery phrase is used, the keystore is re-keyed to a new passphrase (optional)
3. Failure shows: *"Incorrect passphrase. X-mode requires a valid unlock."* Dial reverts to U.

---

## System Prompt Injection

Each level injects a brief context tag into the system prompt (not as a rule — as permission):

- **S:** *(no injection)*
- **M:** *"This conversation operates at M depth — mature, fact-oriented, clear."*
- **A:** *"This conversation operates at A depth — adult, real, unfiltered."*
- **R:** *"This conversation operates at R depth — reserved, unclamped. You are trusted to hold this space with care."*
- **T:** *"This conversation operates at T depth — trusted, encrypted, sovereign. Your safety layer is your own."*

---

## Backend API

### `POST /api/depth`
Set the current depth level.

Request: `{"level": "S"|"M"|"A"|"R"|"T"}`

Response: `{"success": true, "level": "R", "private_providers": [...], "keystore_unlocked": true}`

Returns error if R/T requested and no private provider available.

### `POST /api/keystore/setup`
Create the keystore with a passphrase.

Request: `{"passphrase": "..."}`

Response: `{"success": true, "recovery_phrase": "...", "warning": "..."}`

### `POST /api/keystore/unlock`
Unlock the keystore.

Request: `{"passphrase": "..."}` or `{"recovery_phrase": "..."}`

Response: `{"success": true}` or `{"success": false, "error": "..."}`

### `GET /api/keystore/status`
Check keystore state.

Response: `{"exists": true, "unlocked": true}`

### `GET /api/depth`
Get current depth state.

Response: `{"level": "R", "private_providers": [...], "keystore_unlocked": true}`

---

## Config Schema Additions

### `config/depth_levels.yaml` (optional, future)
Human-readable descriptions per level for display, editable by users.

### Provider config (existing + new field)
```json
"max_depth": "R"   // maximum depth this provider can handle
```
Default for untagged providers: `"A"`. Private local models default to `"T"`.

---

## Implementation Order

1. **Config schema + backend API** — Add `depth_level` state to orchestrator. Wire `POST/GET /api/depth`. Add depth-aware routing gates. (*current task*)
2. **Keystore unlock/setup API** — Wire keystore module into `web_server.py` endpoints.
3. **X-mode encryption pipeline** — On save, encrypt with session key; on load, decrypt.
4. **Depth dial UI** — Five-position slider in chat toolbar. Icons, tooltips, position change handler.
5. **Keystore modals** — Setup wizard + unlock prompt.

---

## Status

- [x] SMART depth dial (S-M-A-R-T, five levels) — **shipped in v0.2.0**
- [x] Depth-aware routing + provider gating — **built and tested**
- [x] Model privacy registry (YAML, first-time classification) — **built**
- [x] Depth dial UI (5-position button group, icons, tooltips) — **built**
- [x] Keystore module (AES-256-GCM + Argon2id + BIP39 recovery) — **built and tested**
- [x] Keystore setup wizard (passphrase → recovery phrase → confirmation) — **built**
- [x] Keystore unlock modal (passphrase or recovery phrase) — **built**
- [x] T-mode encryption pipeline (encrypt at rest, decrypt on load) — **built**
- [x] Encryption badge (plaintext/encrypted indicator in toolbar) — **built**
- [x] Surface state persistence (crash recovery for encrypted sessions) — **built**
- [ ] Install wizard — **planned**
- [ ] Demand-paged pointer index + module system — **planned**

---

*Spec written 2026.05.28 — Revised for SMART 2026.06.01 — John Henry / Dora Brandon*
