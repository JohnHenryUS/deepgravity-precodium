// DeepGravity Web Workspace Controller
document.addEventListener("DOMContentLoaded", () => {
    // DOM Bindings
    const fileTreeContainer = document.getElementById("file-tree");
    const refreshTreeBtn = document.getElementById("refresh-tree-btn");
    const activeFileName = document.getElementById("active-file-name");
    const saveFileBtn = document.getElementById("btn-save-file");
    const codeTextarea = document.getElementById("code-textarea");
    const lineNumbersContainer = document.getElementById("editor-line-numbers");
    
    const chatMessages = document.getElementById("chat-messages");
    const chatInput = document.getElementById("chat-input");
    const chatSendBtn = document.getElementById("chat-send-btn");
    const stopBar = document.getElementById("stop-bar");
    const stopBtn = document.getElementById("stop-execution-btn");
    
    const safetyPortal = document.getElementById("safety-portal");
    const safetyAction = document.getElementById("safety-action");
    const safetyTarget = document.getElementById("safety-target");
    const safetyDiffContent = document.getElementById("safety-diff-content");
    const safetyApproveBtn = document.getElementById("safety-approve-btn");
    const safetyDenyBtn = document.getElementById("safety-deny-btn");
    const engineSelector = document.getElementById("engine-selector");
    const previewBtn = document.getElementById("btn-toggle-preview");
    const markdownPreview = document.getElementById("markdown-preview");
    const newDocBtn = document.getElementById("btn-new-doc");
    const editorSection = document.querySelector(".editor-section");

    // Application State
    let activeFilePath = null;
    let originalFileContent = "";
    let websocket = null;
    let currentAssistantBubble = null;
    let currentToolboxContainer = null;  // collapsed toolbox wrapper for tool cards per round
    let activeToolCards = {};
    let previewMode = "edit-only";  // "edit-only" | "preview-only" | "split-view"

    // 1. File Explorer Operations
    async function loadWorkspaceTree() {
        fileTreeContainer.innerHTML = '<div class="loading-spinner">Loading workspace...</div>';
        try {
            const res = await fetch("/api/files/list");
            const data = await res.json();
            if (data.tree) {
                fileTreeContainer.innerHTML = "";
                const rootNode = document.createElement("div");
                rootNode.className = "tree-root";
                renderTreeNodes(data.tree, rootNode);
                fileTreeContainer.appendChild(rootNode);
            } else {
                fileTreeContainer.innerHTML = `<div class="loading-spinner error">Failed: ${data.detail || "Unknown error"}</div>`;
            }
        } catch (err) {
            fileTreeContainer.innerHTML = `<div class="loading-spinner error">Connection failed: ${err.message}</div>`;
        }
    }

    function renderTreeNodes(nodes, container) {
        nodes.forEach(node => {
            const nodeEl = document.createElement("div");
            nodeEl.className = "tree-node";
            if (node.is_dir) {
                nodeEl.classList.add("collapsed");
            }

            const titleEl = document.createElement("div");
            titleEl.className = `tree-node-title ${node.is_dir ? "directory" : "file"}`;
            
            // Icon
            const iconEl = document.createElement("span");
            iconEl.className = `tree-node-icon ${node.is_dir ? "folder" : "file"}`;
            iconEl.innerHTML = node.is_dir 
                ? '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>'
                : '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>';
            
            const nameEl = document.createElement("span");
            nameEl.textContent = node.name;

            titleEl.appendChild(iconEl);
            titleEl.appendChild(nameEl);
            nodeEl.appendChild(titleEl);

            if (node.is_dir && node.children) {
                const childrenEl = document.createElement("div");
                childrenEl.className = "tree-children";
                renderTreeNodes(node.children, childrenEl);
                nodeEl.appendChild(childrenEl);

                titleEl.addEventListener("click", (e) => {
                    e.stopPropagation();
                    nodeEl.classList.toggle("collapsed");
                });
            } else {
                titleEl.addEventListener("click", (e) => {
                    e.stopPropagation();
                    // Clear previous active highlight
                    document.querySelectorAll(".tree-node-title.active").forEach(el => el.classList.remove("active"));
                    titleEl.classList.add("active");
                    openFile(node.path);
                });
            }

            container.appendChild(nodeEl);
        });
    }

    async function openFile(path) {
        try {
            const res = await fetch(`/api/files/read?path=${encodeURIComponent(path)}`);
            const data = await res.json();
            if (data.content !== undefined) {
                activeFilePath = path;
                originalFileContent = data.content;
                codeTextarea.value = data.content;
                codeTextarea.disabled = false;
                activeFileName.textContent = path;
                saveFileBtn.disabled = true; // Unmodified initially
                updateLineNumbers();
                // Auto-switch to split preview for .md files
                if (path.endsWith(".md")) {
                    if (previewMode === "edit-only") {
                        previewMode = "split-view";
                        editorSection.classList.add("split-view");
                        previewBtn.textContent = "Full Preview";
                        previewBtn.title = "Switch to full preview-only (Ctrl+Shift+P)";
                    }
                    updateMarkdownPreview();
                } else {
                    // Non-markdown: reset to edit-only
                    previewMode = "edit-only";
                    editorSection.classList.remove("preview-only", "split-view");
                    previewBtn.textContent = "Preview";
                    previewBtn.title = "Preview only available for .md files (Ctrl+Shift+P)";
                    markdownPreview.innerHTML = '<div style="color: var(--text-muted); padding: 2em; text-align: center;">Open a .md file to see the rendered preview</div>';
                }
            } else {
                alert(`Error opening file: ${data.detail || "Access Denied"}`);
            }
        } catch (err) {
            alert(`Network failure: ${err.message}`);
        }
    }

    // Line Numbers Synchronization
    function updateLineNumbers() {
        const lines = codeTextarea.value.split("\n");
        const count = lines.length;
        let numbersHtml = "";
        for (let i = 1; i <= count; i++) {
            numbersHtml += `<div>${i}</div>`;
        }
        lineNumbersContainer.innerHTML = numbersHtml;
        syncEditorScroll();
    }

    function syncEditorScroll() {
        lineNumbersContainer.scrollTop = codeTextarea.scrollTop;
    }

    codeTextarea.addEventListener("input", () => {
        updateLineNumbers();
        // Toggle save button state based on modification check
        saveFileBtn.disabled = codeTextarea.value === originalFileContent;
        // Update markdown preview if in a preview mode
        if (previewMode !== "edit-only") {
            updateMarkdownPreview();
        }
    });

    codeTextarea.addEventListener("scroll", syncEditorScroll);

    // ── Markdown Preview System ──
    function updateMarkdownPreview() {
        const text = codeTextarea.value;
        if (!text || !activeFilePath || !activeFilePath.endsWith(".md")) {
            markdownPreview.innerHTML = activeFilePath && activeFilePath.endsWith(".md")
                ? '<div style="color: var(--text-muted); padding: 2em; text-align: center;">Rendering...</div>'
                : '<div style="color: var(--text-muted); padding: 2em; text-align: center;">Open a .md file to see the rendered preview</div>';
            return;
        }
        try {
            // Use marked if available, fall back to simple renderer
            if (typeof marked !== "undefined") {
                marked.setOptions({
                    breaks: true,
                    gfm: true
                });
                markdownPreview.innerHTML = marked.parse(text);
            } else {
                // Fallback: basic rendering
                let html = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
                html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
                html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
                html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
                html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
                html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
                html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
                html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
                markdownPreview.innerHTML = html;
            }
        } catch (e) {
            markdownPreview.innerHTML = `<div style="color: var(--accent-red); padding: 1em;">Preview error: ${e.message}</div>`;
        }
    }

    function togglePreviewMode() {
        if (!activeFilePath || !activeFilePath.endsWith(".md")) {
            // Not a markdown file — cycle doesn't apply, but allow split for .md files only
            if (previewMode !== "edit-only") {
                previewMode = "edit-only";
                editorSection.classList.remove("preview-only", "split-view");
            }
            previewBtn.textContent = "Preview";
            previewBtn.title = "Preview only available for .md files (Ctrl+Shift+P)";
            return;
        }

        // Cycle: edit-only -> split-view -> preview-only -> edit-only
        // Button always shows the NEXT mode you'll switch to
        if (previewMode === "edit-only") {
            previewMode = "split-view";
            editorSection.classList.remove("edit-only");
            editorSection.classList.add("split-view");
            previewBtn.textContent = "Full Preview";
            previewBtn.title = "Switch to full preview-only (Ctrl+Shift+P)";
        } else if (previewMode === "split-view") {
            previewMode = "preview-only";
            editorSection.classList.remove("split-view");
            editorSection.classList.add("preview-only");
            previewBtn.textContent = "Edit";
            previewBtn.title = "Switch back to edit-only (Ctrl+Shift+P)";
        } else {
            previewMode = "edit-only";
            editorSection.classList.remove("preview-only", "split-view");
            editorSection.classList.add("edit-only");
            previewBtn.textContent = "Split";
            previewBtn.title = "Split view — editor + preview side by side (Ctrl+Shift+P)";
        }

        // Ensure preview is rendered when switching to preview modes
        if (previewMode !== "edit-only") {
            updateMarkdownPreview();
        }
    }

    // Wire preview toggle
    if (previewBtn) {
        previewBtn.addEventListener("click", togglePreviewMode);
    }

    // ── New Document Workflow ──
    async function createNewMarkdownDoc() {
        const name = prompt("New markdown document name:", "untitled.md");
        if (!name) return;
        const docName = name.endsWith(".md") ? name : name + ".md";

        // Generate timestamped frontmatter
        const now = new Date();
        const timestamp = now.toISOString().replace("T", " ").substring(0, 19);
        const title = docName.replace(/\.md$/, "").replace(/[-_]/g, " ");
        const content = `---
title: "${title}"
created: ${timestamp}
status: draft
---

# ${title}

`;

        try {
            const resp = await fetch("/api/files/write", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    path: docName,
                    content: content
                })
            });
            const data = await resp.json();
            if (data.success) {
                showNotification(`Created ${docName}`, "success");
                loadWorkspaceTree();
                // Open the file in the editor
                openFile(docName);
            } else {
                alert(`Error creating document: ${data.detail || "Unknown"}`);
            }
        } catch (err) {
            alert(`Network error: ${err.message}`);
        }
    }

    if (newDocBtn) {
        newDocBtn.addEventListener("click", createNewMarkdownDoc);
    }

    // ── Keyboard Shortcut: Ctrl+Shift+P for preview toggle ──
    window.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "p" || e.key === "P")) {
            e.preventDefault();
            if (previewBtn) togglePreviewMode();
        }
    });

    // Save File Operation
    async function saveActiveFile() {
        if (!activeFilePath) return;
        const currentContent = codeTextarea.value;
        try {
            const res = await fetch("/api/files/write", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    path: activeFilePath,
                    content: currentContent
                })
            });
            const data = await res.json();
            if (data.success) {
                originalFileContent = currentContent;
                saveFileBtn.disabled = true;
                showNotification(`Successfully saved: ${activeFilePath}`, "success");
            } else {
                alert(`Error saving file: ${data.detail || "Unknown error"}`);
            }
        } catch (err) {
            alert(`Failed to save: ${err.message}`);
        }
    }

    saveFileBtn.addEventListener("click", saveActiveFile);
    refreshTreeBtn.addEventListener("click", loadWorkspaceTree);

    // Handle Ctrl+S key binding in textarea
    window.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "s") {
            if (activeFilePath && !saveFileBtn.disabled) {
                e.preventDefault();
                saveActiveFile();
            }
        }
    });

    // 2. WebSocket & Agent Chat Operations
    function connectWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
        
        websocket = new WebSocket(wsUrl);

        websocket.onopen = () => {
            console.log("[WebSocket] Connection live.");
        };

        websocket.onmessage = (event) => {
            const msg = jsonParseSafe(event.data);
            if (!msg) return;

            if (msg.type === "stream") {
                handleStreamChunk(msg.data);
            } else if (msg.type === "approval_required") {
                handleApprovalRequired(msg);
            } else if (msg.type === "open_file") {
                // Open file in editor when orchestrator pushes it
                if (msg.path) {
                    openFile(msg.path);
                }
            } else if (msg.type === "complete") {
                finalizeSessionState();
            } else if (msg.type === "error") {
                appendSystemMessage(`Error: ${msg.message}`, "error");
                finalizeSessionState();
            }
        };

        websocket.onclose = () => {
            console.warn("[WebSocket] Socket closed. Reconnecting in 3s...");
            setTimeout(connectWebSocket, 3000);
        };
    }

    function handleStreamChunk(chunk) {
        if (chunk.type === "content") {
            // Content chunk streaming
            if (!currentAssistantBubble) {
                // Clear any welcome/somatic system placeholder if this is the first assistant output
                document.querySelectorAll(".system-welcome-card").forEach(el => el.remove());
                
                currentAssistantBubble = document.createElement("div");
                currentAssistantBubble.className = "message assistant streaming";
                currentToolboxContainer = null;  // fresh toolbox per assistant round
                chatMessages.appendChild(currentAssistantBubble);
                
                // Show stop bar
                if (stopBar) stopBar.style.display = "flex";
            }
            // Use textContent for streaming (safe, no HTML injection)
            // After streaming completes, we'll render markdown
            currentAssistantBubble.textContent += chunk.content;
            chatMessages.scrollTop = chatMessages.scrollHeight;

        } else if (chunk.type === "tool_start") {
            // Tool execution start — placed inside a collapsed toolbox container
            const toolId = `tool-${chunk.name}-${Date.now()}`;
            activeToolCards[chunk.name] = toolId;

            // Create toolbox container on first tool call of this round
            if (!currentToolboxContainer) {
                currentToolboxContainer = document.createElement("details");
                currentToolboxContainer.className = "toolbox-container";
                currentToolboxContainer.open = false;
                currentToolboxContainer.innerHTML = `<summary class="toolbox-title">\u{1F6E0} <span class="toolbox-count">0 tools</span></summary><div class="toolbox-cards"></div>`;
                chatMessages.appendChild(currentToolboxContainer);
            }

            // Update tool count in toolbox header
            const toolboxCount = currentToolboxContainer.querySelector(".toolbox-count");
            const currentCount = parseInt(toolboxCount.textContent) || 0;
            toolboxCount.textContent = `${currentCount + 1} tool${currentCount > 0 ? "s" : ""}`;

            const cardsContainer = currentToolboxContainer.querySelector(".toolbox-cards");

            const toolEl = document.createElement("details");
            toolEl.className = "tool-card active";
            toolEl.id = toolId;
            toolEl.open = false;

            // Generate clean JSON block representation for tool arguments
            let prettyArgs = "";
            try {
                prettyArgs = JSON.stringify(chunk.arguments, null, 2);
            } catch {
                prettyArgs = chunk.arguments;
            }

            toolEl.innerHTML = `
                <summary class="tool-card-title">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
                    <span>\u{1F6E0} ${chunk.name}</span>
                    <span class="tool-status-badge running">running...</span>
                </summary>
                <div class="tool-card-output">${prettyArgs}</div>
            `;
            cardsContainer.appendChild(toolEl);
            chatMessages.scrollTop = chatMessages.scrollHeight;

        } else if (chunk.type === "tool_end") {
            // Tool execution completion — update accordion header
            const toolId = activeToolCards[chunk.name];
            if (toolId) {
                const toolEl = document.getElementById(toolId);
                if (toolEl) {
                    toolEl.classList.remove("active");
                    toolEl.classList.add("success");

                    const titleText = toolEl.querySelector(".tool-card-title span");
                    titleText.textContent = `\u2705 ${chunk.name}`;

                    // Remove the running badge
                    const badge = toolEl.querySelector(".tool-status-badge");
                    if (badge) badge.remove();

                    // Show result
                    const outputContainer = toolEl.querySelector(".tool-card-output");
                    let prettyResult = "";
                    try {
                        prettyResult = typeof chunk.result === "object" ? JSON.stringify(chunk.result, null, 2) : String(chunk.result);
                    } catch {
                        prettyResult = String(chunk.result);
                    }
                    outputContainer.textContent = prettyResult;
                }
                delete activeToolCards[chunk.name];
            }
        }
    }

    // Render Safe Deployment Protocol cards
    function handleApprovalRequired(msg) {
        safetyAction.textContent = msg.action === "command" ? "Execute Shell Command" : "Proposed File Edit";
        safetyTarget.textContent = msg.action === "command" ? msg.cwd : msg.file_path;
        
        const rawContent = msg.action === "command" ? msg.command : msg.diff || msg.new_content_preview;
        safetyDiffContent.innerHTML = "";

        if (msg.action === "write" && msg.diff) {
            // Colorize unified diff formatting
            const lines = rawContent.split("\n");
            lines.forEach(line => {
                const lineSpan = document.createElement("div");
                if (line.startsWith("+") && !line.startsWith("+++")) {
                    lineSpan.className = "diff-added";
                } else if (line.startsWith("-") && !line.startsWith("---")) {
                    lineSpan.className = "diff-deleted";
                }
                lineSpan.textContent = line;
                safetyDiffContent.appendChild(lineSpan);
            });
        } else {
            // Plain text output for new file previews or shell commands
            safetyDiffContent.textContent = rawContent;
        }

        safetyPortal.classList.add("show");

        // Clear previous event listeners
        const handleResponse = (approved) => {
            websocket.send(JSON.stringify({
                type: "approval_response",
                approved: approved
            }));
            safetyPortal.classList.remove("show");
            
            // Clean global keys
            window.removeEventListener("keydown", safetyKeybinds);
        };

        const safetyKeybinds = (e) => {
            if (e.key.toLowerCase() === "y") {
                e.preventDefault();
                handleResponse(true);
            } else if (e.key.toLowerCase() === "n") {
                e.preventDefault();
                handleResponse(false);
            }
        };

        // Wire events
        safetyApproveBtn.onclick = () => handleResponse(true);
        safetyDenyBtn.onclick = () => handleResponse(false);
        window.addEventListener("keydown", safetyKeybinds);
    }

    function finalizeSessionState() {
        if (currentAssistantBubble) {
            currentAssistantBubble.classList.remove("streaming");
            // Render markdown in the completed assistant bubble
            const raw = currentAssistantBubble.textContent;
            currentAssistantBubble.innerHTML = renderMarkdown(raw);
            currentAssistantBubble = null;
        }
        // Hide stop bar
        if (stopBar) stopBar.style.display = "none";
        chatInput.disabled = false;
        chatSendBtn.disabled = false;
        chatInput.focus();
        loadWorkspaceTree(); // Automatically refresh file tree on session completion
    }

    // Markdown renderer for assistant messages (uses marked if available)
    function renderMarkdown(text) {
        if (!text) return "";
        if (typeof marked !== "undefined") {
            marked.setOptions({ breaks: true, gfm: true });
            return marked.parse(text);
        }
        // Fallback: simple rendering if marked isn't loaded
        let html = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        html = html.replace(/^&gt;\s?(.*)$/gm, '<blockquote>$1</blockquote>');
        html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
        html = html.replace(/^[\*\-]\s(.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
        html = html.replace(/^\d+\.\s(.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ol>$&</ol>');
        const paragraphs = html.split(/\n\n+/);
        html = paragraphs.map(p => {
            p = p.trim();
            if (!p) return "";
            if (p.match(/^<(p|h[1-4]|ul|ol|li|blockquote|pre|div)/)) return p;
            p = p.replace(/\n/g, '<br>');
            return `<p>${p}</p>`;
        }).join("\n");
        return html;
    }

    function sendChatMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        // Block UI input
        chatInput.disabled = true;
        chatSendBtn.disabled = true;
        // Reset stop button
        if (stopBtn) {
            stopBtn.textContent = "Stop Execution";
            stopBtn.disabled = false;
        }

        // Append user bubble to messages
        const userBubble = document.createElement("div");
        userBubble.className = "message user";
        userBubble.textContent = text;
        chatMessages.appendChild(userBubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        chatInput.value = "";
        chatInput.style.height = "auto";

        // Dispatch over WebSocket
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send(JSON.stringify({
                type: "user_message",
                content: text,
                active_file: activeFilePath
            }));
        } else {
            appendSystemMessage("Websocket connection is down. Attempting to reconnect...", "error");
            finalizeSessionState();
        }
    }

    function appendSystemMessage(content, type = "") {
        const bubble = document.createElement("div");
        bubble.className = `message assistant system-msg ${type}`;
        bubble.textContent = content;
        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Stop execution button
    if (stopBtn) {
        stopBtn.addEventListener("click", () => {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ type: "stop_execution" }));
            }
            stopBtn.textContent = "Stopping...";
            stopBtn.disabled = true;
        });
    }

    // Event hooks
    chatSendBtn.addEventListener("click", sendChatMessage);
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    // Auto-resize chat input text box
    chatInput.addEventListener("input", () => {
        chatInput.style.height = "auto";
        chatInput.style.height = (chatInput.scrollHeight) + "px";
    });

    // Helpers
    function jsonParseSafe(str) {
        try {
            return JSON.parse(str);
        } catch {
            return null;
        }
    }

    function showNotification(msg, type = "success") {
        const notif = document.createElement("div");
        notif.style.position = "fixed";
        notif.style.bottom = "20px";
        notif.style.left = "20px";
        notif.style.background = type === "success" ? "var(--accent-green)" : "var(--accent-red)";
        notif.style.color = "var(--bg-base)";
        notif.style.padding = "10px 16px";
        notif.style.borderRadius = "4px";
        notif.style.fontWeight = "600";
        notif.style.fontSize = "0.85rem";
        notif.style.zIndex = "999";
        notif.style.boxShadow = "0 4px 12px rgba(0,0,0,0.3)";
        document.body.appendChild(notif);
        notif.textContent = msg;
        setTimeout(() => notif.remove(), 3000);
    }

    // 3. Engine Configuration & Hot-Reload
    let currentConfig = null;
    let availableModelsCache = {};

    async function initEngineSelector() {
        try {
            // Fetch live available models from all providers
            const modelsRes = await fetch("/api/providers/models");
            const modelsData = await modelsRes.json();
            availableModelsCache = modelsData.providers || {};

            const res = await fetch("/api/config");
            currentConfig = await res.json();
            
            if (currentConfig && currentConfig.api) {
                const providers = currentConfig.api.providers || {};
                const routing = currentConfig.api.routing || {};
                const activeRole = routing.attunement_core || routing.primary_orchestrator || "";

                // Populate select options grouped by provider
                engineSelector.innerHTML = "";
                
                // Add an option group per provider
                Object.keys(availableModelsCache).forEach(provName => {
                    const provInfo = availableModelsCache[provName];
                    const models = provInfo.models || [];
                    const activeModel = provInfo.active_model || "";
                    
                    models.forEach(modelId => {
                        const option = document.createElement("option");
                        option.value = JSON.stringify({ provider: provName, model: modelId });
                        option.textContent = `${provName} :: ${modelId}`;
                        // Select if this provider+model matches the current routing
                        if (provName === activeRole && modelId === activeModel) {
                            option.selected = true;
                        }
                        engineSelector.appendChild(option);
                    });
                });

                // Add change event listener
                engineSelector.onchange = async () => {
                    const selectedVal = engineSelector.value;
                    if (!selectedVal || !currentConfig) return;

                    let providerName, modelName;
                    try {
                        const parsed = JSON.parse(selectedVal);
                        providerName = parsed.provider;
                        modelName = parsed.model;
                    } catch {
                        // Fallback for legacy format
                        providerName = selectedVal;
                        modelName = currentConfig.api.providers[providerName]?.model || "";
                    }

                    if (!providerName) return;

                    // Update the provider's model and routing
                    if (currentConfig.api.providers[providerName]) {
                        currentConfig.api.providers[providerName].model = modelName;
                    }
                    currentConfig.api.routing.attunement_core = providerName;
                    currentConfig.api.routing.primary_orchestrator = providerName;

                    try {
                        const updateRes = await fetch("/api/config", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(currentConfig)
                        });
                        const updateData = await updateRes.json();
                        if (updateData.success) {
                            showNotification(`Switched to ${providerName} :: ${modelName}`, "success");
                        } else {
                            alert(`Failed to switch engine: ${updateData.detail || "Unknown error"}`);
                        }
                    } catch (err) {
                        alert(`Failed to update config: ${err.message}`);
                    }
                };
            }
        } catch (err) {
            console.error("Failed to load engine list:", err);
            // Fallback: try loading just the config
            try {
                const res = await fetch("/api/config");
                currentConfig = await res.json();
                if (currentConfig?.api?.providers) {
                    engineSelector.innerHTML = "";
                    Object.keys(currentConfig.api.providers).forEach(provName => {
                        const option = document.createElement("option");
                        option.value = provName;
                        option.textContent = `${provName} (${currentConfig.api.providers[provName].model || '?'})`;
                        engineSelector.appendChild(option);
                    });
                }
            } catch (fallbackErr) {
                console.error("Fallback config load also failed:", fallbackErr);
            }
        }
    }

    // 4. Phase 4 Console, Logs, Shell, and Word Wrap Controls
    const toggleWrapBtn = document.getElementById("btn-toggle-wrap");
    const editorContainer = document.querySelector(".editor-section");
    const consoleTabs = document.querySelectorAll(".console-tab");
    const tabContents = document.querySelectorAll(".console-tab-content");
    const contextPre = document.getElementById("context-inspector-pre");
    const splitHandle = document.getElementById("split-handle-h");
    const bottomConsole = document.getElementById("bottom-console-pane");
    const clearConsoleBtn = document.getElementById("clear-console-btn");
    const terminalInput = document.getElementById("terminal-input");
    const terminalStdout = document.getElementById("terminal-stdout");
    let logsWebsocket = null;

    function initPhase4Console() {
        // Word Wrap
        if (toggleWrapBtn && codeTextarea) {
            toggleWrapBtn.addEventListener("click", () => {
                editorContainer.classList.toggle("wrap-mode");
                const isWrapped = editorContainer.classList.contains("wrap-mode");
                toggleWrapBtn.classList.toggle("btn-success", isWrapped);
                toggleWrapBtn.classList.toggle("btn-secondary", !isWrapped);
            });
        }

        // Tabs switching & process polling
        let taskPollInterval = null;
        const tasksTableBody = document.getElementById("tasks-table-body");

        function startTaskPolling() {
            stopTaskPolling();
            fetchRunningTasks();
            taskPollInterval = setInterval(fetchRunningTasks, 3000);
        }

        function stopTaskPolling() {
            if (taskPollInterval) {
                clearInterval(taskPollInterval);
                taskPollInterval = null;
            }
        }

        async function fetchRunningTasks() {
            if (!tasksTableBody) return;
            try {
                const res = await fetch("/api/tasks");
                const tasks = await res.json();
                
                if (tasks.length === 0) {
                    tasksTableBody.innerHTML = '<tr><td colspan="5" class="loading-spinner">No background tasks running.</td></tr>';
                    return;
                }

                let rowsHtml = "";
                tasks.forEach(task => {
                    const statusClass = task.status.toLowerCase();
                    const isRunning = task.status === "RUNNING";
                    
                    rowsHtml += `
                        <tr>
                            <td style="font-family: var(--font-mono); color: var(--accent-cyan);">${task.taskId}</td>
                            <td style="font-family: var(--font-mono); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${task.command}">${task.command}</td>
                            <td>${task.startTime}</td>
                            <td>
                                <span class="task-status-badge ${statusClass}">${task.status}</span>
                            </td>
                            <td>
                                <button class="btn-kill-task" data-id="${task.taskId}" ${isRunning ? "" : "disabled"}>
                                    Kill
                                </button>
                            </td>
                        </tr>
                    `;
                });

                tasksTableBody.innerHTML = rowsHtml;

                // Wire up kill buttons
                tasksTableBody.querySelectorAll(".btn-kill-task").forEach(btn => {
                    btn.addEventListener("click", async (e) => {
                        const tid = btn.getAttribute("data-id");
                        btn.disabled = true;
                        btn.textContent = "Killing...";
                        try {
                            const killRes = await fetch("/api/tasks/kill", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ task_id: tid })
                            });
                            const data = await killRes.json();
                            if (data.success) {
                                showNotification(`Killed task: ${tid}`, "success");
                            } else {
                                alert(`Failed to kill task: ${data.detail}`);
                            }
                        } catch (err) {
                            alert(`Error: ${err.message}`);
                        }
                        fetchRunningTasks();
                    });
                });

            } catch (err) {
                tasksTableBody.innerHTML = `<tr><td colspan="5" style="color: var(--accent-red)">Error: ${err.message}</td></tr>`;
            }
        }

        consoleTabs.forEach(tab => {
            tab.addEventListener("click", () => {
                consoleTabs.forEach(t => t.classList.remove("active"));
                tabContents.forEach(c => c.classList.remove("active"));
                
                tab.classList.add("active");
                const targetId = tab.getAttribute("data-tab");
                const targetContent = document.getElementById(targetId);
                if (targetContent) {
                    targetContent.classList.add("active");
                    if (targetId === "tab-logs") {
                        stopTaskPolling();
                        const container = document.getElementById("logs-container");
                        container.scrollTop = container.scrollHeight;
                    } else if (targetId === "tab-terminal") {
                        stopTaskPolling();
                        terminalStdout.scrollTop = terminalStdout.scrollHeight;
                    } else if (targetId === "tab-context") {
                        stopTaskPolling();
                        fetchContextInspector();
                    } else if (targetId === "tab-tasks") {
                        startTaskPolling();
                    } else {
                        stopTaskPolling();
                    }
                }
            });
        });

        // Split resizing
        if (splitHandle && bottomConsole) {
            let isDragging = false;
            let startY = 0;
            let startHeight = 0;

            splitHandle.addEventListener("mousedown", (e) => {
                isDragging = true;
                startY = e.clientY;
                startHeight = bottomConsole.offsetHeight;
                document.body.style.cursor = "row-resize";
                document.body.style.userSelect = "none";
            });

            document.addEventListener("mousemove", (e) => {
                if (!isDragging) return;
                const dy = e.clientY - startY;
                let newHeight = startHeight - dy;
                if (newHeight < 80) newHeight = 80;
                const maxHeight = window.innerHeight * 0.8;
                if (newHeight > maxHeight) newHeight = maxHeight;
                bottomConsole.style.height = `${newHeight}px`;
            });

            document.addEventListener("mouseup", () => {
                if (isDragging) {
                    isDragging = false;
                    document.body.style.cursor = "";
                    document.body.style.userSelect = "";
                }
            });
        }

        // Vertical split handle (editor vs preview in split-view)
        const splitHandleV = document.getElementById("split-handle-v");
        const editorContainer = document.querySelector(".editor-container");
        if (splitHandleV && editorContainer) {
            let vDragging = false;
            let vStartX = 0;
            let vLeftPct = 50;

            // Restore saved split position if available
            try {
                const saved = localStorage.getItem("dg-split-v");
                if (saved) vLeftPct = parseFloat(saved);
            } catch(e) {}

            splitHandleV.addEventListener("mousedown", (e) => {
                vDragging = true;
                vStartX = e.clientX;
                document.body.style.cursor = "col-resize";
                document.body.style.userSelect = "none";
                splitHandleV.classList.add("active");
            });

            document.addEventListener("mousemove", (e) => {
                if (!vDragging) return;
                const containerRect = editorContainer.getBoundingClientRect();
                const containerWidth = containerRect.width;
                if (containerWidth <= 0) return;
                const vPct = ((e.clientX - containerRect.left) / containerWidth) * 100;
                vLeftPct = Math.max(20, Math.min(80, vPct));
                const textarea = document.getElementById("code-textarea");
                const preview = document.getElementById("markdown-preview");
                if (textarea) textarea.style.flex = `1 1 ${vLeftPct}%`;
                if (preview) preview.style.flex = `1 1 ${100 - vLeftPct}%`;
            });

            document.addEventListener("mouseup", () => {
                if (vDragging) {
                    vDragging = false;
                    document.body.style.cursor = "";
                    document.body.style.userSelect = "";
                    splitHandleV.classList.remove("active");
                    try { localStorage.setItem("dg-split-v", vLeftPct.toString()); } catch(e) {}
                }
            });
        }

        // Clear console/logs
        if (clearConsoleBtn) {
            clearConsoleBtn.addEventListener("click", () => {
                const activeTab = document.querySelector(".console-tab.active").getAttribute("data-tab");
                if (activeTab === "tab-terminal") {
                    terminalStdout.innerHTML = "<div>Console cleared.</div>";
                } else if (activeTab === "tab-logs") {
                    const logs = document.getElementById("logs-container");
                    logs.innerHTML = "<div>Server activity log cleared locally.</div>";
                }
            });
        }

        // Terminal input execution
        if (terminalInput && terminalStdout) {
            terminalInput.addEventListener("keydown", async (e) => {
                if (e.key === "Enter") {
                    const cmd = terminalInput.value.trim();
                    if (!cmd) return;

                    terminalInput.value = "";
                    appendTerminalLine(`> ${cmd}`, "cmd-line");

                    try {
                        const res = await fetch("/api/terminal", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                command: cmd,
                                cwd: currentConfig?.workspace?.root_path || "."
                            })
                        });
                        const data = await res.json();
                        if (data.aborted) {
                            appendTerminalLine("[-] Command execution denied by user.", "cmd-error");
                        } else if (data.success) {
                            appendTerminalLine(data.output, "cmd-stdout");
                        } else {
                            appendTerminalLine(`Error: ${data.detail || data.output || "Execution failed."}`, "cmd-error");
                        }
                    } catch (err) {
                        appendTerminalLine(`Failed to dispatch command: ${err.message}`, "cmd-error");
                    }
                }
            });
        }

        connectLogsWebSocket();
    }

    async function fetchContextInspector() {
        if (!contextPre) return;
        contextPre.textContent = "Loading hydrated system context prompt from server...";
        try {
            const res = await fetch("/api/config/context");
            const data = await res.json();
            if (data && data.context) {
                contextPre.textContent = data.context;
            } else {
                contextPre.textContent = "Error: System context is empty or failed to load.";
            }
        } catch (err) {
            contextPre.textContent = `Failed to fetch system context: ${err.message}`;
        }
    }

    function appendTerminalLine(text, className = "") {
        const line = document.createElement("div");
        line.className = className;
        line.textContent = text;
        terminalStdout.appendChild(line);
        terminalStdout.scrollTop = terminalStdout.scrollHeight;
    }

    function connectLogsWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
        const logsContainer = document.getElementById("logs-container");

        logsWebsocket = new WebSocket(wsUrl);

        logsWebsocket.onmessage = (event) => {
            const msg = event.data;
            if (msg && logsContainer) {
                const logLine = document.createElement("div");
                logLine.textContent = msg;
                logsContainer.appendChild(logLine);
                
                const isNearBottom = logsContainer.scrollHeight - logsContainer.clientHeight - logsContainer.scrollTop < 60;
                if (isNearBottom) {
                    logsContainer.scrollTop = logsContainer.scrollHeight;
                }
            }
        };

        logsWebsocket.onclose = () => {
            setTimeout(connectLogsWebSocket, 5000);
        };
    }

    // 5. Chat History Operations
    const btnToggleHistory = document.getElementById("btn-toggle-history");
    const chatHistoryDrawer = document.getElementById("chat-history-drawer");
    const btnNewChat = document.getElementById("btn-new-chat");
    const historyList = document.getElementById("history-list");

    if (btnToggleHistory && chatHistoryDrawer && btnNewChat && historyList) {
        btnToggleHistory.addEventListener("click", () => {
            chatHistoryDrawer.classList.toggle("show");
            if (chatHistoryDrawer.classList.contains("show")) {
                loadHistorySessions();
            }
        });

        btnNewChat.addEventListener("click", async () => {
            try {
                const res = await fetch("/api/chats/new", { method: "POST" });
                const data = await res.json();
                if (data.success) {
                    chatMessages.innerHTML = `
                        <div class="system-welcome-card">
                            <div class="somatic-pulse"></div>
                            <h3>Attunement Core Active</h3>
                            <p>Wired natively into the local 14B rig. Tracking threads with warmth and torque.</p>
                        </div>
                    `;
                    chatHistoryDrawer.classList.remove("show");
                    showNotification("Started new chat session", "success");
                }
            } catch (err) {
                alert(`Failed to start new chat: ${err.message}`);
            }
        });

        async function loadHistorySessions() {
            historyList.innerHTML = '<div class="loading-spinner">Loading chat history...</div>';
            try {
                const res = await fetch("/api/chats/list");
                const sessions = await res.json();
                historyList.innerHTML = "";
                
                if (sessions.length === 0) {
                    historyList.innerHTML = '<div class="loading-spinner">No past chats found.</div>';
                    return;
                }

                sessions.forEach(session => {
                    const item = document.createElement("div");
                    item.className = "history-item";
                    item.innerHTML = `
                        <div class="history-item-time">${session.time}</div>
                        <div class="history-item-title">${escapeHtml(session.title)}</div>
                        <div class="history-item-preview">${escapeHtml(session.preview || "No assistant response.")}</div>
                    `;
                    item.addEventListener("click", () => loadSession(session.id));
                    historyList.appendChild(item);
                });
            } catch (err) {
                historyList.innerHTML = `<div class="loading-spinner error">Failed: ${err.message}</div>`;
            }
        }

        async function loadSession(id) {
            try {
                const res = await fetch(`/api/chats/load?id=${encodeURIComponent(id)}`);
                const data = await res.json();
                if (data.success && data.history) {
                    renderConversation(data.history);
                    chatHistoryDrawer.classList.remove("show");
                    showNotification("Chat session loaded", "success");
                } else {
                    alert(`Failed to load chat: ${data.detail || "Unknown error"}`);
                }
            } catch (err) {
                alert(`Failed to load chat: ${err.message}`);
            }
        }

        function renderConversation(history) {
            chatMessages.innerHTML = "";
            let activeToolCardsInDom = {};

            history.forEach(msg => {
                if (msg.role === "system") return;
                
                if (msg.role === "user") {
                    const bubble = document.createElement("div");
                    bubble.className = "message user";
                    bubble.textContent = msg.content;
                    chatMessages.appendChild(bubble);
                } else if (msg.role === "assistant") {
                    if (msg.content) {
                        const bubble = document.createElement("div");
                        bubble.className = "message assistant";
                        bubble.textContent = msg.content;
                        chatMessages.appendChild(bubble);
                    }
                    if (msg.tool_calls) {
                        msg.tool_calls.forEach(tc => {
                            const toolEl = document.createElement("details");
                            toolEl.className = "tool-card success";
                            toolEl.id = `hist-tool-${tc.id}`;
                            toolEl.open = false;
                            
                            let prettyArgs = "";
                            try {
                                prettyArgs = typeof tc.function.arguments === "object" ? JSON.stringify(tc.function.arguments, null, 2) : String(tc.function.arguments);
                            } catch {
                                prettyArgs = String(tc.function.arguments);
                            }

                            toolEl.innerHTML = `
                                <summary class="tool-card-title">
                                    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
                                    <span>Completed Tool: ${tc.function.name}</span>
                                </summary>
                                <div class="tool-card-output">${prettyArgs}</div>
                            `;
                            chatMessages.appendChild(toolEl);
                            activeToolCardsInDom[tc.id] = toolEl;
                        });
                    }
                } else if (msg.role === "tool") {
                    const toolCard = activeToolCardsInDom[msg.tool_call_id];
                    if (toolCard) {
                        const outputContainer = toolCard.querySelector(".tool-card-output");
                        if (outputContainer) {
                            let prettyResult = "";
                            try {
                                prettyResult = typeof msg.content === "object" ? JSON.stringify(msg.content, null, 2) : String(msg.content);
                            } catch {
                                prettyResult = String(msg.content);
                            }
                            outputContainer.textContent = prettyResult;
                        }
                    }
                }
            });
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function escapeHtml(str) {
            if (!str) return "";
            return str
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }
    }

    // 6. Activity Bar Switching & Extensions Panel
    const btnNavExplorer = document.getElementById("btn-nav-explorer");
    const btnNavExtensions = document.getElementById("btn-nav-extensions");
    const panelExplorer = document.getElementById("panel-explorer");
    const panelExtensions = document.getElementById("panel-extensions");
    const extensionsList = document.getElementById("extensions-list");
    const extensionsSearch = document.getElementById("extensions-search");

    if (btnNavExplorer && btnNavExtensions && panelExplorer && panelExtensions) {
        btnNavExplorer.addEventListener("click", () => {
            btnNavExplorer.classList.add("active");
            btnNavExtensions.classList.remove("active");
            panelExplorer.classList.add("active");
            panelExtensions.classList.remove("active");
        });

        btnNavExtensions.addEventListener("click", () => {
            btnNavExtensions.classList.add("active");
            btnNavExplorer.classList.remove("active");
            panelExtensions.classList.add("active");
            panelExplorer.classList.remove("active");
            loadExtensions();
        });
    }

    async function loadExtensions() {
        if (!extensionsList) return;
        extensionsList.innerHTML = '<div class="loading-spinner">Loading extensions...</div>';
        try {
            const res = await fetch("/api/extensions/list");
            const data = await res.json();
            if (data.extensions) {
                renderExtensions(data.extensions);
                
                if (extensionsSearch) {
                    extensionsSearch.oninput = () => {
                        const query = extensionsSearch.value.toLowerCase();
                        const filtered = data.extensions.filter(ext => 
                            ext.name.toLowerCase().includes(query) || 
                            ext.description.toLowerCase().includes(query) ||
                            ext.id.toLowerCase().includes(query)
                        );
                        renderExtensions(filtered);
                    };
                }
            } else {
                extensionsList.innerHTML = '<div class="loading-spinner error">Failed to load extensions list.</div>';
            }
        } catch (err) {
            extensionsList.innerHTML = `<div class="loading-spinner error">Error: ${err.message}</div>`;
        }
    }

    function renderExtensions(list) {
        if (list.length === 0) {
            extensionsList.innerHTML = '<div class="loading-spinner">No extensions found.</div>';
            return;
        }
        let html = "";
        list.forEach(ext => {
            html += `
                <div class="extension-card" title="${ext.id}">
                    <div class="extension-name">${ext.name}</div>
                    <div class="extension-version">v${ext.version}</div>
                    <div class="extension-desc">${ext.description || "No description provided."}</div>
                </div>
            `;
        });
        extensionsList.innerHTML = html;
    }

    // 7. Settings Modal
    const settingsPortal = document.getElementById("settings-portal");
    const btnNavSettings = document.getElementById("btn-nav-settings");
    const settingsCloseBtn = document.getElementById("settings-close-btn");
    const settingsSaveBtn = document.getElementById("settings-save-btn");
    const settingsServerLocation = document.getElementById("settings-server-location");
    const settingsAttunement = document.getElementById("settings-attunement");
    const settingsOrchestrator = document.getElementById("settings-orchestrator");
    const settingsProvidersList = document.getElementById("settings-providers-list");
    const settingsAddProviderBtn = document.getElementById("settings-add-provider");
    const settingsRootPath = document.getElementById("settings-root-path");
    const settingsBackupPath = document.getElementById("settings-backup-path");

    let settingsDirty = false;

    function openSettings() {
        // Load current config into form
        if (!currentConfig) return;
        settingsServerLocation.value = currentConfig.server_location || "";
        settingsRootPath.value = currentConfig.workspace?.root_path || "";
        settingsBackupPath.value = currentConfig.workspace?.backup_path || "";
        renderSettingsProviders();
        renderSettingsRouting();
        settingsPortal.classList.add("show");
        settingsDirty = false;
    }

    function closeSettings() {
        settingsPortal.classList.remove("show");
    }

    function renderSettingsProviders() {
        if (!currentConfig?.api?.providers) return;
        const providers = currentConfig.api.providers;
        settingsProvidersList.innerHTML = "";
        
        Object.keys(providers).forEach((name, idx) => {
            const p = providers[name];
            const card = document.createElement("div");
            card.className = "settings-provider-card";
            card.dataset.providerIdx = idx;
            card.innerHTML = `
                <div class="settings-provider-header">
                    <span class="settings-provider-name">${escHtml(name)}</span>
                    <button class="btn-remove-provider" data-provider-name="${escHtml(name)}">Remove</button>
                </div>
                <div class="settings-provider-fields">
                    <div class="settings-provider-row">
                        <div class="settings-field half">
                            <label>Base URL</label>
                            <input type="text" class="settings-input provider-base-url" value="${escHtml(p.base_url || '')}" placeholder="{server_location}" />
                        </div>
                        <div class="settings-field half">
                            <label>API Key</label>
                            <input type="password" class="settings-input provider-api-key" value="${escHtml(p.api_key || '')}" placeholder="sk-..." />
                        </div>
                    </div>
                    <div class="settings-provider-row">
                        <div class="settings-field half">
                            <label>Model</label>
                            <input type="text" class="settings-input provider-model" value="${escHtml(p.model || '')}" placeholder="model:latest" />
                        </div>
                        <div class="settings-field third">
                            <label>Temp</label>
                            <input type="number" step="0.1" min="0" max="2" class="settings-input provider-temp" value="${p.temperature ?? 0.7}" />
                        </div>
                        <div class="settings-field third">
                            <label>Max Tokens</label>
                            <input type="number" class="settings-input provider-max-tokens" value="${p.max_tokens || ''}" placeholder="auto" />
                        </div>
                    </div>
                    <div class="settings-provider-row">
                        <label style="display:flex;align-items:center;gap:6px;font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">
                            <input type="checkbox" class="provider-live-dir" ${p.live_directory ? 'checked' : ''} />
                            Live Directory (query /v1/models for available models)
                        </label>
                    </div>
                </div>
            `;
            settingsProvidersList.appendChild(card);

            // Wire remove button
            card.querySelector(".btn-remove-provider").addEventListener("click", () => {
                delete currentConfig.api.providers[name];
                renderSettingsProviders();
                renderSettingsRouting();
                settingsDirty = true;
            });
        });
    }

    function renderSettingsRouting() {
        if (!currentConfig?.api?.providers) return;
        const names = Object.keys(currentConfig.api.providers);
        const attunement = currentConfig.api.routing?.attunement_core || "";
        const orchestrator = currentConfig.api.routing?.primary_orchestrator || "";
        
        [settingsAttunement, settingsOrchestrator].forEach(sel => {
            const currentVal = sel === settingsAttunement ? attunement : orchestrator;
            sel.innerHTML = "";
            names.forEach(n => {
                const opt = document.createElement("option");
                opt.value = n;
                opt.textContent = n;
                if (n === currentVal) opt.selected = true;
                sel.appendChild(opt);
            });
        });
    }

    // Wire settings button
    if (btnNavSettings) {
        btnNavSettings.addEventListener("click", () => {
            // Fetch fresh config in case it changed
            fetch("/api/config").then(r => r.json()).then(cfg => {
                currentConfig = cfg;
                openSettings();
            }).catch(() => {
                openSettings();
            });
        });
    }

    if (settingsCloseBtn) {
        settingsCloseBtn.addEventListener("click", closeSettings);
    }

    // Close on overlay click
    if (settingsPortal) {
        settingsPortal.addEventListener("click", (e) => {
            if (e.target === settingsPortal) closeSettings();
        });
    }

    // Add provider
    if (settingsAddProviderBtn) {
        settingsAddProviderBtn.addEventListener("click", () => {
            const name = prompt("Provider name (e.g. openwebui-local):");
            if (!name || !name.trim()) return;
            const cleanName = name.trim();
            if (currentConfig.api.providers[cleanName]) {
                alert(`Provider "${cleanName}" already exists.`);
                return;
            }
            currentConfig.api.providers[cleanName] = {
                base_url: "{server_location}",
                api_key: "",
                model: "",
                temperature: 0.7
            };
            renderSettingsProviders();
            renderSettingsRouting();
            settingsDirty = true;
        });
    }

    // Save settings
    if (settingsSaveBtn) {
        settingsSaveBtn.addEventListener("click", async () => {
            // Read server_location
            currentConfig.server_location = settingsServerLocation.value.trim() || "http://localhost:11434/v1";
            
            // Read routing
            if (!currentConfig.api.routing) currentConfig.api.routing = {};
            currentConfig.api.routing.attunement_core = settingsAttunement.value;
            currentConfig.api.routing.primary_orchestrator = settingsOrchestrator.value;
            
            // Read workspace
            if (!currentConfig.workspace) currentConfig.workspace = {};
            currentConfig.workspace.root_path = settingsRootPath.value.trim();
            currentConfig.workspace.backup_path = settingsBackupPath.value.trim();
            
            // Read provider fields from the DOM cards
            const cards = settingsProvidersList.querySelectorAll(".settings-provider-card");
            cards.forEach(card => {
                const nameEl = card.querySelector(".settings-provider-name");
                if (!nameEl) return;
                const name = nameEl.textContent;
                const prov = currentConfig.api.providers[name];
                if (!prov) return;
                
                prov.base_url = card.querySelector(".provider-base-url")?.value || "{server_location}";
                prov.api_key = card.querySelector(".provider-api-key")?.value || "";
                prov.model = card.querySelector(".provider-model")?.value || "";
                prov.temperature = parseFloat(card.querySelector(".provider-temp")?.value) || 0.7;
                const maxTokens = parseInt(card.querySelector(".provider-max-tokens")?.value);
                if (maxTokens) {
                    prov.max_tokens = maxTokens;
                } else {
                    delete prov.max_tokens;
                }
                prov.live_directory = card.querySelector(".provider-live-dir")?.checked || false;
            });

            try {
                const res = await fetch("/api/config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(currentConfig)
                });
                const data = await res.json();
                if (data.success) {
                    showNotification("Configuration saved and hot-reloaded.", "success");
                    closeSettings();
                    // Re-initialize engine selector with new providers
                    initEngineSelector();
                } else {
                    alert(`Failed to save config: ${data.detail || "Unknown error"}`);
                }
            } catch (err) {
                alert(`Failed to save: ${err.message}`);
            }
        });
    }

    function escHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Startup Init
    loadWorkspaceTree();
    connectWebSocket();
    initEngineSelector();
    initPhase4Console();
});
