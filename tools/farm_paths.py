"""Where the farm's shared state lives.

Installed (Farm.ps1 sets IMOUSE_FARM_DATA): every piece of private state is in that per-machine data
folder, laid out as below; the code folder is never written. MAIN is the data folder, the evidence
archive is <data>/evidence-archive, and the rack and window state is <data>/analysis/farm-multiphone-20261020.

Dev checkout (IMOUSE_FARM_DATA unset): exactly the paths of 27 Oct. The rack belongs to the main folder:
the multi-phone kernel's preparation and process record are written there, and the private evidence
archive sits beside it. Switchboard makes each lane's folder at <main folder>.worktrees/<lane>, so a tool
there finds the main folder by that name. (Git's own common directory would not do: this checkout is
itself a worktree of iMouseXP-2.0.) From the main folder these are the paths they always were. Rack
scripts keep their per-checkout state (windows/, identify/ ...) beside themselves: rack_state(HERE).
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SUFFIX = '.worktrees'  # release-lint: dev-fallback
DATA = os.environ.get('IMOUSE_FARM_DATA') or None

if DATA:
    MAIN = Path(DATA).resolve()
    ARCHIVE = MAIN / 'evidence-archive'
else:
    MAIN = HERE.parent.with_name(HERE.parent.name[:-len(SUFFIX)]) if HERE.parent.name.endswith(SUFFIX) else HERE  # release-lint: dev-fallback
    ARCHIVE = MAIN.parent / 'iMouseXP-2.0-evidence-archive'  # release-lint: dev-fallback
STATE = MAIN / 'analysis' / 'farm-multiphone-20261020'
RACK = STATE / 'slots'


def rack_state(default):
    """A rack script's state folder (windows/, slots/, identify/, rack-b-*.json ...): the data folder's
    when installed, else `default`, the script's own folder as today."""
    return STATE if DATA else Path(default)


def run_root(default):
    """The folder that holds output/ (candidate-runs, farm-data ...): the data folder when installed,
    else `default`, the checkout as today."""
    return MAIN if DATA else Path(default)


def installed(name, default=None):
    """An installed component Farm.ps1 names (IMOUSE_FARM_KERNEL, _RECEIVER, _RECEIVER_RUNTIME, _PYTHON):
    that path when installed and set, else `default`."""
    value = os.environ.get('IMOUSE_FARM_' + name.upper()) if DATA else None
    if value:
        return Path(value)
    return Path(default) if default is not None else None
