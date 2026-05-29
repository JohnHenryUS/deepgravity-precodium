import * as vscode from 'vscode';
export declare class DoraChatPanel {
    private context;
    static readonly viewType = "deepgravity.doraChat";
    private _panel;
    private _disposables;
    constructor(context: vscode.ExtensionContext);
    show(): void;
    dispose(): void;
}
export declare class DoraChatViewProvider implements vscode.WebviewViewProvider {
    private readonly context;
    static readonly viewType = "deepgravity.doraChat";
    private _view?;
    constructor(context: vscode.ExtensionContext);
    resolveWebviewView(webviewView: vscode.WebviewView, context: vscode.WebviewViewResolveContext, token: vscode.CancellationToken): void;
}
//# sourceMappingURL=doraChat.d.ts.map