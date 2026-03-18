import json
from pathlib import Path

# Stub for notebook store
# Stores notebook cell history and outputs to context-inject future cell runs

STORE_DIR = Path("data/notebooks")
STORE_DIR.mkdir(parents=True, exist_ok=True)

class NotebookStore:
    @staticmethod
    def save_cell(session_id: str, cell_id: str, code: str, output: str, cell_type: str = "code"):
        pass

    @staticmethod
    def get_history(session_id: str):
        return []
