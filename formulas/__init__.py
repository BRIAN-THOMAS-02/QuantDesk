"""Formula explainability layer.

Every number shown in the UI/CLI traces back to a FormulaDoc here.
The web UI's (i) icons call GET /api/formula/<id> which serves these docs
plus an optional LIVE worked example computed on real data.
"""
from formulas.registry import REGISTRY, CATEGORIES, get_doc, tree, list_ids
from formulas.examples import live_example

__all__ = ["REGISTRY", "CATEGORIES", "get_doc", "tree", "list_ids", "live_example"]
