// DeepGravity Chat — VS Code chat participant for DeepGravity backend.
// Uses native WebSocket (Node 18+ / Electron) — no npm dependencies required.
// Reads address from DEEPGRAVITY_BACKEND_URL env var, falls back to
// deepgravity.backendUrl setting, falls back to localhost:19850.

const vscode = require('vscode');

// Use native WebSocket if available (Node 18+ / Electron 25+)
const NativeWebSocket = globalThis.WebSocket;
const wsAvailable = typeof NativeWebSocket !== 'undefined';

let backendUrl = 'http://localhost:19850';
let ws = null;
let reconnectTimer = null;
let statusBarItem = null;

function resolveBackendUrl() {
    const envUrl = process.env.DEEPGRAVITY_BACKEND_URL;
    if (envUrl) return envUrl;

    const configUrl = vscode.workspace.getConfiguration('deepgravity').get('backendUrl');
    if (configUrl) return configUrl;

    return 'http://localhost:19850';
}

function wsUrl(httpUrl) {
    return httpUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:') + '/ws/chat';
}

function updateStatusBar(state, detail) {
    if (!statusBarItem) {
        statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
        statusBarItem.command = 'deepgravity.chat.reconnect';
        statusBarItem.tooltip = 'Click to reconnect';
    }
    statusBarItem.text = `$(hubot) DeepGravity: ${state}`;
    statusBarItem.tooltip = detail || state;
    statusBarItem.show();
}

function connectWebSocket(url, chatParticipant) {
    if (!wsAvailable) return;

    if (ws) {
        try { ws.close(); } catch (_) {}
        ws = null;
    }

    const fullUrl = wsUrl(url);
    updateStatusBar('Connecting...', fullUrl);

    let sock;
    try {
        sock = new NativeWebSocket(fullUrl);
    } catch (err) {
        updateStatusBar('Disconnected', err.message);
        return;
    }
    ws = sock;

    sock.onopen = () => {
        updateStatusBar('Connected', fullUrl);
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
    };

    sock.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleServerMessage(msg);
        } catch (_) {}
    };

    sock.onclose = () => {
        updateStatusBar('Disconnected', 'Connection closed');
        if (ws === sock) scheduleReconnect(url, chatParticipant);
    };

    sock.onerror = () => {
        updateStatusBar('Error', 'Connection failed');
        if (ws === sock) scheduleReconnect(url, chatParticipant);
    };
}

function scheduleReconnect(url, chatParticipant) {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket(url, chatParticipant);
    }, 5000);
}

const pendingRequests = new Map();
let nextRequestId = 1;

function handleServerMessage(msg) {
    const type = msg.type;

    if (type === 'stream') {
        for (const [, state] of pendingRequests) {
            if (state.active) {
                const chunk = msg.data;
                if (chunk) {
                    if (chunk.content) {
                        state.stream.markdown(chunk.content);
                    }
                    if (chunk.reasoning_content) {
                        state.stream.markdown(`*${chunk.reasoning_content}*\n\n`);
                    }
                    if (chunk.tool_calls) {
                        for (const tc of chunk.tool_calls) {
                            const name = tc.function?.name || 'unknown';
                            state.stream.markdown(`\n_Using tool: \`${name}\`_\n`);
                        }
                    }
                }
                break;
            }
        }
    } else if (type === 'complete') {
        for (const [, state] of pendingRequests) {
            if (state.active) {
                state.active = false;
                break;
            }
        }
    } else if (type === 'error') {
        for (const [, state] of pendingRequests) {
            if (state.active) {
                state.stream.markdown(`\n\n**Error:** ${msg.message}`);
                state.active = false;
                break;
            }
        }
    } else if (type === 'approval_required') {
        handleApproval(msg);
    } else if (type === 'open_file') {
        if (msg.path) {
            vscode.workspace.openTextDocument(msg.path).then(doc => {
                vscode.window.showTextDocument(doc);
            }, () => {});
        }
    }
}

async function handleApproval(msg) {
    const action = msg.action;
    let detail = '';
    if (action === 'write') {
        detail = `Write to: ${msg.file_path}`;
    } else if (action === 'command') {
        detail = `Run: ${msg.command}`;
    }

    const choice = await vscode.window.showInformationMessage(
        `DeepGravity requests approval: ${action}`,
        { modal: true, detail },
        'Approve',
        'Deny'
    );

    if (ws && ws.readyState === NativeWebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'approval_response',
            approved: choice === 'Approve'
        }));
    }
}

function activate(context) {
    backendUrl = resolveBackendUrl();

    // Warn if native WebSocket isn't available (very old runtime)
    if (!wsAvailable) {
        console.warn('[DeepGravity Chat] Native WebSocket not available in this runtime. Chat participant requires Node.js 18+ or Electron 25+.');
    }

    // Register chat participant — gracefully handle if API is unavailable
    let participant;
    try {
        participant = vscode.chat.createChatParticipant('deepgravity.chat', async (request, context, stream, token) => {
            if (!wsAvailable) {
                stream.markdown('DeepGravity Chat requires a newer runtime with native WebSocket support.\n\nCheck that your editor is running on a recent version.');
                return;
            }

            const requestId = nextRequestId++;
            const state = { active: true, stream, requestId };
            pendingRequests.set(requestId, state);

            token.onCancellationRequested(() => {
                state.active = false;
                pendingRequests.delete(requestId);
                if (ws && ws.readyState === NativeWebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'stop_execution' }));
                }
            });

            if (!ws || ws.readyState !== NativeWebSocket.OPEN) {
                connectWebSocket(backendUrl, participant);
                // Wait briefly for connection
                await new Promise(resolve => {
                    let waited = 0;
                    const check = () => {
                        if (ws && ws.readyState === NativeWebSocket.OPEN) {
                            resolve();
                        } else if (waited > 30) {
                            resolve();
                        } else {
                            waited++;
                            setTimeout(check, 200);
                        }
                    };
                    check();
                });
            }

            if (!ws || ws.readyState !== NativeWebSocket.OPEN) {
                stream.markdown('Could not connect to DeepGravity backend. Check `deepgravity.backendUrl` setting or `DEEPGRAVITY_BACKEND_URL` environment variable.');
                pendingRequests.delete(requestId);
                return;
            }

            const payload = {
                type: 'user_message',
                content: request.prompt
            };

            // Inject active editor file as context
            const editor = vscode.window.activeTextEditor;
            if (editor) {
                const doc = editor.document;
                const relPath = vscode.workspace.asRelativePath(doc.uri);
                if (relPath) {
                    payload.active_file = relPath;
                }
            }

            ws.send(JSON.stringify(payload));

            await new Promise(resolve => {
                const interval = setInterval(() => {
                    if (!state.active) {
                        clearInterval(interval);
                        pendingRequests.delete(requestId);
                        resolve();
                    }
                }, 100);
            });
        });

        participant.iconPath = new vscode.ThemeIcon('hubot');

        context.subscriptions.push(
            vscode.commands.registerCommand('deepgravity.chat.reconnect', () => {
                connectWebSocket(backendUrl, participant);
            })
        );

        connectWebSocket(backendUrl, participant);

        context.subscriptions.push(participant);
        if (statusBarItem) context.subscriptions.push(statusBarItem);
    } catch (err) {
        console.warn('[DeepGravity Chat] Could not register chat participant:', err.message);
        console.warn('[DeepGravity Chat] The chat participant API may not be available in this editor version.');
    }
}

function deactivate() {
    if (ws) {
        try { ws.close(); } catch (_) {}
        ws = null;
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
}

module.exports = { activate, deactivate };
