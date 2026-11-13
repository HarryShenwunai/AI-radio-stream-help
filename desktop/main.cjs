'use strict';
const { app, BrowserWindow, desktopCapturer, dialog, globalShortcut, ipcMain, Menu, nativeImage, screen, Tray } = require('electron');
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { normalizeBackendURL, trustedNavigation, validateCommand, compactBounds, expandedBounds, restoreOutputBounds } = require('./window-policy.cjs');
const { backendDirectory, selectRuntimeProfile, saveRuntimeProfile } = require('./runtime-profiles.cjs');
const { installMediaPermissions } = require('./media-policy.cjs');
const { createScreenCaptureManager } = require('./screen-capture.cjs');
const { ownerRuntimePaths } = require('./owner-runtime-path.cjs');

app.setName('虚拟陪伴');
let window = null, backend = null, tray = null, backendURL = '', quitting = false;
let expanded = false, clickThrough = false, recoverShortcut = false, recoveryTimer = null;
let savedCompactBounds = null;
let focusHelper = null, focusRestoreAvailable = false;
let runtimeSelection = { profile:'cpu',fallback:null }, runtimeSession = null;
let screenCapture = null;
let displayOutput = null;
const RECOVERY_SHORTCUT = 'CommandOrControl+Shift+Space';
const args = process.argv.slice(app.isPackaged ? 1 : 2);
if (app.isPackaged && !args.includes('--smoke-test')) {
  for (const flag of ['remote-debugging-port', 'remote-debugging-pipe', 'no-sandbox', 'disable-setuid-sandbox']) app.commandLine.removeSwitch(flag);
}
app.enableSandbox();
const findArg = name => args.find(value => value.startsWith(name + '='))?.slice(name.length + 1);
const state = () => ({ expanded, clickThrough, recoveryShortcut: recoverShortcut ? RECOVERY_SHORTCUT : null,
  clickThroughTimeoutSeconds: 60, trayAvailable: Boolean(tray), visible: Boolean(window && window.isVisible()),
  platform: process.platform, focusRestoreAvailable, runtimeProfile:runtimeSelection.profile,
  runtimeFallback:runtimeSelection.fallback, windowCount: BrowserWindow.getAllWindows().length,
  displayOutputId:displayOutput?.id ?? null });
function publishState() { if (window && !window.isDestroyed()) window.webContents.send('companion:desktop-state', state()); }
function ensureNoPendingUIUpdate() {
  if (app.isPackaged && process.platform === 'win32' &&
      fs.existsSync(path.join(process.resourcesPath, 'ui-update-journal.json'))) {
    throw new Error('检测到未完成的界面更新。请重新运行已校验的 apply-ui-update.cmd 完成更新，或运行 rollback-ui-update.cmd 恢复；暂不启动本机服务。');
  }
}
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
  if (displayOutput) restoreDisplayOutput();
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
function displayInfo() {
  const primary = screen.getPrimaryDisplay(), displays = screen.getAllDisplays();
  return { displays:displays.map(item=>({id:item.id,label:item.label||'显示器',is_primary:item.id===primary.id,
    bounds:item.bounds,scale_factor:item.scaleFactor})), external_display_detected:displays.some(item=>item.id!==primary.id),
    output_display_id:displayOutput?.id ?? null };
}
function setDisplayOutput(id) {
  if (!Number.isSafeInteger(id) || !window || window.isDestroyed()) throw new Error('无效显示器。');
  const target = screen.getAllDisplays().find(item=>item.id===id);
  if (!target) throw new Error('所选显示器已断开。');
  if (!displayOutput) displayOutput = { id,bounds:window.getBounds(),expanded,resizable:window.isResizable(),
    alwaysOnTop:window.isAlwaysOnTop(),compact:savedCompactBounds,originalDisplayId:screen.getDisplayMatching(window.getBounds()).id };
  else displayOutput.id=id;
  stopClickThrough(); expanded=false;
  window.setResizable(false); window.setAlwaysOnTop(true,'floating'); setFocusable(true);
  window.setBounds(target.workArea); window.show(); window.focus(); publishState(); return state();
}
function restoreDisplayOutput() {
  if (!displayOutput || !window || window.isDestroyed()) return state();
  const old=displayOutput;displayOutput=null;
  const target=screen.getAllDisplays().find(item=>item.id===old.originalDisplayId)||screen.getPrimaryDisplay();
  expanded=old.expanded;savedCompactBounds=old.compact;stopClickThrough();
  window.setBounds(restoreOutputBounds(old.bounds,target.workArea));window.setResizable(old.resizable);
  window.setAlwaysOnTop(old.alwaysOnTop,'floating');setFocusable(old.expanded);window.showInactive();publishState();return state();
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
  ipcMain.handle('companion:display-output', (event, command, id) => {
    assertSender(event);
    if (command==='list' && id===undefined) return displayInfo();
    if (command==='restore' && id===undefined) return restoreDisplayOutput();
    if (command==='select' && Number.isSafeInteger(id)) return setDisplayOutput(id);
    throw new Error('Invalid display output request');
  });
  ipcMain.handle('companion:screen-preview', async (event, command, captureId) => {
    assertSender(event);
    if (command === 'start' && captureId === undefined) return screenCapture.start();
    if (!['frame','stop'].includes(command) || typeof captureId !== 'string' ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(captureId)) throw new Error('Invalid capture request');
    return command === 'frame' ? screenCapture.frame(captureId) : screenCapture.stop(captureId);
  });
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
    const base = process.platform==='win32'?backendDirectory(process.resourcesPath,runtimeSelection.profile):path.join(process.resourcesPath,'backend');
    const exeName = process.platform === 'win32' ? 'companion-backend.exe' : 'companion-backend';
    for (const candidate of [path.join(base, exeName),path.join(base, 'companion-backend', exeName)]) {
      if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return [candidate, ['--port', String(port), '--no-browser']];
    }
    if (process.platform === 'win32') {
      const python = path.join(base, 'python', 'python.exe');
      const script = path.join(base, 'app', runtimeSelection.profile==='cuda'?'desktop_backend.py':'server.py');
      if ([python, script].every(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile())) {
        return [python, ['-I', '-u', '-X', 'utf8', script, '--port', String(port), '--no-browser']];
      }
    }
    throw new Error('安装包缺少本地后端。');
  }
  return [process.env.COMPANION_PYTHON || 'python3', [path.join(__dirname, '..', 'run.py'), '--port', String(port), '--no-browser']];
}
function backendEnvironment() {
  const env = { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8',
    COMPANION_RUNTIME_PROFILE:runtimeSelection.profile,COMPANION_PROFILE_FALLBACK:runtimeSelection.fallback||'',
    COMPANION_DATA: process.env.COMPANION_DATA || path.join(app.getPath('userData'), 'profile-data') };
  if (app.isPackaged) {
    // Profiles use fixed bundled DLL directories, without global toolkit paths.
    delete env.CUDA_PATH;delete env.HIP_PATH;
    const roots = [path.dirname(process.execPath), path.join(process.resourcesPath, 'backend'), process.resourcesPath];
    for (const [key, folder] of [['COMPANION_MODELS', 'models'], ['COMPANION_VOICES', 'voices']]) {
      if (env[key]) continue;
      const found = roots.map(root => path.join(root, folder)).find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isDirectory());
      env[key] = found || path.join(process.resourcesPath, 'backend', folder);
    }
  }
  return env;
}
async function startBackend() {
  const attached = findArg('--backend-url');
  if (attached) { backendURL = normalizeBackendURL(attached); await waitForBackend(backendURL); return; }
  if(app.isPackaged&&process.platform==='win32')runtimeSelection=selectRuntimeProfile(process.resourcesPath);
  try{await startOwnedBackend();}
  catch(error){
    if(runtimeSelection.profile!=='cuda')throw error;
    stopOwnedBackend();backend=null;backendURL='';
    runtimeSelection={profile:'cpu',fallback:'CUDA配置启动失败，已退回CPU；请检查驱动和运行库。'};
    saveRuntimeProfile(process.resourcesPath,'cpu',runtimeSelection.fallback);
    await startOwnedBackend();
  }
}
async function startOwnedBackend() {
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
  if(runtimeSession)fs.writeFileSync(runtimeSession,JSON.stringify({pid:process.pid,backend_origin:backendURL})+'\n',{mode:0o600});
}
function stopOwnedBackend(){
  if(!backend||backend.exitCode!==null)return;
  const child=backend;
  if(process.platform==='win32'&&child.pid){
    const taskkill=path.join(process.env.SystemRoot||'C:\\Windows','System32','taskkill.exe');
    spawnSync(taskkill,['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore',timeout:2500});
  }
  child.kill('SIGTERM');
  const timer=setTimeout(()=>{if(child.exitCode===null)child.kill('SIGKILL');},2000);timer.unref();
}
function claimRuntimeSession(){
  if(!app.isPackaged||process.platform!=='win32')return;
  runtimeSession=path.join(process.resourcesPath,'runtime-session.json');
  if(fs.existsSync(runtimeSession)){
    if(fs.statSync(runtimeSession).size>4096)throw new Error('运行时锁文件损坏，请在程序关闭后检查。');
    const prior=JSON.parse(fs.readFileSync(runtimeSession,'utf8'));
    if(Number.isSafeInteger(prior.pid)&&prior.pid>0){try{process.kill(prior.pid,0);throw new Error('运行时仍在使用中；请先退出已打开的程序。');}catch(error){if(error.code!=='ESRCH')throw error;}}
    fs.unlinkSync(runtimeSession);
  }
  const fd=fs.openSync(runtimeSession,'wx',0o600);
  try{fs.writeFileSync(fd,JSON.stringify({pid:process.pid})+'\n');}finally{fs.closeSync(fd);}
}

function makeTray() {
  try {
    const image = nativeImage.createFromPath(path.join(__dirname, 'icon.png'));
    if (image.isEmpty()) return;
    tray = new Tray(image); tray.setToolTip('虚拟陪伴');
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: '显示角色', click: restore }, { label: '展开聊天', click: () => setExpanded(true) },
      { label: '返回电脑显示', click: restoreDisplayOutput },
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
  installMediaPermissions({ getWindow: () => window, getBackendURL: () => backendURL, dialog, desktopCapturer, Menu });
  screenCapture = createScreenCaptureManager({ getOwner: () => window, BrowserWindow, desktopCapturer, Menu });
  window.webContents.on('did-start-navigation', (_event, _url, _inPlace, mainFrame) => { if (mainFrame) screenCapture.stopAll(); });
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
  screenCapture?.stopAll();
  focusHelper?.stdin.end();
  stopOwnedBackend();
  if(runtimeSession){try{if(JSON.parse(fs.readFileSync(runtimeSession,'utf8')).pid===process.pid)fs.unlinkSync(runtimeSession);}catch{}}
}
if (args.includes('--owner-runtime-path')) {
  // Read-only owner CLI: bypass backend/window/tray and instance restoration.
  // getPath is available before app.ready, matching backendEnvironment's path.
  try {
    const paths = ownerRuntimePaths({ userData:app.getPath('userData'),
      backendCwd:app.isPackaged ? process.resourcesPath : path.join(__dirname,'..') });
    process.stdout.write(JSON.stringify({ ...paths,backend_started:Boolean(backend),window_count:BrowserWindow.getAllWindows().length })+'\n');
    app.exit(0);
  } catch { process.stderr.write('Owner runtime path is unavailable.\n');app.exit(2); }
}
else if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (window) restore(); });
  app.on('before-quit', cleanup); app.on('window-all-closed', () => app.quit());
  app.whenReady().then(async () => {
    try {
      if (args.includes('--smoke-test')) app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
      ensureNoPendingUIUpdate(); installIPC(); claimRuntimeSession(); await startBackend(); await createWindow();
      screen.on('display-removed', () => {
        if (displayOutput && !screen.getAllDisplays().some(item=>item.id===displayOutput.id)) restoreDisplayOutput();
      });
      screen.on('display-metrics-changed', (_event, display) => {
        if (displayOutput?.id===display.id && window && !window.isDestroyed()) window.setBounds(display.workArea);
      });
      recoverShortcut = globalShortcut.register(RECOVERY_SHORTCUT, restore);
      makeTray(); publishState();
    } catch (error) {
      console.error('Desktop startup failed:', error.message);
      if(app.isPackaged&&!args.includes('--smoke-test'))dialog.showErrorBox('本机程序未能启动',error.message+'\n请确认已完整解压。缺少MSVCP140/VCOMP140时请查看微软官方VC++ x64运行库说明；程序不会自行修改系统运行库。');
      cleanup(); app.exit(1);
    }
  });
}
