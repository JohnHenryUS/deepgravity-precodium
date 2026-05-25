import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.orchestrator import DeepGravityOrchestrator

def main():
    console = Console()
    console.print(Panel.fit(
        "[bold cyan]DeepGravity: Sovereign Agent Interface[/bold cyan]\n"
        "[dim]Initializing local/cloud federated API router...[/dim]",
        border_style="cyan"
    ))

    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json"))
    if not os.path.exists(config_path):
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json.template"))

    try:
        # Initialize orchestrator
        orchestrator = DeepGravityOrchestrator(config_path)
        orchestrator.initialize_session()
        
        # Resolve model roles for display
        attunement = orchestrator.config.get("api", {}).get("routing", {}).get("attunement_core", "None")
        coder = orchestrator.config.get("api", {}).get("routing", {}).get("primary_orchestrator", "None")
        
        console.print(f"[green][+][/green] Sessions initialized.")
        console.print(f"    - Attunement Core model: [yellow]{attunement}[/yellow]")
        console.print(f"    - Primary Coder model:     [yellow]{coder}[/yellow]")
        console.print(f"    - System prompt size:     [green]{len(orchestrator.system_prompt)}[/green] characters.")
        console.print("\n[bold green]Ready. Press Ctrl+C to exit.[/bold green]\n")

        while True:
            # Get user input
            try:
                user_input = Prompt.ask("\n[bold white]JH[/bold white]")
                if not user_input.strip():
                    continue
                
                # Check for special terminal controls
                if user_input.strip().lower() in {"exit", "quit"}:
                    console.print("\n[dim]DeepGravity shut down.[/dim]")
                    break

                console.print("\n[bold cyan]Dora[/bold cyan]")
                
                # Run the streaming agent loop
                stream = orchestrator.run_agent_loop_stream(user_input)
                
                sys.stdout.write("\033[96m") # Set terminal color to cyan
                sys.stdout.flush()
                
                for chunk in stream:
                    if chunk["type"] == "content":
                        sys.stdout.write(chunk["content"])
                        sys.stdout.flush()
                    elif chunk["type"] == "tool_start":
                        sys.stdout.write("\033[0m") # Reset color
                        console.print(f"\n[yellow]⚙ Running tool: {chunk['name']}...[/yellow]")
                        sys.stdout.write("\033[96m") # Restore cyan
                        sys.stdout.flush()
                    elif chunk["type"] == "tool_end":
                        sys.stdout.write("\033[0m") # Reset color
                        console.print(f"[green]✔ Tool {chunk['name']} completed.[/green]")
                        sys.stdout.write("\033[96m") # Restore cyan
                        sys.stdout.flush()
                
                sys.stdout.write("\033[0m\n") # Reset color and add newline
                sys.stdout.flush()
                
            except KeyboardInterrupt:
                console.print("\n\n[yellow][*] Interrupt received. Exiting DeepGravity.[/yellow]")
                break
            except Exception as loop_err:
                console.print(f"\n[bold red][!] Error in execution loop: {loop_err}[/bold red]")

    except Exception as e:
        console.print(f"\n[bold red][!] Critical Initialization Failure: {e}[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
