"""The re-check gate for a saved Reel attempt whose creation stopped right after saving. Offline."""
import unittest

from farm_fleet_verify import saved_then_stopped


def run(**changes):
    action = dict(label='save-reel-draft-once', state='answered', observationId='o1')
    toast = dict(observationId='o2', observation=dict(text=dict(lines=[dict(text='Draft saved')])))
    workflow = dict(cleanup='confirmed', actions=[action], observations=[dict(observationId='o1'), toast])
    workflow.update(changes.pop('workflow', {}))
    return dict(dict(terminal=True, state='review_required', savedDraftVerified=False, workflow=workflow), **changes)


class Gate(unittest.TestCase):
    def test_saved_and_stopped_passes(self):
        self.assertTrue(saved_then_stopped(run()))

    def test_everything_else_is_refused(self):
        for bad in (run(terminal=False), run(savedDraftVerified=True), run(workflow=dict(cleanup='unconfirmed')),
                    run(workflow=dict(verification={})), run(workflow=dict(actions=[])),
                    run(workflow=dict(actions=[dict(label='open-reel-editor', state='answered', observationId='o1')])),
                    run(workflow=dict(actions=[dict(label='save-reel-draft-once', state='outcome_unknown', observationId='o1')])),
                    run(workflow=dict(observations=[dict(observationId='o1')]))):
            self.assertFalse(saved_then_stopped(bad))


if __name__ == '__main__':
    unittest.main()
