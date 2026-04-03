import os
from pathlib import Path

class SecurityManager:
    def __init__(self, root_dir: str):
        # Resolve the absolute path of your current directory
        self.root_dir = Path(root_dir).resolve()

    def is_safe_path(self, target_path: str) -> bool:
        """
        Check if the target path is inside the allowed root directory.
        Prevents ../../etc/passwd style attacks.
        """
        try:
            # Resolve the path the AI wants to touch
            target = Path(target_path).resolve()
            # Check if the root_dir is a parent of the target path
            return self.root_dir in target.parents or target == self.root_dir
        except Exception:
            return False

    def check_command_safety(self, command: str) -> bool:
        """
        Scans the command for obvious 'jailbreak' attempts.
        """
        # Block attempts to use environment variables or home shortcuts
        forbidden_patterns = [
            ";", "&&", "||",  # Block command chaining (optional, if you want strictness)
            "$HOME", "~", "/etc", "/var", "/root",
            "sudo ", "chmod ", "chown "
        ]
        
        # Check for forbidden strings
        if any(pattern in command for pattern in forbidden_patterns):
            return False
            
        return True

    def validate_action(self, command: str) -> (bool, str):
        """
        The main gatekeeper function.
        """
        if not self.check_command_safety(command):
            return False, "Security Error: Command contains forbidden patterns or system paths."
        
        # Note: Validating paths inside a complex bash string is hard. 
        # The best 'jail' is setting the `cwd` in subprocess.run, 
        # which we do in actions.py.
        
        return True, "Success"