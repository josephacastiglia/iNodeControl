"""Old name of farm_owned_capture, kept only for four rack scripts that still import it.

analysis/farm-multiphone-20261020/close_app.py, discard_leftover.py, one_tap.py and switcher_probe.py read
InspectionStopped from here. Delete this file once they import it from farm_owned_capture.
"""
from farm_owned_capture import InspectionStopped  # noqa: F401
