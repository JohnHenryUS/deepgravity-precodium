import * as vscode from 'vscode';

export type LayoutMode = 'ide' | 'cce' | 'doc';

export class ModeSwitcher implements vscode.Disposable {
    private _currentMode: LayoutMode = 'ide';
    private _disposables: vscode.Disposable[] = [];

    constructor(private statusBarItem: vscode.StatusBarItem) {
        // Register quick pick for mode switching on click
        this._disposables.push(
            vscode.commands.registerCommand('deepgravity.switchMode', () => {
                this.showModePicker();
            })
        );

        // Make the status bar item open the mode picker
        this.statusBarItem.command = 'deepgravity.switchMode';
    }

    public get currentMode(): LayoutMode {
        return this._currentMode;
    }

    public setMode(mode: LayoutMode) {
        this._currentMode = mode;

        // Save to workspace state
        const ext = vscode.extensions.getExtension('deepgravity-core');
        if (ext) {
            ext.exports?.setLastMode?.(mode);
        }

        // Notify the user
        const modeNames: Record<LayoutMode, string> = {
            ide: 'IDE — Editor centered',
            cce: 'CCE — Conversation centered',
            doc: 'Document — Writing centered'
        };
        vscode.window.showInformationMessage(`DeepGravity: ${modeNames[mode]}`);
    }

    public async showModePicker() {
        const selection = await vscode.window.showQuickPick(
            [
                { label: '$(symbol-event) IDE Mode', description: 'Editor centered, Dora in sidebar', id: 'ide' as LayoutMode },
                { label: '$(comment-discussion) CCE Mode', description: 'Dora centered, editor as preview', id: 'cce' as LayoutMode },
                { label: '$(book) Document Mode', description: 'Writing centered, Dora compact bar', id: 'doc' as LayoutMode },
            ],
            {
                placeHolder: `Current mode: ${this._currentMode.toUpperCase()}`,
                title: 'DeepGravity Layout Mode'
            }
        );

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

    public dispose() {
        while (this._disposables.length) {
            const d = this._disposables.pop();
            if (d) d.dispose();
        }
    }
}
