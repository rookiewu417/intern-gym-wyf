from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import REQUIRED_COMPLETE_DATASETS, MockConfig


@dataclass(frozen=True)
class RecordingCatalog:
    root: Path
    run_id: str
    run_path: Path
    datasets: frozenset[str]

    @classmethod
    def discover(cls, config: MockConfig) -> "RecordingCatalog":
        root = config.recording_root
        if not root.exists():
            raise FileNotFoundError(f"recording root does not exist: {root}")

        if config.run_id:
            run_path = root / f"run_id={config.run_id}"
            if not run_path.exists():
                raise FileNotFoundError(f"recording run does not exist: {run_path}")
            return cls(root=root, run_id=config.run_id, run_path=run_path, datasets=_datasets(run_path))

        candidates = sorted((p for p in root.glob("run_id=*") if p.is_dir()), reverse=True)
        complete = [p for p in candidates if REQUIRED_COMPLETE_DATASETS.issubset(_datasets(p))]
        if complete:
            run_path = complete[0]
        elif candidates:
            run_path = candidates[0]
        else:
            raise FileNotFoundError(f"no recording runs found under {root}")

        return cls(
            root=root,
            run_id=run_path.name.removeprefix("run_id="),
            run_path=run_path,
            datasets=_datasets(run_path),
        )

    def dataset_path(self, dataset: str) -> Path:
        path = self.run_path / f"dataset={dataset}"
        if not path.exists():
            raise FileNotFoundError(f"dataset not found in run {self.run_id}: {dataset}")
        return path


def _datasets(run_path: Path) -> frozenset[str]:
    return frozenset(p.name.removeprefix("dataset=") for p in run_path.glob("dataset=*") if p.is_dir())

