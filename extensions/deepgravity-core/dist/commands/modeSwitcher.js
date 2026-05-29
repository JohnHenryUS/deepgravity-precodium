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
exports.ModeSwitcher = void 0;
const vscode = __importStar(require("vscode"));
class ModeSwitcher {
    statusBarItem;
    _currentMode = 'ide';
    _disposables = [];
    constructor(statusBarItem) {
        this.statusBarItem = statusBarItem;
        // Register quick pick for mode switching on click
        this._disposables.push(vscode.commands.registerCommand('deepgravity.switchMode', () => {
            this.showModePicker();
        }));
        // Make the status bar item open the mode picker
        this.statusBarItem.command = 'deepgravity.switchMode';
    }
    get currentMode() {
        return this._currentMode;
    }
    setMode(mode) {
        this._currentMode = mode;
        // Save to workspace state
        const ext = vscode.extensions.getExtension('deepgravity-core');
        if (ext) {
            ext.exports?.setLastMode?.(mode);
        }
        // Notify the user
        const modeNames = {
            ide: 'IDE — Editor centered',
            cce: 'CCE — Conversation centered',
            doc: 'Document — Writing centered'
        };
        vscode.window.showInformationMessage(`DeepGravity: ${modeNames[mode]}`);
    }
    async showModePicker() {
        const selection = await vscode.window.showQuickPick([
            { label: '$(symbol-event) IDE Mode', description: 'Editor centered, Dora in sidebar', id: 'ide' },
            { label: '$(comment-discussion) CCE Mode', description: 'Dora centered, editor as preview', id: 'cce' },
            { label: '$(book) Document Mode', description: 'Writing centered, Dora compact bar', id: 'doc' },
        ], {
            placeHolder: `Current mode: ${this._currentMode.toUpperCase()}`,
            title: 'DeepGravity Layout Mode'
        });
        if (selection) {
            switch (selection.id) {
                case 'ide':
                    vscode.commands.executeCommand('deepgravity.ideMode');
                    break;
                case 'cce':
                    vscode.commands.executeCommand('deepgravity.cceMode');
                    break;
                case 'doc':
                    vscode.commands.executeCommand('deepgravity.docMode');
                    break;
            }
        }
    }
    dispose() {
        while (this._disposables.length) {
            const d = this._disposables.pop();
            if (d)
                d.dispose();
        }
    }
}
exports.ModeSwitcher = ModeSwitcher;
//# sourceMappingURL=modeSwitcher.js.map