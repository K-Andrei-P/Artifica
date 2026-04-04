# security.py updates
import os
from pathlib import Path

class SecurityManager:
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir).resolve()

    def is_safe_path(self, target_path: str) -> bool:
        try:
            # Join with root_dir if it's a relative path
            target = Path(target_path)
            if not target.is_absolute():
                target = (self.root_dir / target).resolve()
            else:
                target = target.resolve()
            
            return self.root_dir in target.parents or target == self.root_dir
        except Exception:
            return False

    def check_command_safety(self, command: str) -> bool:
        forbidden_patterns = [
            ";", "&&", "||", 
            "$HOME", "~", "/etc", "/var", "/root",
            "sudo ", "chmod ", "chown "
        ]
        return not any(pattern in command for pattern in forbidden_patterns)

    def validate_action(self, command: str) -> (bool, str):
        if not self.check_command_safety(command):
            return False, "Security Error: Command contains forbidden patterns."
        return True, "Success"