"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.DoraChatViewProvider = exports.DoraChatPanel = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
function getSharedConfig(workspaceRoot) {
    try {
        if (!workspaceRoot)
            return null;
        const configPath = path.join(workspaceRoot, 'config.json');
        const fs = require('fs');
        if (fs.existsSync(configPath)) {
            const raw = fs.readFileSync(configPath, 'utf-8');
            return JSON.parse(raw);
        }
    }
    catch (e) { }
    return null;
}
function renderChatHtml(context, workspaceRoot) {
    const cfg = getSharedConfig(workspaceRoot);
    const serverCfg = cfg?.server;
    const host = serverCfg?.host === '0.0.0.0' ? '127.0.0.1' : (serverCfg?.host || '127.0.0.1');
    const port = serverCfg?.port || 19850;
    const serverUrl = `http://${host}:${port}/?embed=chat&t=${Date.now()}`;
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src http://${host}:${port} http://localhost:${port}; connect-src http://${host}:${port} ws://${host}:${port}; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
    <title>Dora Chat</title>
    <style>
        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            background-color: #0a1520;
        }
        iframe {
            border: none;
            width: 100%;
            height: 100%;
        }
    </style>
</head>
<body>
    <iframe src="${serverUrl}" sandbox="allow-scripts allow-forms allow-same-origin allow-downloads"></iframe>
</body>
</html>`;
}
// ── WebviewPanel Provider (Editor Tab / Center Workspace) ──
class DoraChatPanel {
    context;
    static viewType = 'deepgravity.doraChat';
    _panel;
    _disposables = [];
    constructor(context) {
        this.context = context;
    }
    show() {
        if (this._panel) {
            this._panel.reveal(vscode.ViewColumn.Beside);
            return;
        }
        this._panel = vscode.window.createWebviewPanel(DoraChatPanel.viewType, 'Dora Chat', vscode.ViewColumn.Beside, {
            enableScripts: true,
            retainContextWhenHidden: true,
            localResourceRoots: [
                vscode.Uri.joinPath(this.context.extensionUri, 'media')
            ]
        });
        const folders = vscode.workspace.workspaceFolders;
        const workspaceRoot = folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
        this._panel.webview.html = renderChatHtml(this.context, workspaceRoot);
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
    }
    dispose() {
        this._panel?.dispose();
        while (this._disposables.length) {
            const d = this._disposables.pop();
            if (d)
                d.dispose();
        }
    }
}
exports.DoraChatPanel = DoraChatPanel;
// ── WebviewView Provider (Sidebar Pane) ──
class DoraChatViewProvider {
    context;
    static viewType = 'deepgravity.doraChat';
    _view;
    constructor(context) {
        this.context = context;
    }
    resolveWebviewView(webviewView, context, token) {
        this._view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [
                vscode.Uri.joinPath(this.context.extensionUri, 'media')
            ]
        };
        const folders = vscode.workspace.workspaceFolders;
        const workspaceRoot = folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
        webviewView.webview.html = renderChatHtml(this.context, workspaceRoot);
    }
}
exports.DoraChatViewProvider = DoraChatViewProvider;
//# sourceMappingURL=doraChat.js.map