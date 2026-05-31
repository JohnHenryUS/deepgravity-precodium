import * as vscode from 'vscode';
import { DoraChatPanel, DoraChatViewProvider } from './panels/doraChat';
import { ModeSwitcher } from './commands/modeSwitcher';

let doraChat: DoraChatPanel | undefined;
let modeSwitcher: ModeSwitcher | undefined;
let statusBarItem: vscode.StatusBarItem | undefined = undefined;
let wsStatusItem: vscode.StatusBarItem | undefined = undefined;
let healthPollInterval: NodeJS.Timeout | undefined = undefined;

export function activate(context: vscode.ExtensionContext) {
    console.log('DeepGravity Core activating...');

    // Register WebviewViewProvider for the sidebar chat pane
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            DoraChatViewProvider.viewType,
            new DoraChatViewProvider(context)
        )
    );

    // ── Status bar mode indicator (right side) ──
    const sb = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );
    sb.text = "$(symbol-event) IDE";
    sb.tooltip = "DeepGravity — Switch Layout Mode";
    sb.command = "deepgravity.ideMode";
    sb.show();
    context.subscriptions.push(sb);

    // ── Mode switcher ──
    modeSwitcher = new ModeSwitcher(sb);
    context.subscriptions.push(modeSwitcher);
    statusBarItem = sb;

    // ── WebSocket health indicator (left side) ──
    const wsSb = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left,
        0
    );
    wsSb.text = "$(circle-slash) Dora";
    wsSb.tooltip = "DeepGravity — Backend status unknown";
    wsSb.show();
    context.subscriptions.push(wsSb);
    wsStatusItem = wsSb;

    // Poll backend health every 10 seconds
    async function pollHealth() {
        try {
            const resp = await fetch('http://127.0.0.1:19850/api/health');
            if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
            const data = await resp.json();
            if (data.ws_connected) {
                wsSb.text = "$(circle-filled) Dora";
                wsSb.tooltip = "DeepGravity — Backend connected";
                wsSb.color = '#4ec9b0';
            } else {
                wsSb.text = "$(debug-disconnect) Dora";
                wsSb.tooltip = "DeepGravity — Backend running, no chat WebSocket";
                wsSb.color = '#dcdcaa';
            }
        } catch (e: any) {
            wsSb.text = "$(circle-slash) Dora";
            wsSb.tooltip = "DeepGravity — Backend unreachable: " + (e.message || 'unknown');
            wsSb.color = '#f44747';
        }
    }
    pollHealth();
    healthPollInterval = setInterval(pollHealth, 10000);
    context.subscriptions.push({ dispose: () => { if (healthPollInterval) clearInterval(healthPollInterval); } });

    // ── Commands ──
    context.subscriptions.push(
        vscode.commands.registerCommand('deepgravity.ideMode', () => {
            modeSwitcher?.setMode('ide');
            sb.text = "$(symbol-event) IDE";
            sb.tooltip = "DeepGravity — IDE Mode (code centered)";
            applyIdeLayout();
        }),

        vscode.commands.registerCommand('deepgravity.cceMode', () => {
            modeSwitcher?.setMode('cce');
            sb.text = "$(symbol-event) CCE";
            sb.tooltip = "DeepGravity — CCE Mode (conversation centered)";
            // CCE layout: conversation centered, editor as preview
            vscode.commands.executeCommand('workbench.action.togglePanel', false);
            if (!doraChat) {
                doraChat = new DoraChatPanel(context);
            }
            doraChat.show();
        }),

        vscode.commands.registerCommand('deepgravity.docMode', () => {
            modeSwitcher?.setMode('doc');
            sb.text = "$(symbol-event) DOC";
            sb.tooltip = "DeepGravity — Document Mode (writing centered)";
            applyDocLayout();
        }),

        vscode.commands.registerCommand('deepgravity.openDora', () => {
            if (!doraChat) {
                doraChat = new DoraChatPanel(context);
            }
            doraChat.show();
        }),

        vscode.commands.registerCommand('deepgravity.toggleTimeline', () => {
            vscode.commands.executeCommand('workbench.view.extension.deepgravity-timeline');
        })
    );

    // ── Auto-open Dora Chat on first activation ──
    const hasOpenedBefore = context.globalState.get<boolean>('deepgravity.hasOpenedBefore', false);
    if (!hasOpenedBefore) {
        context.globalState.update('deepgravity.hasOpenedBefore', true);
        // Open Dora Chat after a short delay to let the workbench settle
        setTimeout(() => {
            if (!doraChat) {
                doraChat = new DoraChatPanel(context);
            }
            doraChat.show();
        }, 1500);
    }

    // ── Restore last mode ──
    const lastMode = context.workspaceState.get<string>('deepgravity.lastMode', 'ide');
    if (lastMode === 'cce') {
        vscode.commands.executeCommand('deepgravity.cceMode');
    } else if (lastMode === 'doc') {
        vscode.commands.executeCommand('deepgravity.docMode');
    }

    console.log('DeepGravity Core activated.');
}

function applyIdeLayout() {
    vscode.commands.executeCommand('workbench.action.toggleSidebarVisibility', true);
    vscode.commands.executeCommand('workbench.action.togglePanel', true);
    vscode.commands.executeCommand('workbench.action.focusFirstEditorGroup');
}

function applyDocLayout() {
    vscode.commands.executeCommand('workbench.action.toggleSidebarVisibility', false);
    vscode.commands.executeCommand('workbench.action.togglePanel', false);
    vscode.commands.executeCommand('workbench.action.focusFirstEditorGroup');
}

export function deactivate() {
    console.log('DeepGravity Core deactivating.');
    doraChat?.dispose();
}
