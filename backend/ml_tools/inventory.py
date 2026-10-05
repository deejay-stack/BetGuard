"""Read-only inventory of possible datasets; configuration is not training data."""
import json
import os
from pathlib import Path

SKIP = {"node_modules", ".git", ".venv", "build", ".gradle", "__pycache__", "Pods", ".pytest_cache", "runs", "models"}
DATA_EXTENSIONS = {".csv", ".tsv", ".jsonl", ".parquet", ".xlsx", ".xls", ".arff"}
ARTIFACT_EXTENSIONS = {".skops", ".pkl", ".joblib", ".onnx"}


def inventory(root: Path, output: Path):
    candidates, artifacts, configuration = [], [], []
    for directory, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in SKIP and not name.endswith(".egg-info")]
        for name in sorted(files):
            path = Path(directory) / name
            if path.resolve() == output.resolve():
                continue
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() in DATA_EXTENSIONS:
                candidates.append(relative)
            elif path.suffix.lower() in ARTIFACT_EXTENSIONS:
                artifacts.append(relative)
            elif path.suffix.lower() == ".json" and path.stat().st_size <= 50_000_000:
                try:
                    value = json.loads(path.read_text(encoding="utf-8-sig"))
                    if isinstance(value, list) and any(isinstance(row, dict) and "hostname" in row for row in value):
                        candidates.append(relative)
                    else:
                        configuration.append(relative)
                except (ValueError, OSError):
                    configuration.append(relative)
    return {"root": root.name, "excluded_directories": sorted(SKIP),
            "dataset_candidates": sorted(candidates), "dataset_candidate_files": len(candidates),
            "model_artifacts": sorted(artifacts), "model_artifact_files": len(artifacts),
            "non_dataset_json_files": sorted(configuration), "non_dataset_json_count": len(configuration),
            "note": "A candidate filename is not evidence of licensing, review quality or usable supervised labels. Inspect each candidate with the audit command after mapping its schema."}
