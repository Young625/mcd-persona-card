"""Skill 入口：python3 <Skill 目录>/scripts/run.py {card,match,check}"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcd_persona.cli import main  # noqa: E402

sys.exit(main())
