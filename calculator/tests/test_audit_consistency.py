"""Regression coverage for cross-stage financial and publication failures."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

CALC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CALC))
import audit_model
import build_site
from forecast import forecast
from run_pipeline import validate_data


class AuditConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((CALC/'configs/current.json').read_text())
        cls.research = json.loads((CALC/'configs/user_assumption_research.json').read_text())
        cls.result = forecast(cls.config)

    def test_primary_financial_and_asset_reconciliations(self):
        self.assertGreater(audit_model.reconcile(self.result), 400)

    def test_corrupted_net_income_fails_reconciliation(self):
        result = copy.deepcopy(self.result)
        result['companies']['tesla'][0]['net_income_usd'] += 1e6
        with self.assertRaisesRegex(ValueError, 'net profit'):
            audit_model.reconcile(result)

    def test_leap_year_billing_uses_actual_calendar(self):
        rows = [r for r in self.result['segments'] if 'calendar_hours' in r['drivers']]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row['drivers']['calendar_hours'], 8784 if row['year'] == 2028 else 8760)

    def test_html_matches_python_and_rejects_different_results(self):
        document = build_site.render_document(self.config, self.research, self.result)
        self.assertTrue(audit_model.validate_html(document, self.result))
        altered = copy.deepcopy(self.result)
        altered['companies']['tesla'][0]['net_income_usd'] += 1
        with self.assertRaisesRegex(ValueError, 'company results differ'):
            audit_model.validate_html(document, altered)
        for element in ('ts-opening-anchors','ts-orbit-flights','ts-orbit-capacity','ts-fsd-annual'):
            self.assertIn(element, document)

    def test_opening_balance_source_components_must_reconcile(self):
        registry = json.loads((CALC/'configs/input_provenance.json').read_text())
        facts = json.loads((CALC/'configs/reference_facts.json').read_text())
        next(f for f in facts['facts'] if f['id']=='tesla_cash_anchor_2026')['components'][0] += 1
        with self.assertRaisesRegex(ValueError, 'components do not reconcile'):
            validate_data(self.config, registry, facts)

    def test_user_metadata_cannot_drift_from_calculation(self):
        config = copy.deepcopy(self.config)
        registry = json.loads((CALC/'configs/input_provenance.json').read_text())
        facts = json.loads((CALC/'configs/reference_facts.json').read_text())
        binding = registry['user_bindings'][0]
        config['metadata']['user_assumptions'][binding['user_key']] += 1
        with self.assertRaisesRegex(ValueError, 'user instruction/forecast driver mismatch'):
            validate_data(config, registry, facts)

    def test_displayed_assumptions_follow_drivers(self):
        config = copy.deepcopy(self.config)
        network = config['companies']['spacex']['segments']['orbital_compute']['launch_network']
        network['capacity_upgrade']['net_it_mw_per_flight'] = 17
        text = str(build_site.assumptions(config))
        self.assertIn('淨17MW', text)
        self.assertNotIn('淨15MW', text)

    def test_clean_build_is_repeatable_without_prior_html(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'calculator').mkdir()
            shutil.copytree(CALC/'configs', root/'calculator/configs')
            for template in ('site_template.html','site_shell.html'):
                shutil.copy(CALC/template, root/'calculator'/template)
            (root/'docs').mkdir()
            (root/'research').mkdir()
            with patch.object(build_site, 'ROOT', root):
                build_site.build()
                first = (root/'index.html').read_bytes()
                (root/'index.html').write_text('corrupted old output')
                (root/'docs/index.html').unlink()
                build_site.build()
                self.assertEqual(first, (root/'index.html').read_bytes())
                self.assertEqual(first, (root/'docs/index.html').read_bytes())


if __name__ == '__main__':
    unittest.main()
