"""Command-line entry point for the automation pipeline."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from pipeline.config import PipelineConfig, load_config, DEFAULT_CONFIG_PATH
from pipeline.state import PipelineState
from pipeline.stages import run_pipeline


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automate Word → Prompt → LLM → Excel pipeline")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH), help="Path to pipeline config JSON")
    parser.add_argument("--resume", action="store_true", help="Resume from previous artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls and Excel export")
    parser.add_argument("--preview", action="store_true", help="Generate preview markdown during parsing stage")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)

    if args.resume:
        config.flags.resume = True
    if args.dry_run:
        config.flags.dry_run = True
    if args.preview:
        config.flags.preview = True

    state = PipelineState(config.paths.artifacts_dir)
    asyncio.run(run_pipeline(config, state))


if __name__ == "__main__":
    main()
