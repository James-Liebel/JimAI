"""Agent Space autonomy primitives.

This package adds the four building blocks the 2026 research consensus calls
"the cheapest path to a feel-autonomous agent":

    1. episodic memory - persistent (run, event, outcome) records with similarity search
    2. skill library  - verifier-gated capture of winning code patterns
    3. reflection     - Reflexion-style verbal critique appended on retry
    4. replan         - mid-run goal re-evaluation after each subagent finishes
    5. heartbeat      - tick-driven scheduler that lets agents act on their own

Each primitive is independently usable; the orchestrator wires them together.
"""

from .episodic_memory import EpisodicMemory, EpisodeRecord
from .skill_library import SkillLibrary, SkillEntry
from .reflection import ReflectionEngine, ReflectionTrace
from .replan import ReplanEngine, ReplanDecision
from .heartbeat import HeartbeatScheduler, HeartbeatJob

__all__ = [
    "EpisodicMemory",
    "EpisodeRecord",
    "SkillLibrary",
    "SkillEntry",
    "ReflectionEngine",
    "ReflectionTrace",
    "ReplanEngine",
    "ReplanDecision",
    "HeartbeatScheduler",
    "HeartbeatJob",
]
