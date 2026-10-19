"""Run the existing self-check, forbidding real rack and external connections."""
from pathlib import Path
import runpy
import sys


def offline_only(event, args):
    if event == "socket.connect":
        address = args[1]
        if (not isinstance(address, tuple)
                or address[0] not in ("127.0.0.1", "::1")
                or address[1] in (9911, 9913, 9914)):
            raise AssertionError("Real service or external network access forbidden during self-check")


sys.addaudithook(offline_only)
script = Path(__file__).resolve().parents[2] / "tools" / "imouse_farm_server.py"
sys.argv = [str(script), "--self-check"]
runpy.run_path(str(script), run_name="__main__")
