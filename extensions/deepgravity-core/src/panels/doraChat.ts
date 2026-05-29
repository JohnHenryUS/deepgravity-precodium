import * as vscode from 'vscode';
import * as path from 'path';

function getSharedConfig(workspaceRoot: string | undefined): any {
    try {
        if (!workspaceRoot) return null;
        const configPath = path.join(workspaceRoot, 'config.json');
        const fs = require('fs');
        if (fs.existsSync(configPath)) {
            const raw = fs.readFileSync(configPath, 'utf-8');
            return JSON.parse(raw);
        }
    } catch (e) {}
    return null;
}

function renderChatHtml(context: vscode.ExtensionContext, workspaceRoot: string | undefined): string {
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
export class DoraChatPanel {
    public static readonly viewType = 'deepgravity.doraChat';
    private _panel: vscode.WebviewPanel | undefined;
    private _disposables: vscode.Disposable[] = [];

    constructor(private context: vscode.ExtensionContext) {}

    public show() {
        if (this._panel) {
            this._panel.reveal(vscode.ViewColumn.Beside);
            return;
        }

        this._panel = vscode.window.createWebviewPanel(
            DoraChatPanel.viewType,
            'Dora Chat',
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.joinPath(this.context.extensionUri, 'media')
                ]
            }
        );

        const folders = vscode.workspace.workspaceFolders;
        const workspaceRoot = folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;

        this._panel.webview.html = renderChatHtml(this.context, workspaceRoot);
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
    }

    public dispose() {
        this._panel?.dispose();
        while (this._disposables.length) {
            const d = this._disposables.pop();
            if (d) d.dispose();
        }
    }
}

// ── WebviewView Provider (Sidebar Pane) ──
export class DoraChatViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'deepgravity.doraChat';
    private _view?: vscode.WebviewView;

    constructor(private readonly context: vscode.ExtensionContext) {}

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        token: vscode.CancellationToken
    ) {
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
