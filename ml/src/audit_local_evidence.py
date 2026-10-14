"""Read-only repository/dataset inventory; never train, download or edit inputs.

Run from any directory with --output pointing to a new evidence directory.
Installed dependencies, secrets, Git internals and generated native builds are
listed as retained boundaries rather than traversed as application source.
"""
import argparse
import ast
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OPAQUE = {".git", ".venv", "node_modules", ".gradle", ".kotlin", ".cxx", "Pods", "build", "dist", "verification", ".local"}
SECRET_SUFFIXES = {".key", ".pem", ".crt", ".cer", ".keystore"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect():
    files, boundaries, errors, datasets, modules = [], [], [], [], []
    def onerror(error):
        errors.append({"path": str(Path(error.filename).relative_to(ROOT)), "error": type(error).__name__})
    for directory, dirs, names in os.walk(ROOT, onerror=onerror, followlinks=False):
        parent = Path(directory)
        for name in list(dirs):
            path = parent / name
            if name in OPAQUE or name.endswith(".egg-info") or path.is_symlink():
                boundaries.append({"path": path.relative_to(ROOT).as_posix(), "action": "KEEP", "reason": "installed/generated/private boundary; no deletion"})
                dirs.remove(name)
        for name in sorted(names):
            path = parent / name
            rel = path.relative_to(ROOT).as_posix()
            try:
                generated = "__pycache__" in path.parts or ".pytest_cache" in path.parts or path.suffix in {".pyc", ".pyo"}
                secret = name.startswith(".env") and name != ".env.example" or path.suffix in SECRET_SUFFIXES
                uncertain = path.suffix == ".backup" or name == "train_baseline_current.txt"
                row = {"path": rel, "bytes": path.stat().st_size, "category": "D" if generated else "C" if uncertain else "B" if rel.startswith("ml/") else "A", "action": "REMOVE_CACHE" if generated else "REVIEW_KEEP" if uncertain else "KEEP"}
                if generated:
                    row["reason"] = "reproducible Python/pytest cache; verify exact path before deletion"
                elif uncertain:
                    row["reason"] = "backup/log may preserve user work; retained pending manual review"
                elif secret:
                    row["reason"] = "private configuration/key retained; content not read or hashed"
                else:
                    row["sha256"] = sha256(path)
                    row["reason"] = "runtime/source/evidence retained"
                files.append(row)
                if path.suffix == ".py" and not generated:
                    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                    imports = sorted({n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names})
                    modules.append({"path": rel, "imports": imports, "definitions": [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]})
                if path.suffix == ".csv" and rel.startswith("ml/"):
                    with path.open(encoding="utf-8-sig", newline="") as stream:
                        reader = csv.DictReader(stream)
                        columns = reader.fieldnames or []
                        counts = {key: Counter() for key in columns if key in {"label", "verified_label", "final_verified_label", "proposed_label", "candidate_label", "suggested_label", "final_label", "review_decision", "review_status", "human_label", "verification_status", "source", "sources"}}
                        domains, families, total = set(), set(), 0
                        duplicate_domains = 0
                        for record in reader:
                            total += 1
                            for key, counter in counts.items():
                                counter[record.get(key, "")] += 1
                            host = record.get("domain", "").strip().lower()
                            if host:
                                duplicate_domains += host in domains
                                domains.add(host)
                            family = record.get("domain_family", "").strip().lower()
                            if family:
                                families.add(family)
                    datasets.append({"path": rel, "sha256": row["sha256"], "rows": total, "columns": columns, "distributions": {k: dict(v) for k, v in counts.items()}, "unique_domains": len(domains), "duplicate_domain_rows": duplicate_domains, "unique_saved_families": len(families)})
            except (OSError, ValueError, SyntaxError) as error:
                errors.append({"path": rel, "error": type(error).__name__})
    return {"files": files, "retained_boundaries": boundaries, "scan_errors": errors, "datasets": datasets, "python_modules": modules}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Use a new output directory; previous evidence is preserved.")
    result = collect()
    result["git"] = {name: subprocess.run(["git", "-C", str(ROOT), *command], capture_output=True, text=True, check=False).stdout for name, command in {"branch": ["branch", "--show-current"], "head": ["rev-parse", "HEAD"], "status": ["status", "--short"]}.items()}
    output.mkdir(parents=True)
    (output / "local_inventory.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "cleanup_inventory.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "bytes", "category", "action", "reason", "sha256"])
        writer.writeheader()
        writer.writerows(result["files"])
    print(json.dumps({"files": len(result["files"]), "datasets": len(result["datasets"]), "modules": len(result["python_modules"]), "cache_files": sum(f["category"] == "D" for f in result["files"]), "review_keep": [f["path"] for f in result["files"] if f["category"] == "C"], "scan_errors": result["scan_errors"]}, indent=2))


if __name__ == "__main__":
    main()
