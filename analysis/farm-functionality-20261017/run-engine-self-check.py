"""Execute the legacy engine check in temporary storage with all sockets blocked."""
from pathlib import Path
import sys


def offline_only(event, args):
    if event == "socket.connect":
        raise AssertionError("Engine self-check may not contact any service.")


sys.addaudithook(offline_only)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import imouse_social_automation as engine
engine.self_check()
