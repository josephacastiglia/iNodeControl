"""The per-format matrix must stay complete, conservative and evidence-linked."""
from pathlib import Path
import re
import unittest

from farm_capabilities import capabilities
from farm_format_coverage import LEVELS, coverage
from imouse_social_automation import UploadFormat

ROOT = Path(__file__).resolve().parents[1]


class FormatCoverageTests(unittest.TestCase):
    def test_every_upload_format_appears_once_in_enum_order(self):
        self.assertEqual([m.value for m in UploadFormat], [row['id'] for row in coverage()])
        self.assertEqual(14, len(coverage()))

    def test_levels_are_conservative(self):
        for row in coverage():
            with self.subTest(format=row['id']):
                self.assertIn(row['level'], LEVELS)
                self.assertFalse(row['publishingEnabled'])
                if row['draftMechanism'] != 'observed':
                    # No verified draft: never claim more than simulation, never a live route.
                    self.assertIn(row['level'], ('unsupported_draft', 'simulation_only'))
                    self.assertEqual('none', row['liveRoute'])
                if row['level'] in ('supervised_phone', 'integrated_offline', 'integrated_live'):
                    self.assertTrue(row['supervised'])
                if row['level'] in ('integrated_offline', 'integrated_live'):
                    self.assertTrue(row['offline'])
                    self.assertEqual('explicit_isolated_candidate', row['liveRoute'])
                self.assertEqual(row['level'] == 'integrated_live', bool(row['live']))
        self.assertEqual(['ig_carousel'], [r['id'] for r in coverage() if r['level'] == 'integrated_live'])

    def test_story_thread_community_and_long_video_stay_unsupported(self):
        rows = {r['id']: r for r in coverage()}
        for name in ('ig_story', 'tt_story', 'tt_text', 'x_thread', 'yt_video', 'yt_community_post'):
            self.assertEqual('unsupported_draft', rows[name]['level'], name)

    def test_cited_records_exist_in_this_checkout(self):
        for row in coverage():
            for field in ('supervised', 'offline', 'live', 'simulation'):
                for path in re.findall(r'((?:analysis|tools)/[\w./-]+?\.(?:md|py))', row[field] or ''):
                    with self.subTest(format=row['id'], path=path):
                        self.assertTrue((ROOT/path).is_file(), path)

    def test_capabilities_report_includes_the_matrix_without_enabling_automation(self):
        report = capabilities()
        self.assertEqual(coverage(), report['formats'])
        self.assertFalse(report['liveAutomationReady']); self.assertFalse(report['allMarketingFeaturesAccepted'])


if __name__ == '__main__':
    unittest.main()
