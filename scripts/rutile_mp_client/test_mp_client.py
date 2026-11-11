import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mp_client import (MPClient, MPAuthError, MPNetworkError, composition_key,
                       safe_search, to_props)

class MockRester:
    version = '2026.11.01'
    calls = 0
    def __init__(self, key):
        self.current_db_version = self.version
        self.materials = self
        self.summary = self
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def search(self, **kw):
        type(self).calls += 1
        if kw.get('material_ids'):
            return [{'material_id': 'mp-1374', 'formula_pretty':'Zr5Re24', 'density':17.6}]
        return [
            {'material_id':'mp-1', 'formula_pretty':'ZrRe2', 'symmetry':{'number':194,'symbol':'P6_3/mmc'}, 'density':14.71,
             'bulk_modulus':{'vrh':252.9},'shear_modulus':{'vrh':75}},
            {'material_id':'mp-2', 'formula_pretty':'Zr2Re','symmetry':{'number':194}},
        ]

class Tests(unittest.TestCase):
    def setUp(self):
        MockRester.calls = 0
        MockRester.version = '2026.11.01'
        self.tmp = tempfile.TemporaryDirectory()
        self.client = MPClient('fake-key', cache_dir=self.tmp.name, rester_factory=MockRester,
                               backoff_seconds=0)
    def tearDown(self): self.tmp.cleanup()
    def test_formula_reduction_and_order(self):
        self.assertEqual(composition_key('Re24Zr5'), composition_key('Zr5Re24'))
        self.assertEqual(composition_key('Re2Zr'), composition_key('ZrRe2'))
        self.assertNotEqual(composition_key('Re2Zr'), composition_key('Zr2Re'))
        self.assertEqual(composition_key('Al4Cu2'), composition_key('Al2Cu'))
    def test_filtered(self):
        r = self.client.find_formula('Re2Zr', spacegroup=194)
        self.assertEqual(r.search_status, 'complete')
        self.assertEqual([x['mp_id'] for x in r.records], ['mp-1'])
        self.assertAlmostEqual(r.records[0]['youngs_modulus_vrh_derived_GPa'],204.68, places=0)
    def test_cache_version(self):
        self.client.find_formula('Re2Zr')
        self.assertEqual(MockRester.calls,1)
        r = self.client.find_formula('Re2Zr')
        self.assertTrue(r.from_cache)
        self.assertEqual(MockRester.calls,1)
        MockRester.version = '2026.12.01'
        r2 = self.client.find_formula('Re2Zr')
        self.assertFalse(r2.from_cache)
        self.assertEqual(MockRester.calls,2)
    def test_no_match(self):
        self.assertEqual(self.client.find_formula('Re20Zr9').search_status,'no_match')
    def test_failure_not_no_match(self):
        class Bad(MockRester):
            def search(self, **kwargs):
                raise ConnectionError('network offline')
        c = MPClient('test',retries=2,backoff_seconds=0,cache_dir=self.tmp.name,rester_factory=Bad)
        with patch('mp_client.time.sleep') as sleep:
            r = safe_search(c.get_ids,['mp-1'])
            self.assertEqual(sleep.call_count, 2)
        self.assertEqual(r['search_status'],'network_error')
    def test_null_safe(self):
        r = to_props({'material_id':'mp-5','formula_pretty':'Al2Cu'})
        self.assertIsNone(r['hardness'])
        self.assertIsNone(r['bulk_modulus_vrh_GPa'])

if __name__ == '__main__': unittest.main()
