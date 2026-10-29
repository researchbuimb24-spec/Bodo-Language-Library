"""Package main entry point for running python -m bhasha_lib.

💡 FILE INSIGHT & PURPOSE:
Enables direct package execution via `python -m bhasha_lib <args>`.
Forwards execution arguments directly to `bhasha_lib.cli.main()`.
"""

from __future__ import annotations

import sys

from bhasha_lib.cli import main

if __name__ == "__main__":
    sys.exit(main())
