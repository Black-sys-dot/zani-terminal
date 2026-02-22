import os
import yaml

class SafetyShield:
    def __init__(self):
        # Dynamically find the config file relative to this file's location
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = os.path.join(base_path, "config", "settings.yaml")
        self.config = self._load_config()
        self.static_ignore = set(self.config.get('safety', {}).get('static_ignore', []))
        self.max_size_kb = self.config.get('safety', {}).get('max_file_size_kb', 500)

    def _load_config(self):
        if not os.path.exists(self.config_path):
            return {"safety": {"static_ignore": [".git", "venv", ".venv", "node_modules"], "max_file_size_kb": 500}}
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def is_human_readable(self, file_path):
        try:
            file_size_kb = os.path.getsize(file_path) / 1024
            if file_size_kb > self.max_size_kb:
                return False
        except OSError:
            return False

        machine_extensions = {'.pyc', '.exe', '.dll', '.so', '.o', '.bin', '.png', '.jpg', '.pdf', '.zip'}
        if os.path.splitext(file_path)[1].lower() in machine_extensions:
            return False

        filename = os.path.basename(file_path)
        # Allow .zani internal files but ignore other hidden clutter
        if filename.startswith('.') and filename not in ['.env', '.gitignore', '.zani']:
            return False

        return True

    def scan_workspace(self, root_path):
        human_files = []
        for root, dirs, files in os.walk(root_path):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in self.static_ignore]

            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_path)
                
                if self.is_human_readable(full_path):
                    human_files.append(rel_path)
        
        return human_files