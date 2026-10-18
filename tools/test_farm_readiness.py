"""Acceptance for schedule boundaries and evidence-based analytics, offline only."""
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch

import imouse_social_automation as engine
import imouse_farm_server as server


class FarmReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='farm-readiness-')
        self.addCleanup(self.temp.cleanup)
        self.runtime = server.FarmBackendRuntime(Path(self.temp.name) / 'farm.db', Path(self.temp.name) / 'stage')
        self.db = self.runtime.db
        self.guard = engine.ShadowbanGuardAndDiagnostics(self.runtime.kernel_client, self.db)
        self.now = 1792281600.0
        self.rows = [dict(post_id=f'post-{i}', account='@test.account', platform='instagram', views=v,
                         published_at=self.stamp(self.now - (i + 2) * 86400), observed_at=self.stamp(self.now))
                     for i, v in enumerate([0, 2, 0])]

    def stamp(self, epoch):
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat()

    def evaluate(self, rows=None):
        return self.guard.evaluate_observations('C24C', self.rows if rows is None else rows, self.now)

    def test_counts_alone_cannot_pause_or_invent_24_hour_views(self):
        before = self.db.get_persona('C24C')
        result = self.guard.evaluate_device_views('C24C', [0, 0, 0])
        self.assertEqual(before, self.db.get_persona('C24C'))
        self.assertEqual('observation_incomplete', result['status'])

    def test_feature_readiness_never_promotes_simulation_to_live_acceptance(self):
        from farm_capabilities import capabilities
        report = capabilities()
        self.assertFalse(report['allMarketingFeaturesAccepted'])
        self.assertFalse(report['liveAutomationReady'])
        features = {f['id']: f for f in report['features']}
        self.assertEqual(len(features), len(report['features']))
        for feature in ('formats', 'warmup', 'replies', 'publish'):
            self.assertIn(features[feature]['availability'], ('Simulation only', 'Unavailable'))

    def test_every_unvalidated_live_action_refuses_before_a_phone_probe(self):
        self.runtime.execution_mode = 'live'
        handler = object.__new__(server.FarmRequestHandler)
        handler._send_json = Mock()
        paths = ('auto-create-and-deploy', 'upload-single', 'single-upload', 'warmup-wave', 'funnel-action', 'funnel-suite')
        with patch.object(server, 'RUNTIME', self.runtime), patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('Must refuse before live access')):
            for path in paths:
                with self.subTest(path=path), self.assertRaises(engine.KernelSafetyError):
                    handler._handle_post('/api/farm/' + path, {'device_id': 'C24C'}, b'{}')
            with self.assertRaises(engine.KernelSafetyError):
                handler._handle_post('/api/farm/scheduler-tick', {'execute_actions': True}, b'{}')
            for action in server.JOB_ACTIONS - {'create-content', 'scan-profile-views', 'scheduler-tick'}:
                with self.subTest(job=action), self.assertRaises(engine.KernelSafetyError):
                    self.runtime.submit_job('unsubmitted', action, {'device_id': 'C24C'})
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_mature_recent_low_views_pause_and_preserve_evidence(self):
        before = self.db.get_persona('C24C')['views_24h']
        result = self.evaluate()
        self.assertTrue(result['paused'])
        self.assertFalse(result['platformRestrictionConfirmed'])
        self.assertEqual('operator_submitted', result['source'])
        self.assertEqual(before, self.db.get_persona('C24C')['views_24h'])
        with self.db._connect() as conn:
            row = conn.execute('SELECT observed_json FROM analytics_observations WHERE id=?', (result['evidenceId'],)).fetchone()
        self.assertEqual(self.rows, json.loads(row[0]))
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_analytics_pause_holds_recurring_preparation_without_automatic_resume(self):
        self.db.update_persona('C24C', account_day=5, paused_zero_view=False)
        self.runtime.preparation.clock = lambda: self.now
        self.runtime.preparation.prepare = Mock(side_effect=AssertionError('Paused account must not render'))
        self.runtime.preparation.configure(dict(id=str(uuid.uuid4()), device_id='C24C', action='create-content',
                                                interval_minutes=60, max_runs=2))
        self.assertTrue(self.evaluate()['paused'])
        self.runtime.preparation.tick()
        self.assertEqual('held', self.runtime.preparation.status()['config']['state'])
        self.evaluate([{**row, 'views': 1000} for row in self.rows])
        self.runtime.preparation.tick()
        self.runtime.preparation.prepare.assert_not_called()
        self.assertFalse(self.runtime.preparation.status()['config']['enabled'])
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_good_observations_never_automatically_clear_a_pause(self):
        self.db.update_persona('C24C', paused_zero_view=True)
        for item in self.rows: item['views'] = 100
        result = self.evaluate()
        self.assertFalse(result['circuitBreakerTripped'])
        self.assertTrue(result['paused'])
        self.assertTrue(self.db.get_persona('C24C')['paused_zero_view'])

    def test_age_and_freshness_boundaries(self):
        for field, value in (('published_at', self.stamp(self.now - 86399)),
                             ('observed_at', self.stamp(self.now - 86401))):
            rows = copy.deepcopy(self.rows); rows[0][field] = value
            result = self.evaluate(rows)
            self.assertEqual('observation_incomplete', result['status'])
            self.assertFalse(self.db.get_persona('C24C')['paused_zero_view'])
        self.rows[0]['published_at'] = self.stamp(self.now - 86400)
        self.assertTrue(self.evaluate()['circuitBreakerTripped'])

    def test_account_identity_duplicate_counts_and_bad_dates_refuse(self):
        for field, value in (('account', '@another'), ('platform', 'tiktok'), ('post_id', 'post-1'),
                             ('views', True), ('views', -1), ('views', 1.5), ('published_at', '2026-10-17'),
                             ('observed_at', self.stamp(self.now + 600))):
            rows = copy.deepcopy(self.rows); rows[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): self.evaluate(rows)
        self.assertFalse(self.db.get_persona('C24C')['paused_zero_view'])

    def test_latest_three_by_post_time_not_input_order(self):
        self.rows.append(dict(post_id='older', account='@test.account', platform='instagram', views=999,
                              published_at=self.stamp(self.now - 9 * 86400), observed_at=self.stamp(self.now)))
        result = self.evaluate(list(reversed(self.rows)))
        self.assertTrue(result['circuitBreakerTripped'])
        self.assertEqual(1001, result['observedViewsTotal'])
        self.assertNotIn('views24h', result)

    def test_early_account_review_cannot_clear_existing_pause(self):
        self.db.update_persona('C24C', account_day=1, paused_zero_view=True)
        result = self.evaluate()
        self.assertFalse(result['circuitBreakerTripped'])
        self.assertTrue(result['paused'])

    def test_analytics_http_dispatch_does_not_require_a_kernel(self):
        handler = object.__new__(server.FarmRequestHandler)
        handler._send_json = Mock()
        with patch.object(server, 'RUNTIME', self.runtime), patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('No phone connection')), patch.object(engine.time, 'time', return_value=self.now):
            handler._handle_post('/api/farm/shadowban-scan', {'device_id': 'C24C', 'observations': self.rows}, b'{}')
        self.assertEqual(200, handler._send_json.call_args.args[0])
        self.assertEqual('operator_submitted', handler._send_json.call_args.args[1]['result']['source'])

    def test_scheduler_uses_requested_utc_day_for_upload_budget(self):
        sched = self.runtime.build_scheduler()
        self.db.update_persona('C24C', account_day=4)
        with self.db._connect() as conn:
            conn.execute('UPDATE personas SET last_warmup_epoch=? WHERE device_id=?', (self.now - 86400, 'C24C'))
        with patch.object(engine, 'utc_now', return_value=self.stamp(self.now)):
            self.db.log_upload('C24C', 'instagram', 'ig_carousel', 'test', 0)
        self.assertEqual('blocked_daily_cap_reached', sched.evaluate_device_upload_readiness('C24C', self.now)['status'])
        self.assertTrue(sched.evaluate_device_upload_readiness('C24C', self.now + 86400)['readyForUpload'])

    def test_scheduler_cooldown_exact_boundary_and_clock_rollback(self):
        sched = self.runtime.build_scheduler()
        duration = sched.required_cooldown_hours('C24C') * 3600
        with self.db._connect() as conn:
            conn.execute('UPDATE personas SET last_warmup_epoch=? WHERE device_id=?', (self.now, 'C24C'))
        self.assertFalse(sched.evaluate_device_upload_readiness('C24C', self.now - 60)['readyForUpload'])
        self.assertFalse(sched.evaluate_device_upload_readiness('C24C', self.now + duration - 1)['readyForUpload'])
        self.assertTrue(sched.evaluate_device_upload_readiness('C24C', self.now + duration)['readyForUpload'])

    def test_phase_one_plans_warmup_instead_of_holding_forever(self):
        self.db.update_persona('C24C', account_day=1)
        sched = self.runtime.build_scheduler()
        plan = sched.run_cohort_tick(1, now_epoch=self.now)
        action = next(a for a in plan['actions'] if a['deviceId'] == 'C24C')
        self.assertEqual('run_warmup', action['plannedAction'])
        self.assertFalse(action['executed'])
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_paused_account_never_runs_a_scheduled_action(self):
        self.db.update_persona('C24C', paused_zero_view=True)
        sched = self.runtime.build_scheduler()
        with patch.object(self.db, 'list_personas', return_value=[self.db.get_persona('C24C')]), patch.object(sched.warmup_engine, 'run_warmup_session') as warmup, patch.object(sched.upload_orchestrator, 'execute_upload') as upload:
            result = sched.run_cohort_tick(1, now_epoch=self.now, execute_actions=True)
        self.assertEqual('hold_blocked_circuit_breaker', result['actions'][0]['plannedAction'])
        warmup.assert_not_called(); upload.assert_not_called()
