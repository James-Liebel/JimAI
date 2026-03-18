import json
from pathlib import Path

def create_notebook(path: str, cells: list[dict]):
    nb = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f)

def read_notebook(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    return nb.get("cells", [])

def execute_cell(code: str) -> dict:
    return {"status": "success", "outputs": []}

def add_cell(path: str, code: str, cell_type: str = 'code'):
    if not Path(path).exists():
        create_notebook(path, [])
    cells = read_notebook(path)
    cells.append({"cell_type": cell_type, "source": [code]})
    create_notebook(path, cells)

def export_to_script(notebook_path: str) -> str:
    cells = read_notebook(notebook_path)
    code = [ "".join(c["source"]) for c in cells if c["cell_type"] == "code" ]
    script_path = str(notebook_path).replace(".ipynb", ".py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(code))
    return script_path
