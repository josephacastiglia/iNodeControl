"""Run farm tests at Windows Idle priority so a live rack window on this PC keeps the CPU. No socket or phone.

python run_suite.py               -> the complete farm suite, as `cd tools; python -m unittest discover -s . -p "test_farm*.py"`
python run_suite.py NAME [NAME..] -> only these test names (modules, classes or methods)
Child processes (FFmpeg, the OCR bridge) inherit the priority class.
"""
import ctypes
import os
from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[2] / 'tools'


def main(names):
    if os.name == 'nt':
        IDLE_PRIORITY_CLASS = 0x40
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), IDLE_PRIORITY_CLASS)
    os.chdir(TOOLS); sys.path.insert(0, str(TOOLS))
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromNames(names) if names else loader.discover('.', pattern='test_farm*.py')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
