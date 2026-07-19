import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class TaskState:
    original_request: str
    plan: Optional[str] = None
    progress: list = field(default_factory=list)
    subagent_results: dict = field(default_factory=dict)
    sources_consulted: list = field(default_factory=list)
    files_modified: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    iteration_count: int = 0
    loop_warnings: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def log_progress(self, step: str) -> None:
        self.progress.append(step)

    def record_subagent_result(self, name: str, result: dict) -> None:
        self.subagent_results[name] = result
        for src in result.get("sources", []):
            self.sources_consulted.append({"subagent": name, **src})

    def record_file_modified(self, path: str) -> None:
        if path not in self.files_modified:
            self.files_modified.append(path)

    def record_observation(self, text: str) -> None:
        self.observations.append(text)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
