"""统一管理路径。Skill 可能被装在任何目录、从任何工作目录调用，所以不依赖当前目录。"""

from __future__ import annotations

import os
from pathlib import Path

# Skill 根目录（即仓库根目录，SKILL.md 所在位置）
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
PERSONA_FILE = ASSETS_DIR / "personas.json"
DEMO_FILE = ASSETS_DIR / "demo.json"

# 用户数据目录：缓存、输出、可选的 .env，都放在这里而不是 Skill 目录或当前目录
DATA_HOME = Path(os.environ.get("MCD_PERSONA_HOME", "~/.mcd-persona-card")).expanduser()
CACHE_FILE = DATA_HOME / "cache" / "raw.json"
INPUT_FILE = DATA_HOME / "input.json"
OUT_DIR = DATA_HOME / "out"

# 按顺序查找 .env：当前目录 → 用户数据目录 → Skill 目录
ENV_FILES = (Path.cwd() / ".env", DATA_HOME / ".env", SKILL_DIR / ".env")
