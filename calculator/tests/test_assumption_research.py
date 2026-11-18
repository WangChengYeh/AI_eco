"""Research coverage is required without promoting targets to verified results."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("review_assumptions", ROOT / "review_assumptions.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class AssumptionResearch(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "configs/current.json").read_text())
        self.research = json.loads((ROOT / "configs/user_assumption_research.json").read_text())

    def test_new_user_assumption_requires_web_and_musk_search(self):
        self.config["metadata"]["user_assumptions"]["new_claim"] = 123
        with self.assertRaisesRegex(ValueError, "no web/Musk research"):
            m.validate_research(self.config, self.research)

    def test_changed_user_assumption_requires_new_evidence_review(self):
        self.config["metadata"]["user_assumptions"]["optimus_production_2027"] = 20000000
        with self.assertRaisesRegex(ValueError, "changed"):
            m.validate_research(self.config, self.research)

    def test_secondary_transcript_or_blocked_x_cannot_be_direct_support(self):
        row = next(r for r in self.research["claims"] if r["id"] == "optimus_rental")
        row["verdict"] = "direct_support"
        with self.assertRaisesRegex(ValueError, "readable primary evidence"):
            m.validate_research(self.config, self.research)

    def test_recording_search_queries_is_required(self):
        self.research["claims"][0]["search_queries"] = []
        with self.assertRaisesRegex(ValueError, "recorded web and Musk"):
            m.validate_research(self.config, self.research)

    def test_missing_or_broken_sources_are_rejected(self):
        self.research["claims"][0]["source_ids"] = ["invented_source"]
        with self.assertRaisesRegex(ValueError, "missing research sources"):
            m.validate_research(self.config, self.research)

    def test_user_input_must_link_to_researched_claim(self):
        registry = {"records": [{"classification": "user_assumption", "input_path": "example"}]}
        with self.assertRaisesRegex(ValueError, "requires a researched claim"):
            m.validate_research(self.config, self.research, registry)


if __name__ == "__main__":
    unittest.main()
