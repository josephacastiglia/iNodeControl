"""Where the farm's shared state lives.

Installed (Farm.ps1 sets IMOUSE_FARM_DATA): every piece of private state is in that per-machine data
folder, laid out as below; the code folder is never written. MAIN is the data folder, the evidence
archive is <data>/evidence-archive, and the rack and window state is <data>/rack.

Dev checkout (IMOUSE_FARM_DATA unset): the paths of 27 Oct, with the rack scripts and their state in
rack/ since 9 Nov. The rack belongs to the main folder:
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
STATE = MAIN / 'rack'  # checkout: beside the rack scripts; installed: farm_install.RACK_STATE in the data folder
RACK = STATE / 'slots'
# One phone run on the rack at a time, for the runs that opt in (farm_rack_lock.py; the slot runner does):
# heavy OCR from parallel runs aged decisions past the 1.5 s frame limit (4 Nov).
RUN_LOCK = MAIN / 'output' / 'farm-state' / 'rack-run.lock'


def rack_state(default):
    """A rack script's state folder (windows/, slots/, identify/, rack-b-*.json ...): the data folder's
    when installed, else `default`, the script's own folder as today."""
    return STATE if DATA else Path(default)


def run_root(default):
    """The folder that holds output/ (candidate-runs, farm-data ...): the data folder when installed,
    else `default`, the checkout as today."""
    return MAIN if DATA else Path(default)


def source_option(argv, default, flag='--source'):
    """Take `flag DIR` out of argv and return DIR. Without it: `default` (today's sibling-repo input) in a
    checkout; installed there is no sibling repo, so the flag is required."""
    if flag in argv:
        i = argv.index(flag)
        if i + 1 >= len(argv):
            raise SystemExit(f'{flag} needs a folder.')
        value = argv[i + 1]
        del argv[i:i + 2]
        return Path(value)
    if DATA:
        raise SystemExit(f'Installed: pass {flag} <config folder>; there is no sibling checkout to read.')
    return Path(default)


def account_label(key='v1CandidateAccount'):
    """An account label kept in per-machine private data, never in code, Git or a package:
    <evidence archive>/privacy/farm-accounts.json. '' when this machine has none (a check against it then fails)."""
    import json
    try:
        return str(json.loads((ARCHIVE / 'privacy' / 'farm-accounts.json').read_text(encoding='utf-8'))[key])
    except (OSError, ValueError, KeyError):
        return ''


def machine_config():
    """Installed: <data>/machine.json (per-machine settings the operator writes once); {} in a checkout or when absent."""
    if not DATA:
        return {}
    import json
    path = MAIN / 'machine.json'
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}


def lan_address(default):
    """The PC's farm-network IPv4 address, which window media servers bind and phones fetch from.
    Checkout: `default`, as today. Installed: IMOUSE_FARM_LAN, else machine.json "lanAddress", else the one
    private IPv4 address this PC has; with none or several, stop and list them (the operator picks one)."""
    if not DATA:
        return default
    import ipaddress
    import socket
    chosen = os.environ.get('IMOUSE_FARM_LAN') or machine_config().get('lanAddress')
    if chosen:
        ipaddress.IPv4Address(chosen)  # a typo stops here, not when a phone cannot connect
        return chosen
    found = sorted({i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
    private = [a for a in found if ipaddress.ip_address(a).is_private and not ipaddress.ip_address(a).is_loopback
               and not ipaddress.ip_address(a).is_link_local]
    if len(private) == 1:
        return private[0]
    raise SystemExit('Set the farm network address: write {"lanAddress": "<address>"} to ' + str(MAIN / 'machine.json')
                     + ' (this PC has: ' + (', '.join(private) or 'no private IPv4 address') + ').')


def installed(name, default=None):
    """An installed component Farm.ps1 names (IMOUSE_FARM_KERNEL, _RECEIVER, _RECEIVER_RUNTIME, _PYTHON):
    that path when installed and set, else `default`."""
    value = os.environ.get('IMOUSE_FARM_' + name.upper()) if DATA else None
    if value:
        return Path(value)
    return Path(default) if default is not None else None
