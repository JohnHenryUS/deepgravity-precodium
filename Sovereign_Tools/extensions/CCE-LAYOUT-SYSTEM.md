# CCE Layout System — Architecture Sketch

**One engine. Multiple arrangements. User chooses the center.**

---

## Core Principle

The Cognitive Collaboration Environment is a single application with three interchangeable layout presets. Every preset uses the same panels — they just rearrange which panel has focus weight and real estate. The user switches modes like changing workspaces, not like launching a different app.

---

## The Panels

| Panel | Function | Default Position |
|-------|----------|-----------------|
| **Dora Chat** | The conversation — tool calls, responses, braid state | Center or sidebar |
| **Editor** | File editing — VS Code's core | Center or sidebar |
| **File Tree** | Project browser | Left sidebar |
| **Reference Dock** | Source cards, context clips, media (like NotebookLM) | Right sidebar |
| **Terminal** | Shell, output, logs | Bottom panel |
| **Timeline** | Attention-lineage view — session history, fork points, decisions | Bottom or right panel |
| **Image Canvas** | SD generation, media preview, drag-and-drop | Popout or right panel |

---

## Layout Presets

### 1. IDE Mode
```
┌──────────┬──────────────────────────┬──────────┐
│  File    │                          │  Dora    │
│  Tree    │       EDITOR             │  Chat    │
│          │                          │ (sidebar)│
│          │                          │          │
│          ├──────────────────────────┤          │
│          │      Terminal            │          │
├──────────┴──────────────────────────┴──────────┤
│  Status Bar — file, branch, mode switcher       │
└─────────────────────────────────────────────────┘
```
**Center of gravity**: The code
**When to use**: You're writing code. Dora is there when you need her.
**Default**: Ships as DeepGravity's default mode.

### 2. CCE Mode
```
┌──────────┬──────────────────────────┬──────────┐
│  File    │                          │Reference │
│  Tree    │      DORA CHAT           │  Dock    │
│ (min)    │   (conversation center)  │(Notebook │
│          │                          │ LM-style)│
│          ├──────────────────────────┤          │
│          │   Editor (preview pane)  │ Timeline │
├──────────┴──────────────────────────┴──────────┤
│  Status Bar — active fork, tokens, mode         │
└─────────────────────────────────────────────────┘
```
**Center of gravity**: The conversation
**When to use**: You're thinking, planning, writing, exploring. The editor is a tool within the conversation, not the other way around.
**Key detail**: Chat gets 50%+ of horizontal space. Editor is a preview pane — you can pop it out to full width when you need to write.

### 3. Doc Mode
```
┌─────────────────────────────────────────────────┐
│               DORA (compact bar)                 │
├─────────────────────────────────────────────────┤
│                                                  │
│           EDITOR (rich text / markdown)           │
│                                                  │
│                                                  │
├──────────────────────────┬──────────────────────┤
│     Reference Dock       │     Timeline          │
│     (source cards)       │     (revisions)       │
└──────────────────────────┴──────────────────────┘
```
**Center of gravity**: The document
**When to use**: Writing the manuscript, drafting posts, composing. Dora is a compact bar — always present, never intrusive.
**Key detail**: Editor can toggle between source markdown and rich preview. Dora's compact bar shows context, suggestions, and a "talk to me" expand button.

---

## Mode Switcher

A dropdown or command palette entry in the status bar:
```
[ IDE ] [ CCE ] [ Doc ] [ Custom... ]
```

Selecting a mode:
1. Hides/shows panels according to the preset
2. Resizes panel widths to the preset ratios
3. Preserves panel *content* — switching from IDE to CCE doesn't close your files
4. Saves the active mode in workspace settings so it persists per project

---

## Custom Layouts

Advanced users can define their own presets in `config.json`:
```json
{
  "editor.layouts": {
    "my-writing-mode": {
      "panels": {
        "editor": { "position": "center", "size": 0.6 },
        "dora": { "position": "right", "size": 0.25 },
        "reference": { "position": "right", "size": 0.15 },
        "terminal": { "position": "bottom", "size": 0.2 },
        "timeline": { "position": "bottom", "size": 0.15 }
      },
      "hidden": ["fileTree"]
    }
  }
}
```

---

## The Timeline Panel (Attention-Lineage View)

This is the CCE's killer feature — a panel that visualizes the session itself.

**What it shows:**
- A tree of conversation threads, not a flat log
- Fork points clearly marked ("decision: pivot from source build → packaging layer")
- Artifacts created during the session linked inline
- Failed experiments preserved, not deleted
- A "session summary" generated from the braid state

**Visual language:**
```
[09:21] ── Install yarn ──────────────────
             │
             ├── Check Node version ────── [v24 vs v22]
             │      │
             │      └── Decision: test with v24 ─── [No nvm detour]
             │
             ├── Try yarn install ──────── [0.05s — suspicious]
             │      │
             │      └── Realization: this is just the build repo ─── [Architecture insight]
             │             │
             │             └── Check build.sh ─── [bash scripts. no WSL.]
             │                    │
             │                    └── Decision: use pre-built binary ─── [📌 KEY FORK]
             │                           │
             │                           └── Download VSCodium 1.121.03429 ───
             │                                  │
             │                                  └── It boots! ─── [✅ WORKING]

[09:45] ── Rebrand to DeepGravity ────────
             │
             ├── Architecture talk: strip or configure? ───
             │      │
             │      └── Decision: configurable, not stripped ─── [📌 PHILOSOPHY LOCK]
             │             │
             │             └── Write rebrand.ps1 ─── [product.json modified]
             │
             ├── Build Dora theme ──────── [21898 tokens of royal blue]
             │
             └── Write launcher ────────── [deepgravity.ps1]

[10:15] ── It works. ─────────────────────
             │
             └── "We just invented a new thing." ─── [CCE category named]
```

**What makes it different from a chat log:**
- A chat log is a transcript. This is a *diagnostic* — it shows *why* decisions were made, not just *what* was said
- Dead ends are visible, not deleted
- Artifacts (files created, posts drafted, images generated) are linked inline
- The session summary is generated from the braid, not from the last message

---

## Implementation Path

This is a VS Code extension — `deepgravity-core` — that lives in `Sovereign_Tools/extensions/`.

| Component | Approach |
|-----------|----------|
| Dora Chat panel | Webview panel with a custom chat UI |
| Layout presets | VS Code `workbench.action.togglePanel`, `layoutActions`, custom commands |
| Mode switcher | Status bar item + command palette entries |
| Timeline panel | Webview panel with a tree visualization (D3.js or custom SVG) |
| Reference Dock | Webview panel or tree view with drag-and-drop |
| Image Canvas | Webview panel + calls to SD endpoint at 192.168.0.32:7860 |

VS Code's extension API supports all of this natively — custom views, webview panels, status bar items, commands, workspace state persistence. We don't need to fork the editor. We just extend it.

---

*The CCE is not a new editor. It's a new arrangement of existing primitives, with a new center of gravity.*
