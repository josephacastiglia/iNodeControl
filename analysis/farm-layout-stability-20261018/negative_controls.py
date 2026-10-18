"""Deliberately disable guards in memory; regression tests must catch it."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from test_farm_screen_layout import LayoutTests
from test_farm_draft_rehearsal import RehearsalTests


def main():
    cases=[
        ('without_layout_corroboration',LayoutTests,'test_partial_next_needs_frame_geometry_without_repairing_text',
         'farm_observations.editor_controls',None),
        ('without_autoplay_exclusion',RehearsalTests,'test_full_sequence_saves_once_checks_every_slide_and_reopens_persisted_model',
         'farm_draft_rehearsal.picker_stability',dict(controlsStable=False)),
        ('without_control_stability_guard',RehearsalTests,'test_picker_changes_expiry_stream_change_and_cancellation_stop_before_navigation',
         'farm_draft_rehearsal.picker_stability',dict(controlsStable=True)),
        ('without_exact_next_guard',RehearsalTests,'test_editor_layout_is_not_permission_to_press_an_ambiguous_next_button',
         'farm_draft_rehearsal.next_label',dict(label='Next')),
    ]
    rows=[]
    for name,cls,method,target,result in cases:
        stream=io.StringIO()
        with patch(target,return_value=result):
            outcome=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite([cls(method)]))
        (Path(__file__).parent/(name+'.txt')).write_text(stream.getvalue(),encoding='utf-8')
        row=dict(name=name,failures=len(outcome.failures),errors=len(outcome.errors),
                 regressionCaught=bool(outcome.failures) and not outcome.errors)
        rows.append(row); print(json.dumps(row),flush=True)
    (Path(__file__).parent/'negative-controls.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    assert all(r['regressionCaught'] for r in rows)


if __name__=='__main__': main()
