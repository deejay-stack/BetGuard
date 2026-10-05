"""python -m ml_tools.cli: all training/evaluation commands are explicit."""
import argparse
import json
from pathlib import Path

from ml_tools.data import Observation, audit, json_write
from ml_tools.protocol import TrainingConfig
from ml_tools.inventory import inventory
from ml_tools.workflow import create_split, evaluate, export, train


def main():
    parser = argparse.ArgumentParser(description="BetGuard hostname ML development; no production dataset is bundled.")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("inventory")
    listing.add_argument("root", type=Path)
    listing.add_argument("--output", type=Path, required=True)
    schema = commands.add_parser("schema")
    schema.add_argument("output", type=Path)
    audit_cmd = commands.add_parser("audit")
    audit_cmd.add_argument("dataset", type=Path)
    audit_cmd.add_argument("--output", type=Path, required=True)
    split = commands.add_parser("split")
    split.add_argument("dataset", type=Path)
    split.add_argument("--output", type=Path, required=True)
    split.add_argument("--config", type=Path)
    training = commands.add_parser("train")
    training.add_argument("dataset", type=Path)
    training.add_argument("--split", type=Path, required=True)
    training.add_argument("--run", type=Path, required=True)
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("dataset", type=Path)
    evaluation.add_argument("--run", type=Path, required=True)
    exporting = commands.add_parser("export")
    exporting.add_argument("--run", type=Path, required=True)
    exporting.add_argument("--output", type=Path, required=True)
    exporting.add_argument("--reviewed-by", required=True)
    exporting.add_argument("--review-note", required=True)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            report = inventory(args.root.resolve(), args.output)
            json_write(args.output, report)
            print(json.dumps(report))
        elif args.command == "schema":
            json_write(args.output, Observation.model_json_schema())
        elif args.command == "audit":
            report, _, _ = audit(args.dataset)
            json_write(args.output, report)
            print(json.dumps({key: report[key] for key in ("rows", "valid_rows", "invalid_rows", "supervised_unique_rows", "status")}))
        elif args.command == "split":
            config = TrainingConfig(**json.loads(args.config.read_text(encoding="utf-8"))) if args.config else TrainingConfig()
            create_split(args.dataset, args.output, config)
            print("Recorded fixed train/validation/test membership. No models trained.")
        elif args.command == "train":
            result = train(args.dataset, args.split, args.run)
            print(json.dumps({"selected_on_validation": result["selected"], "test_evaluated": False}))
        elif args.command == "evaluate":
            evaluate(args.dataset, args.run)
            print("Recorded held-out comparison for all three models. Selection remains fixed.")
        else:
            print(json.dumps(export(args.run, args.output, reviewer=args.reviewed_by, note=args.review_note)))
    except (OSError, ValueError, TypeError, KeyError) as error:
        # No row contents or credentials in CLI output. Detailed private reports
        # contain record indexes/hostnames, never submitted URL paths.
        parser.exit(1, f"ML command could not complete ({type(error).__name__}). Check the audit, inputs and workflow prerequisites.\n")


if __name__ == "__main__":
    main()
