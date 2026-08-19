"""Fixture: this module has an import-time side effect and MUST never be executed.

eo-workflow-lint parses source statically; if analysis ever imported or executed
the target, the marker file below would appear.
"""

import pathlib

pathlib.Path(__file__).with_name("SIDE_EFFECT_MARKER").write_text("executed")

raise SystemExit("eo-workflow-lint executed the analyzed source")
