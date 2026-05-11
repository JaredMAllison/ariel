import os
import sys
from pathlib import Path

# Resolve LMF stack from env or assume sibling repo layout (~/git/lmf/stack)
lmf_stack = os.environ.get("LMF_STACK_PATH", str(Path(__file__).parent.parent.parent / "lmf" / "stack"))
sys.path.insert(0, lmf_stack)
