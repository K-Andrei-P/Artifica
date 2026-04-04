import subprocess
import os
import requests
import warnings
from bs4 import BeautifulSoup
from ddgs import DDGS
from security import SecurityManager

# Silence the renaming warning from duckduckgo_search
warnings.filterwarnings("ignore", message=".*renamed to .ddgs.*")

def ask_permission(action_type: str, details: str) -> bool:
    """Centralized Human-in-the-loop check."""
    print(f"\n[AI REQUEST - {action_type.upper()}]:")
    print(f"Details: {details}")
    confirm = input("Confirm execution? (y/N): ").lower()
    return confirm == 'y'

def run_bash(command: str, root_dir: str):
    sec = SecurityManager(root_dir)
    is_safe, error_msg = sec.validate_action(command)
    if not is_safe:
        return f"Error: {error_msg}"

    cmd_clean = command.strip().lower()

    # 1. Define strictly read-only commands
    safe_prefixes = ("ls", "pwd", "whoami", "echo", "cat")
    
    # 2. Define "Danger Indicators" that force a confirmation 
    # even if the command starts with a safe prefix
    danger_indicators = ["|", ";", "&", ">", "rm", "mv", "cp", "chmod", "chown", "sudo", "touch"]

    # 3. Logic: Only skip confirmation if it starts with a safe command 
    # AND contains NO dangerous indicators/piping.
    skip_confirm = False
    if any(cmd_clean.startswith(safe) for safe in safe_prefixes):
        # If any danger indicator is found anywhere in the string, force confirmation
        if not any(danger in cmd_clean for danger in danger_indicators):
            skip_confirm = True

    if not skip_confirm:
        if not ask_permission("BASH", command):
            return "User denied execution."
    else:
        print(f"  > Executing (Auto-Approved): {command}")

    try:
        # Use a list for safer execution if possible, but keeping shell=True 
        # since you want to support pipes when the user approves them.
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=root_dir)
        
        # Combine stdout and stderr so the AI knows if the command failed
        output = (result.stdout + result.stderr).strip()
        return output if output else "Command executed successfully (no output)."
    except Exception as e:
        return f"System Error: {str(e)}"

def write_file(filename: str, content: str, root_dir: str):
    sec = SecurityManager(root_dir)
    if not sec.is_safe_path(filename):
        return "Error: Security violation."
    
    # ALWAYS ask before writing/overwriting files
    preview = content[:100] + "..." if len(content) > 100 else content
    if not ask_permission("WRITE FILE", f"File: {filename}\nContent Preview: {preview}"):
        return "User denied execution."

    try:
        path = os.path.join(root_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: File '{filename}' written."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def web_search(query: str):
    print(f"search: {query}")
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append(f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}\n")
        return "\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Search Error: {str(e)}"

def web_fetch(url: str):

    print(f"fetching from: {url}")
    try:
        # Use a session to ensure connection closure
        with requests.Session() as session:
            response = session.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text(separator=' ')
            return text[:10000]
    except Exception as e:
        return f"Fetch Error: {str(e)}"