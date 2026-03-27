"""Tool execution layer for the system agent."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from config.models import get_config
from models import ollama_client

from .tools import app_launcher, browser, clipboard, filesystem, process, screen, shell


class ToolExecutor:
    """Route logical tool names to concrete implementations."""

    def __init__(self) -> None:
        self.tool_map = {
            "filesystem.search_files": filesystem.search_files,
            "filesystem.read_file": filesystem.read_file,
            "filesystem.write_file": filesystem.write_file,
            "filesystem.delete_file": filesystem.delete_file,
            "filesystem.move_file": filesystem.move_file,
            "filesystem.copy_file": filesystem.copy_file,
            "filesystem.list_directory": filesystem.list_directory,
            "filesystem.get_file_hash": filesystem.get_file_hash,
            "filesystem.create_directory": filesystem.create_directory,
            "shell.run_command": shell.run_command,
            "shell.run_python_file": shell.run_python_file,
            "shell.run_powershell_file": shell.run_powershell_file,
            "process.list_processes": process.list_processes,
            "process.kill_process": process.kill_process,
            "process.get_system_stats": process.get_system_stats,
            "clipboard.read_clipboard": clipboard.read_clipboard,
            "clipboard.write_clipboard": clipboard.write_clipboard,
            "screen.take_screenshot": screen.take_screenshot,
            "screen.screenshot_and_analyze": screen.screenshot_and_analyze,
            "browser.open_url": browser.open_url,
            "browser.capture_page": browser.capture_page,
            "app_launcher.launch_application": app_launcher.launch_application,
            "app_launcher.open_path": app_launcher.open_path,
            "ai.analyze_file": self._ai_analyze_file,
            "ai.summarize_files": self._ai_summarize_files,
            "ai.generate_code": self._ai_generate_code,
            "ai.explain_error": self._ai_explain_error,
        }

    async def execute(self, tool: str, args: dict[str, Any]) -> Any:
        """Execute a tool by name."""
        fn = self.tool_map.get(tool)
        if fn is None:
            raise ValueError(f"Unknown tool: {tool}")
        result = fn(**args)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _ai_analyze_file(self, path: str, question: str) -> dict:
        file_data = filesystem.read_file(path)
        role = "code" if Path(path).suffix.lower() in {".js", ".jsx", ".py", ".sql", ".ts", ".tsx"} else "chat"
        config = get_config(role)
        response = ""
        async for chunk in ollama_client.generate(
            model=config.model,
            prompt=(
                f"File: {path}\n\n"
                f"```text\n{file_data['content']}\n```\n\n"
                f"Question: {question}"
            ),
            system=config.system_prompt,
            stream=True,
            temperature=config.temperature,
        ):
            response += chunk
        return {"analysis": response, "file": path}

    async def _ai_summarize_files(self, paths: list[str], style: str = "brief") -> dict:
        summaries: list[dict[str, Any]] = []
        config = get_config("code")
        for path in paths[:20]:
            try:
                data = filesystem.read_file(path, max_chars=10_000)
            except Exception as exc:
                summaries.append({"path": path, "error": str(exc)})
                continue
            prompt = (
                f"Summarize this file in a {style} style.\n\n"
                f"Path: {path}\n\n```text\n{data['content'][:8000]}\n```"
            )
            response = ""
            async for chunk in ollama_client.generate(
                model=config.model,
                prompt=prompt,
                system=config.system_prompt,
                stream=True,
                temperature=0.3,
            ):
                response += chunk
            summaries.append({"path": path, "summary": response})
        return {"summaries": summaries}

    async def _ai_generate_code(self, description: str, context: Any = None) -> dict:
        config = get_config("code")
        context_text = await self._build_context_text(context)
        response = ""
        async for chunk in ollama_client.generate(
            model=config.model,
            prompt=f"Task:\n{description}\n\nContext:\n{context_text}",
            system=config.system_prompt,
            stream=True,
            temperature=config.temperature,
        ):
            response += chunk
        return {"code": response}

    async def _ai_explain_error(self, error_text: str, context: Any = None) -> dict:
        config = get_config("code")
        context_text = await self._build_context_text(context)
        response = ""
        async for chunk in ollama_client.generate(
            model=config.model,
            prompt=f"Explain this error and propose a fix.\n\nError:\n{error_text}\n\nContext:\n{context_text}",
            system=config.system_prompt,
            stream=True,
            temperature=0.2,
        ):
            response += chunk
        return {"explanation": response}

    async def _build_context_text(self, context: Any) -> str:
        if context is None:
            return "(none)"
        if isinstance(context, str):
            potential_path = Path(context)
            if potential_path.exists():
                try:
                    return filesystem.read_file(str(potential_path), max_chars=12_000)["content"]
                except Exception:
                    return context
            return context
        if isinstance(context, list):
            blocks: list[str] = []
            for item in context[:5]:
                if isinstance(item, str) and Path(item).exists():
                    try:
                        data = filesystem.read_file(item, max_chars=6_000)
                        blocks.append(f"Path: {item}\n{data['content']}")
                    except Exception as exc:
                        blocks.append(f"Path: {item}\nError: {exc}")
                else:
                    blocks.append(str(item))
            return "\n\n".join(blocks)
        return str(context)
