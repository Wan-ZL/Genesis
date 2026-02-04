"""CLI entry point for AI Assistant.

Usage:
    python -m assistant.cli export --output conversation.json
    python -m assistant.cli import --input conversation.json
    python -m assistant.cli import --input conversation.json --mode replace
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from assistant.server.services.memory import MemoryService
import assistant.config as config


async def export_command(args):
    """Export conversation to JSON file."""
    memory = MemoryService(config.DATABASE_PATH)

    export_data = await memory.export_conversation()

    # Write to file or stdout
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(export_data, indent=2))
        print(f"Exported {export_data['message_count']} messages to {output_path}")
    else:
        print(json.dumps(export_data, indent=2))


async def import_command(args):
    """Import conversation from JSON file."""
    memory = MemoryService(config.DATABASE_PATH)

    # Read input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(input_path.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Perform import
    try:
        result = await memory.import_conversation(data, mode=args.mode)
        print(f"Import complete:")
        print(f"  - Imported: {result['imported_count']} messages")
        print(f"  - Skipped: {result['skipped_count']} messages")
        print(f"  - Mode: {result['mode']}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="assistant.cli",
        description="AI Assistant CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export conversation to JSON")
    export_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)"
    )

    # Import command
    import_parser = subparsers.add_parser("import", help="Import conversation from JSON")
    import_parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input file path"
    )
    import_parser.add_argument(
        "--mode", "-m",
        choices=["merge", "replace"],
        default="merge",
        help="Import mode: merge (skip duplicates) or replace (clear existing)"
    )

    args = parser.parse_args()

    if args.command == "export":
        asyncio.run(export_command(args))
    elif args.command == "import":
        asyncio.run(import_command(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
