"""What the rack's connect scripts share about Screen Mirroring: the calibrated points and the Bonjour list.

The points are C24C's calibration (500x1080 frame); the rack scripts in rack/
(auto_connect.py, card_survey.py, rack_recovery.py) decide when and whether to use them, under a
lease. Nothing here sends input.
"""
import re
import subprocess
import time

# C24C calibration (500x1080 frame): Control Center's Screen Mirroring tile (16 Sep and 19 Oct
# captures), and the not-yet-mirroring sheet's rows (20 Oct screenshot; separators 458/520/583/645/709).
TILE = (199, 432)
ROWS = ((250, 489), (250, 551), (250, 614), (250, 677))
CLOSE = (250, 960)            # Below the mirroring sheet (card ends at y 755) and the Control Center grid.


def natural(name):
    return [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', name.casefold())]


COLLATIONS = (lambda n: n, str.casefold, natural)


LINE = re.compile(r'^\s*\S+\s+(Add|Rmv)\s+\d+\s+\d+\s+(\S+)\s+_airplay\._tcp\.\s+(.+?)\s*$')


def parse_browse(output):
    present = set()
    for line in output.splitlines():
        match = LINE.match(line)
        if not match: continue
        action, _, name = match.groups()
        (present.add if action == 'Add' else present.discard)(name)
    return present


def browse(seconds=3.0):
    """AirPlay receivers this PC currently sees over Bonjour (dns-sd)."""
    process = subprocess.Popen(['dns-sd', '-B', '_airplay._tcp', 'local.'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        time.sleep(seconds)
    finally:
        process.kill()
    output = process.communicate(timeout=5)[0].decode('utf-8', 'replace')
    return parse_browse(output), output
