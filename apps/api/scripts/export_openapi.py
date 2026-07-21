from __future__ import annotations

import argparse
import json
from pathlib import Path

from dayboard.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the current FastAPI OpenAPI document.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
