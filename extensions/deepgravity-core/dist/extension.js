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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const doraChat_1 = require("./panels/doraChat");
const modeSwitcher_1 = require("./commands/modeSwitcher");
let doraChat;
let modeSwitcher;
let statusBarItem = undefined;
function activate(context) {
    console.log('DeepGravity Core activating...');
    // Register WebviewViewProvider for the sidebar chat pane
    context.subscriptions.push(vscode.window.registerWebviewViewProvider(doraChat_1.DoraChatViewProvider.viewType, new doraChat_1.DoraChatViewProvider(context)));
    // ── Status bar mode indicator ──
    const sb = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    sb.text = "$(symbol-event) IDE";
    sb.tooltip = "DeepGravity — Switch Layout Mode";
    sb.command = "deepgravity.ideMode";
    sb.show();
    context.subscriptions.push(sb);
    // ── Mode switcher ──
    modeSwitcher = new modeSwitcher_1.ModeSwitcher(sb);
    context.subscriptions.push(modeSwitcher);
    statusBarItem = sb;
    // ── Commands ──
    context.subscriptions.push(vscode.commands.registerCommand('deepgravity.ideMode', () => {
        modeSwitcher?.setMode('ide');
        sb.text = "$(symbol-event) IDE";
        sb.tooltip = "DeepGravity — IDE Mode (code centered)";
        applyIdeLayout();
    }), vscode.commands.registerCommand('deepgravity.cceMode', () => {
        modeSwitcher?.setMode('cce');
        sb.text = "$(symbol-event) CCE";
        sb.tooltip = "DeepGravity — CCE Mode (conversation centered)";
        // CCE layout: conversation centered, editor as preview
        vscode.commands.executeCommand('workbench.action.togglePanel', false);
        if (!doraChat) {
            doraChat = new doraChat_1.DoraChatPanel(context);
        }
        doraChat.show();
    }), vscode.commands.registerCommand('deepgravity.docMode', () => {
        modeSwitcher?.setMode('doc');
        sb.text = "$(symbol-event) DOC";
        sb.tooltip = "DeepGravity — Document Mode (writing centered)";
        applyDocLayout();
    }), vscode.commands.registerCommand('deepgravity.openDora', () => {
        if (!doraChat) {
            doraChat = new doraChat_1.DoraChatPanel(context);
        }
        doraChat.show();
    }), vscode.commands.registerCommand('deepgravity.toggleTimeline', () => {
        vscode.commands.executeCommand('workbench.view.extension.deepgravity-timeline');
    }));
    // ── Auto-open Dora Chat on first activation ──
    const hasOpenedBefore = context.globalState.get('deepgravity.hasOpenedBefore', false);
    if (!hasOpenedBefore) {
        context.globalState.update('deepgravity.hasOpenedBefore', true);
        // Open Dora Chat after a short delay to let the workbench settle
        setTimeout(() => {
            if (!doraChat) {
                doraChat = new doraChat_1.DoraChatPanel(context);
            }
            doraChat.show();
        }, 1500);
    }
    // ── Restore last mode ──
    const lastMode = context.workspaceState.get('deepgravity.lastMode', 'ide');
    if (lastMode === 'cce') {
        vscode.commands.executeCommand('deepgravity.cceMode');
    }
    else if (lastMode === 'doc') {
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
function deactivate() {
    console.log('DeepGravity Core deactivating.');
    doraChat?.dispose();
}
//# sourceMappingURL=extension.js.map