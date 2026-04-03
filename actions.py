import subprocess
from security import SecurityManager

def run_bash(command: str, root_dir: str):
    sec = SecurityManager(root_dir)
    
    # 1. Security Check
    is_safe, error_msg = sec.validate_action(command)
    if not is_safe:
        return f"Error: {error_msg}"

    # 2. Human-in-the-loop 
    cmd_clean = command.strip().lower()
    # Skip confirmation for 'ls' or 'echo'
    skip_confirm = cmd_clean.startswith("ls") or cmd_clean.startswith("echo")

    if not skip_confirm:
        print(f"\n[AI REQUEST]: {command}")
        confirm = input("Confirm execution? (y/N): ").lower()
        if confirm != 'y':
            return "User denied execution."
    else:
        # Just show what's happening silently
        print(f"  > Executing: {command}")

    # 3. Execution
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=root_dir 
        )
        
        output = result.stdout if result.stdout else result.stderr
        if not output and result.returncode == 0:
            return "Success (No output)"
        return output
        
    except Exception as e:
        return f"System Error: {str(e)}"

def web_search(query: str):
    return ""