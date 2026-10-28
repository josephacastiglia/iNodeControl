"""Where the farm's shared state lives when a tool runs from a lane's worktree (Switchboard, 27 Oct).
The rack belongs to the main folder: the multi-phone kernel's preparation and process record are
written there, and the private evidence archive sits beside it. Switchboard makes each lane's folder
at <main folder>.worktrees/<lane>, so a tool there finds the main folder by that name. (Git's own
common directory would not do: this checkout is itself a worktree of iMouseXP-2.0.) From the main
folder these are the paths they always were.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SUFFIX = '.worktrees'

MAIN = HERE.parent.with_name(HERE.parent.name[:-len(SUFFIX)]) if HERE.parent.name.endswith(SUFFIX) else HERE
ARCHIVE = MAIN.parent / 'iMouseXP-2.0-evidence-archive'
RACK = MAIN / 'analysis/farm-multiphone-20261020/slots'
