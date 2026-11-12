"""Run the real portable bundle/backend smoke on Windows CI without browser download."""
import os,runpy
from pathlib import Path
if os.name != 'nt':raise SystemExit('Windows smoke must execute on Windows, not emulate success on Linux')
runpy.run_path(str(Path(__file__).with_name('bundled_app_smoke.py')),run_name='__main__')
