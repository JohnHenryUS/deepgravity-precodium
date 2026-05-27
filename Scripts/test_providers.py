import os
import sys

# Ensure parent directory is in sys.path so we can import from src
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, parent_dir)

from src.orchestrator import DeepGravityOrchestrator

def main():
    print("==================================================")
    print("DeepGravity - Provider Configuration Test Utility")
    print("==================================================")

    config_path = os.path.join(parent_dir, "config.json")
    if not os.path.exists(config_path):
        config_path = os.path.join(parent_dir, "config.json.template")
        print(f"[*] Local config.json not found. Using template configuration.")
    else:
        print(f"[*] Found local config.json.")

    try:
        # Initialize orchestrator
        orchestrator = DeepGravityOrchestrator(config_path)
        orchestrator.initialize_session()
        print(f"[+] Orchestrator successfully initialized.")
        
        # Test prompt hydration
        print("\n[*] Testing system prompt hydration...")
        system_prompt = orchestrator.hydrate_system_prompt()
        prompt_len = len(system_prompt)
        print(f"[+] Loaded system prompt size: {prompt_len} characters.")
        
        # Test provider connection states
        print("\n[*] Scanning configured model providers:")
        for name, provider in orchestrator.providers.items():
            print(f"\n  Provider: {name}")
            print(f"  - Base URL: {provider.base_url}")
            print(f"  - Model: {provider.model_name}")
            print(f"  - Attempting connection...")
            
            # Simple connection ping
            try:
                # We send a minimal system check message to verify the pipe is live
                test_messages = [{"role": "user", "content": "ping"}]
                # We do not use tools for connection test
                response_text, _, _ = provider.generate_response(test_messages)
                safe_response = response_text.strip()[:60].encode('ascii', 'replace').decode('ascii')
                print(f"  [+] SUCCESS. Response received: {safe_response}...")
            except Exception as conn_err:
                print(f"  [-] CONNECTION FAILED: {conn_err}")
                print(f"      (Note: If this is local Ollama, ensure Ollama service is running on the target port).")

    except Exception as e:
        print(f"\n[-] ERROR: Failed to execute provider check: {e}")
        sys.exit(1)

    print("\n==================================================")
    print("[*] Scan complete.")
    print("==================================================")

if __name__ == "__main__":
    main()
