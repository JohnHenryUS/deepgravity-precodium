import * as vscode from 'vscode';
export type LayoutMode = 'ide' | 'cce' | 'doc';
export declare class ModeSwitcher implements vscode.Disposable {
    private statusBarItem;
    private _currentMode;
    private _disposables;
    constructor(statusBarItem: vscode.StatusBarItem);
    get currentMode(): LayoutMode;
    setMode(mode: LayoutMode): void;
    showModePicker(): Promise<void>;
    dispose(): void;
}
//# sourceMappingURL=modeSwitcher.d.ts.map