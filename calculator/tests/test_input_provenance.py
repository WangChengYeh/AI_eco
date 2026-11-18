"""Changing data requires revisiting its evidence and classification."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_pipeline", ROOT / "run_pipeline.py")
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class DataProvenance(unittest.TestCase):
    def setUp(self):
        def read(name):
            return json.loads((ROOT / "configs" / name).read_text())
        self.config = read("current.json")
        self.registry = read("input_provenance.json")
        self.facts = read("reference_facts.json")

    def test_changed_milestone_without_evidence_revision_is_rejected(self):
        self.config["companies"]["tesla"]["segments"]["robotaxi"]["production_ramp"]["full_rate_month"] = 9
        with self.assertRaisesRegex(ValueError, "input/provenance mismatch"):
            p.validate_data(self.config, self.registry, self.facts)

    def test_capacity_lower_bound_is_not_relabelled_verified_production(self):
        self.registry["records"][0]["classification"] = "company_disclosed"
        with self.assertRaisesRegex(ValueError, "model assumption"):
            p.validate_data(self.config, self.registry, self.facts)

    def test_wrong_source_lower_bound_fails_even_if_input_mapping_matches(self):
        source = next(f for f in self.facts["facts"] if f["id"] == "tesla_cybercab_installed_capacity_2026q3")
        source["value"] = 250000
        with self.assertRaisesRegex(ValueError, "source lower bound"):
            p.validate_data(self.config, self.registry, self.facts)

    def test_required_deployment_evidence_cannot_be_omitted(self):
        self.registry["records"] = [r for r in self.registry["records"] if not r["input_path"].endswith("deployment_delay_months")]
        with self.assertRaisesRegex(ValueError, "complete provenance"):
            p.validate_data(self.config, self.registry, self.facts)


if __name__ == "__main__":
    unittest.main()
