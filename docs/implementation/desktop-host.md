# Desktop host implementation

The host reuses one local application page, one backend, and the page's existing
audio owner. Compact/expanded modes resize the same native window. Character
images remain user-imported assets; the host contains no character catalog.

## Build and run

Windows 10/11 x64 is the requested delivery target. Build on Windows x64:

```powershell
npm ci --prefix desktop
node desktop/test/window-policy.test.cjs
node desktop/build-windows.cjs --backend=.build/native/companion-backend --output=.build/desktop/character-windows-x64
python -m pip install playwright psutil Pillow
python desktop/test/windows_smoke.py
```

The backend directory must contain the actual Windows PyInstaller onedir build,
including `companion-backend.exe` and its `_internal` directory. The portable
directory includes the pinned official Electron runtime, its license files,
application notices and licenses, the limited main/preload bridge, and the native
backend. Extract the whole directory before opening `companion-desktop.exe`.
There is no electron-builder dependency or browser download for the smoke test.
The smoke connects to the packaged Electron's local CDP port only during testing.
The normal executable does not enable CDP automatically.

Optional `models` and `voices` directories belong next to the portable executable.
Existing `COMPANION_MODELS` / `COMPANION_VOICES` take precedence. Model assets are
added by the final packaging workflow; these builders do not download them.
User data defaults to Electron's per-user directory; `COMPANION_DATA` supports an
isolated test profile. The Chinese README distinguishes full and reduced packages.

Linux x64 development/build commands:

```sh
npm ci --prefix desktop
node desktop/build-linux.cjs --backend=/absolute/native/backend --output=/new/empty/output
```

Linux builds require a C compiler and X11 development headers for the optional
focus-restoration helper (`COMPANION_X11_INCLUDE` can identify workspace headers).
Development launch: `npm start --prefix desktop`; this spawns repository `run.py`
using `COMPANION_PYTHON` or `python3`. `--backend-url=http://127.0.0.1:PORT` attaches
an explicitly existing local service instead. Packaged startup automatically
spawns its embedded executable on an OS-assigned loopback port.

## Window and permission boundaries

- Default: transparent compact window, topmost, inactive startup. Expansion is
  an explicit focus request. Collapse preserves the document and audio owner.
- Drag the toolbar. Hide requires a successfully registered
  `Ctrl+Shift+Space` recovery shortcut. Tray recovery is additional; creating a
  Tray object is not evidence the desktop actually displays it.
- Mouse ignore expires after 60 seconds and can be cleared through the shortcut
  or tray. Expansion and restore also clear mouse ignore.
- Renderer uses `sandbox: true`, `contextIsolation: true`,
  `nodeIntegration: false`. Preload exposes only typed window operations.
  Main verifies the main frame and its exact attached loopback page.
- External navigation, new windows and webview attachment are denied. A model
  cannot select an executable, shell command, navigation target, or window ID.
- Microphone access requires an explicit native confirmation when requested;
  camera and other permission types are denied. No account connection occurs.
- The X11 helper reads only the active window ID and restores the previous ID
  after explicit collapse. It blocks on events/stdin rather than polling and
  never reads titles, pixels, keystrokes or application contents. It is not
  included in Windows packages. Other window managers may ignore its request.
- Exit stops the owned backend; attached external backends are untouched. Windows
  uses the fixed system `taskkill.exe /PID <owned pid> /T /F` to include PyInstaller
  descendants. No renderer-supplied PID or arbitrary command is accepted.

## Evidence and remaining acceptance

`desktop/test-results/` stores actual execution reports. `window-policy.test.cjs`
has four tests for loopback restrictions, navigation, typed bridge payloads and
small/normal monitor bounds. `smoke.py` uses a synthetic local page for native
window count, renderer isolation, bridge rejection, stop, collapse, timed-ignore
state, recovery and navigation restrictions. `native_window_probe.py` additionally
uses a real X11 compositor plus XTest to check transparency, actual underlying
pointer receipt, restoration and keyboard-focus ownership. Its passing scope is
the observed Linux X11/xfwm4 configuration, not Windows or all compositors.

`bundled_app_smoke.py` / `windows_smoke.py` launch the actual portable executable
without an attached URL, verify its child backend, create a character in the real
UI, preview/activate a synthetic PNG, exercise the same window, and check owned
backend/helper exit. These scripts do not infer from API existence alone. They do
not test voice/model quality, physical multi-DPI displays, exclusive fullscreen
games or all Windows 10/11 configurations. Windows script presence is not a
Windows pass; the CI report must exist and pass before making that claim.

One earlier packaged synthetic-page observation (GPU disabled, CDP enabled) was
0.856 seconds to ready, approximately 239 MiB process-tree PSS, and 0.4% of one
CPU core across five idle seconds. RSS sums shared pages repeatedly. This excludes
Python/Xvfb and models, is one cloud observation, and is neither p95 nor a target
Windows resource budget. Actual target-device idle CPU/PSS, start time, loaded
LLM/TTS resource use and game frame impact remain acceptance work.

## Pitfalls found by executing the host

1. Electron's Linux `blur()` / `setFocusable(false)` did not restore focus after
   expansion on the tested X11 WM. A scoped native helper fixed this in an actual
   focus test. Temporary hide/show would stop ongoing explicit voice, so collapse
   never hides the page.
2. `BrowserWindow.hide()` did not consistently change `document.hidden` in the
   real Electron test. Desktop state explicitly sets `companionDesktopHidden`,
   pauses media, and frontend late-audio/recognition guards must check both.
3. `Tray` constructor success does not prove there is a visible tray host. Hiding
   is gated on a registered recovery shortcut, and pointer-ignore has a timer.
4. Merely reserving a port and releasing it creates a startup race. Backend binds
   port zero and returns its bound loopback address; the host parses bounded
   stdout then checks HTTP readiness.
5. Test screenshots of a geometric fixture are evidence about window behavior,
   not a finished anime character or a visual-quality assessment.
6. The Electron npm package can install without a downloaded runtime in this
   environment. Official install/download checksums were checked; provenance is
   recorded in `desktop/dependency-provenance.json`. TLS validation stayed enabled.
