#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Current product documentation, taxonomy, safety and routing contracts.

Historical report prose remains in test-reviewer-doc-contracts.py and runs only
through ci-evidence.sh. Importing that module performs no evidence reads.
"""
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("doc_contracts", ROOT / "scripts/ci/test-reviewer-doc-contracts.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.verify_current_docs()
print("current documentation contracts: pass")
