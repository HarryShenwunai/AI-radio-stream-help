'use strict';
const { app, BrowserWindow, dialog, globalShortcut, ipcMain, Menu, nativeImage, screen, Tray } = require('electron');
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { normalizeBackendURL, trustedNavigation, validateCommand, compactBounds, expandedBounds } = require('./window-policy.cjs');

app.setName('虚拟陪伴');
let window = null, backend = null, tray = null, backendURL = '', quitting = false;
let expanded = false, clickThrough = false, recoverShortcut = false, recoveryTimer = null;
let savedCompactBounds = null, microphoneGranted = false;
let focusHelper = null, focusRestoreAvailable = false;
const RECOVERY_SHORTCUT = 'CommandOrControl+Shift+Space';
const args = process.argv.slice(app.isPackaged ? 1 : 2);
const findArg = name => args.find(value => value.startsWith(name + '='))?.slice(name.length + 1);
const state = () => ({ expanded, clickThrough, recoveryShortcut: recoverShortcut ? RECOVERY_SHORTCUT : null,
  clickThroughTimeoutSeconds: 60, trayAvailable: Boolean(tray), visible: Boolean(window && window.isVisible()),
  platform: process.platform, focusRestoreAvailable, windowCount: BrowserWindow.getAllWindows().length });
function publishState() { if (window && !window.isDestroyed()) window.webContents.send('companion:desktop-state', state()); }
function setFocusable(value) {
  // Electron documents this setter for Windows/macOS. Linux uses showInactive.
  if (window && ['win32', 'darwin'].includes(process.platform)) window.setFocusable(value);
}
function stopClickThrough() {
  clearTimeout(recoveryTimer); recoveryTimer = null; clickThrough = false;
  if (window && !window.isDestroyed()) window.setIgnoreMouseEvents(false);
}
function setExpanded(value, focus = true) {
  if (!window || window.isDestroyed()) return;
  stopClickThrough();
  if (!expanded) savedCompactBounds = window.getBounds();
  expanded = value;
  const display = screen.getDisplayMatching(window.getBounds());
  window.setBounds(value ? expandedBounds(display.workArea) : savedCompactBounds || compactBounds(display.workArea));
  window.setResizable(value); window.setAlwaysOnTop(!value, 'floating');
  setFocusable(value);
  if (value && focus) { window.show(); window.focus(); }
  else {
    window.blur(); window.showInactive();
    if (focusRestoreAvailable && focusHelper?.stdin.writable) focusHelper.stdin.write('restore\n');
  }
  publishState();
}
function restore() { stopClickThrough(); setExpanded(false, false); window?.showInactive(); publishState(); }
function setClickThrough(value) {
  if (!window || window.isDestroyed()) return;
  stopClickThrough();
  if (value) {
    if (expanded) throw new Error('先收起聊天，再开启鼠标穿透。');
    clickThrough = true;
    window.setIgnoreMouseEvents(true, { forward: true });
    // A timed recovery works even when the desktop has no tray or global hotkeys.
    recoveryTimer = setTimeout(() => { stopClickThrough(); publishState(); }, 60_000);
    recoveryTimer.unref();
  }
  publishState();
}
function hide() {
  stopClickThrough();
  // Without a verified shortcut, do not hide the only discoverable surface.
  if (!recoverShortcut) throw new Error('当前系统未注册恢复快捷键；请使用收起或退出。');
  window?.hide(); publishState();
}
function assertSender(event) {
  if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame ||
      !trustedNavigation(event.senderFrame.url, backendURL)) throw new Error('Untrusted desktop request');
}
function installIPC() {
  ipcMain.handle('companion:desktop', (event, command, value) => {
    assertSender(event); validateCommand(command, value);
    if (command === 'set-expanded') setExpanded(value);
    else if (command === 'set-click-through') setClickThrough(value);
    else if (command === 'hide') hide();
    else if (command === 'restore') restore();
    else if (command === 'quit') app.quit();
    return state();
  });
}
async function waitForBackend(url) {
  const deadline = Date.now() + 25_000;
  while (Date.now() < deadline) {
    if (backend?.startError) throw new Error('本地后端无法启动：' + backend.startError);
    if (backend && backend.exitCode !== null) throw new Error('本地后端提前退出，请检查Python与依赖。');
    const ready = await new Promise(resolve => {
      const request = http.get(url, response => { const ok = response.statusCode === 200; response.resume(); resolve(ok); });
      request.setTimeout(500, () => request.destroy()); request.on('error', () => resolve(false));
    });
    if (ready) return;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error('本地后端启动超时。');
}
function backendCommand(port) {
  if (app.isPackaged) {
    const exeName = process.platform === 'win32' ? 'companion-backend.exe' : 'companion-backend';
    for (const candidate of [path.join(process.resourcesPath, 'backend', exeName),
      path.join(process.resourcesPath, 'backend', 'companion-backend', exeName)]) {
      if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return [candidate, ['--port', String(port), '--no-browser']];
    }
    throw new Error('安装包缺少本地后端。');
  }
  return [process.env.COMPANION_PYTHON || 'python3', [path.join(__dirname, '..', 'run.py'), '--port', String(port), '--no-browser']];
}
function backendEnvironment() {
  const env = { ...process.env, COMPANION_DATA: process.env.COMPANION_DATA || path.join(app.getPath('userData'), 'profile-data') };
  if (app.isPackaged) {
    const roots = [path.dirname(process.execPath), path.join(process.resourcesPath, 'backend'), process.resourcesPath];
    for (const [key, folder] of [['COMPANION_MODELS', 'models'], ['COMPANION_VOICES', 'voices']]) {
      if (env[key]) continue;
      const found = roots.map(root => path.join(root, folder)).find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isDirectory());
      if (found) env[key] = found;
    }
  }
  return env;
}
async function startBackend() {
  const attached = findArg('--backend-url');
  if (attached) { backendURL = normalizeBackendURL(attached); await waitForBackend(backendURL); return; }
  const [command, commandArgs] = backendCommand(0);
  backend = spawn(command, commandArgs, { cwd: app.isPackaged ? process.resourcesPath : path.join(__dirname, '..'),
    env: backendEnvironment(), stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  backend.stderr.on('data', () => {}); // Application content is not written to desktop logs.
  backendURL = await new Promise((resolve, reject) => {
    let text = '';
    const timer = setTimeout(() => reject(new Error('本地后端没有返回启动地址。')), 25_000);
    const failed = error => { clearTimeout(timer); reject(error); };
    backend.once('error', failed);
    backend.once('exit', () => { if (!backendURL) failed(new Error('本地后端提前退出。')); });
    backend.stdout.on('data', chunk => {
      text += chunk.toString('utf8');
      if (text.length > 32768) text = text.slice(-16384);
      const match = text.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(normalizeBackendURL(match[0])); }
    });
  });
  await waitForBackend(backendURL);
}

function makeTray() {
  try {
    const image = nativeImage.createFromPath(path.join(__dirname, 'icon.png'));
    if (image.isEmpty()) return;
    tray = new Tray(image); tray.setToolTip('虚拟陪伴');
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: '显示角色', click: restore }, { label: '展开聊天', click: () => setExpanded(true) },
      { label: '恢复鼠标', click: () => { stopClickThrough(); publishState(); } },
      { type: 'separator' }, { label: '退出', click: () => app.quit() },
    ]));
    tray.on('click', restore);
  } catch { tray = null; }
}
async function createWindow() {
  const workArea = screen.getPrimaryDisplay().workArea;
  window = new BrowserWindow({ ...compactBounds(workArea), show: false, transparent: true, frame: false,
    resizable: false, hasShadow: false, alwaysOnTop: true, skipTaskbar: false,
    backgroundColor: '#00000000', title: '虚拟陪伴', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), nodeIntegration: false,
      contextIsolation: true, sandbox: true, webSecurity: true, allowRunningInsecureContent: false,
      backgroundThrottling: true, devTools: !app.isPackaged } });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => { if (!trustedNavigation(url, backendURL)) event.preventDefault(); });
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.webContents.session.setPermissionRequestHandler(async (contents, permission, callback, details) => {
    if (contents !== window?.webContents || !trustedNavigation(contents.getURL(), backendURL) ||
        permission !== 'media' || !details.mediaTypes?.length || details.mediaTypes.some(type => type !== 'audio')) return callback(false);
    const answer = await dialog.showMessageBox(window, { type: 'question', buttons: ['取消', '允许麦克风'],
      defaultId: 0, cancelId: 0, message: '允许这次使用麦克风？', detail: '只在你主动开启语音输入时采集。' });
    microphoneGranted = answer.response === 1; callback(microphoneGranted);
  });
  window.webContents.on('did-finish-load', publishState);
  window.on('closed', () => { window = null; if (!quitting) app.quit(); });
  window.on('close', () => { stopClickThrough(); });
  await startFocusHelper();
  setFocusable(false); await window.loadURL(backendURL); window.showInactive();
  if (findArg('--expanded') === 'true') setExpanded(true);
}
async function startFocusHelper() {
  if (process.platform !== 'linux' || !process.env.DISPLAY) return;
  const executable = path.join(__dirname, 'focus-x11');
  if (!fs.existsSync(executable)) return;
  const own = window.getNativeWindowHandle().readUInt32LE(0);
  focusHelper = spawn(executable, [String(own)], { stdio: ['pipe', 'pipe', 'ignore'] });
  focusHelper.stdin.on('error', () => {});
  focusHelper.on('error', () => { focusRestoreAvailable = false; });
  focusHelper.on('exit', () => { focusRestoreAvailable = false; });
  await new Promise(resolve => {
    const timer = setTimeout(resolve, 1000);
    focusHelper.stdout.once('data', data => {
      focusRestoreAvailable = data.toString('utf8').trim() === 'ready'; clearTimeout(timer); resolve();
    });
    focusHelper.once('error', () => { clearTimeout(timer); resolve(); });
    focusHelper.once('exit', () => { clearTimeout(timer); resolve(); });
  });
}
function cleanup() {
  if (quitting) return; quitting = true;
  stopClickThrough(); globalShortcut.unregisterAll(); tray?.destroy(); tray = null;
  focusHelper?.stdin.end();
  if (backend && backend.exitCode === null) {
    const child = backend;
    // Windows kill() alone can leave a PyInstaller bootloader descendant alive.
    // Only our owned process identifier is accepted; no renderer command is used.
    if (process.platform === 'win32' && child.pid) {
      const taskkill = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'taskkill.exe');
      spawnSync(taskkill, ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore', timeout: 2500 });
    }
    child.kill('SIGTERM');
    const killTimer = setTimeout(() => { if (child.exitCode === null) child.kill('SIGKILL'); }, 2000);
    killTimer.unref();
  }
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (window) restore(); });
  app.on('before-quit', cleanup); app.on('window-all-closed', () => app.quit());
  app.whenReady().then(async () => {
    try {
      if (args.includes('--smoke-test')) app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
      installIPC(); await startBackend(); await createWindow();
      recoverShortcut = globalShortcut.register(RECOVERY_SHORTCUT, restore);
      makeTray(); publishState();
    } catch (error) { console.error('Desktop startup failed:', error.message); cleanup(); app.exit(1); }
  });
}
