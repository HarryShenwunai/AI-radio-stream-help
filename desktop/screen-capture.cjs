'use strict';
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { randomUUID } = require('node:crypto');

function chooseSource({ owner, desktopCapturer, Menu, valid, timeoutMs = 60_000 }) {
  return new Promise(resolve => {
    let done = false, menu = null, choosing = false;
    const finish = value => {
      if (done) return; done = true; clearTimeout(timer);
      owner.removeListener('hide', cancel); owner.removeListener('closed', cancel);
      if (menu) { try { menu.closePopup(owner); } catch {} }
      resolve(value);
    };
    const cancel = () => finish(null);
    const timer = setTimeout(cancel, timeoutMs); timer.unref?.();
    owner.once('hide', cancel); owner.once('closed', cancel);
    const options = { types: ['screen', 'window'], thumbnailSize: { width: 0, height: 0 }, fetchWindowIcons: false };
    void (async () => {
      try {
        const sources = await desktopCapturer.getSources(options);
        if (done || !valid()) return cancel();
        const allowed = sources.filter(item => /^(screen|window):[0-9]+:[0-9]+$/.test(item.id));
        if (!allowed.length || allowed.length > 256) return cancel();
        const select = source => {
          choosing = true;
          void (async () => {
            try {
              const fresh = await desktopCapturer.getSources(options);
              const selected = fresh.find(item => item.id === source.id);
              finish(!done && valid() && selected ? selected : null);
            } catch { cancel(); }
          })();
        };
        const groups = ['screen', 'window'].map(type => ({ label: type === 'screen' ? '显示器' : '窗口',
          submenu: allowed.filter(item => item.id.startsWith(type + ':')).map(source => ({
            label: String(source.name || source.id).replace(/[\x00-\x1f\x7f]/g, '').slice(0, 140).replace(/&/g, '&&'), click: () => select(source),
          })) })).filter(group => group.submenu.length);
        menu = Menu.buildFromTemplate([{ label: '选择本机预览范围（不含音频）', enabled: false },
          { type: 'separator' }, ...groups, { type: 'separator' }, { label: '取消', click: cancel }]);
        menu.popup({ window: owner, callback: () => { if (!choosing) cancel(); } });
      } catch { cancel(); }
    })();
  });
}

function createScreenCaptureManager({ getOwner, BrowserWindow, desktopCapturer, Menu, now = Date.now,
  lifetimeMs = 900_000, pickerTimeoutMs = 60_000 }) {
  let active = null, starting = false, epoch = 0;
  const finished = new Set();
  function remember(id) { finished.add(id); if (finished.size > 32) finished.delete(finished.values().next().value); }
  function stop(id) {
    if (!active || active.id !== id) return { capture_id: id, stopped: finished.has(id) };
    const old = active; active = null; epoch++; clearTimeout(old.timer);
    old.owner.removeListener('hide', old.onStop); old.owner.removeListener('closed', old.onStop); old.owner.removeListener('minimize', old.onStop);
    if (!old.window.isDestroyed()) old.window.destroy();
    remember(id); return { capture_id: id, stopped: true };
  }
  function stopAll() { epoch++; if (active) stop(active.id); }
  async function start() {
    if (starting || active) throw new Error('请先关闭现有屏幕预览。');
    const owner = getOwner(), ticket = epoch;
    if (!owner || owner.isDestroyed() || !owner.isVisible()) throw new Error('主窗口不可用。');
    starting = true;
    const valid = () => getOwner() === owner && !owner.isDestroyed() && owner.isVisible() && epoch === ticket;
    try {
      const selected = await chooseSource({ owner, desktopCapturer, Menu, valid, timeoutMs: pickerTimeoutMs });
      if (!selected || !valid()) throw new Error('已取消屏幕预览。');
      const id = randomUUID(), localPath = path.join(__dirname, 'screen-capture.html'), localURL = pathToFileURL(localPath).href;
      const child = new BrowserWindow({ width: 720, height: 560, parent: owner, show: false,
        title: '屏幕本机预览', autoHideMenuBar: true, webPreferences: {
          partition: 'capture-'+id, sandbox: true, nodeIntegration: false, contextIsolation: true,
          webSecurity: true, allowRunningInsecureContent: false, devTools: false,
        } });
      const entry = { id, window: child, owner, source: selected, lastFrame: 0, inflight: false, timer: null, onStop: () => stop(id) };
      active = entry;
      entry.timer = setTimeout(() => stop(id), lifetimeMs); entry.timer.unref?.();
      owner.once('hide', entry.onStop); owner.once('closed', entry.onStop); owner.once('minimize', entry.onStop);
      const contents = child.webContents, session = contents.session;
      const current = () => active === entry && valid() && !child.isDestroyed() && contents.mainFrame.url === localURL;
      const allowedURLs = new Set(['screen-capture.html','screen-capture-view.js','screen-capture.css'].map(name => pathToFileURL(path.join(__dirname,name)).href));
      session.webRequest.onBeforeRequest((details, callback) => callback({ cancel: !allowedURLs.has(details.url) }));
      contents.setWindowOpenHandler(() => ({ action: 'deny' }));
      contents.on('will-navigate', (event, url) => { if (url !== localURL) event.preventDefault(); });
      contents.on('will-attach-webview', event => event.preventDefault());
      contents.on('render-process-gone', entry.onStop);
      child.on('closed', entry.onStop);
      child.on('hide', entry.onStop); child.on('minimize', entry.onStop);
      session.setPermissionCheckHandler(() => false);
      // Only packaged, isolated capture code receives this permission. The main
      // UI always denies it, including legacy getUserMedia desktop constraints.
      session.setPermissionRequestHandler((sender, permission, callback, details) => callback(Boolean(
        current() && sender === contents && permission === 'display-capture' && details.isMainFrame === true &&
        details.requestingUrl === localURL && Array.isArray(details.mediaTypes) &&
        details.mediaTypes.length === 1 && details.mediaTypes[0] === 'video')));
      let granted = false;
      session.setDisplayMediaRequestHandler(async (request, callback) => {
        let called = false;
        const finish = value => { if (called) return; called = true; try { callback(value); } catch {} };
        if (granted || !current() || request.frame !== contents.mainFrame || request.userGesture !== true ||
            request.videoRequested !== true || request.audioRequested !== false) return finish(null);
        granted = true;
        try {
          const sources = await desktopCapturer.getSources({ types: ['screen','window'], thumbnailSize: { width: 0, height: 0 }, fetchWindowIcons: false });
          const source = sources.find(item => item.id === selected.id);
          finish(current() && source ? { video: source } : null);
        } catch { finish(null); }
      }, { useSystemPicker: false });
      await child.loadFile(localPath);
      if (!current()) throw new Error('屏幕预览已过期。');
      child.show();
      return { capture_id: id, state: 'awaiting_user', source_label: String(selected.name || '所选内容').slice(0,140), processing: 'local' };
    } catch (error) { if (active) stop(active.id); throw error; }
    finally { starting = false; }
  }
  async function frame(id) {
    if (!active || active.id !== id) return { capture_id: id, state: 'stopped' };
    const entry = active;
    if (entry.inflight || now()-entry.lastFrame < 500) throw new Error('预览帧请求过快。');
    entry.inflight = true; entry.lastFrame = now();
    try {
      const value = await entry.window.webContents.executeJavaScript('window.captureFrame()');
      if (active !== entry) return { capture_id: id, state: 'stopped' };
      if (!value || !['awaiting_user','active','failed','stopped'].includes(value.state)) throw new Error('无效预览状态。');
      if (value.state !== 'active') return { capture_id: id, state: value.state };
      if (typeof value.image_base64 !== 'string' || value.image_base64.length > 2_000_000 ||
          !/^[A-Za-z0-9+/=]+$/.test(value.image_base64) || !Number.isSafeInteger(value.width) || !Number.isSafeInteger(value.height) ||
          value.width < 1 || value.height < 1 || value.width > 1600 || value.height > 900) throw new Error('无效预览帧。');
      return { capture_id: id, state: 'active', image_base64: value.image_base64,
        mime_type: 'image/jpeg', width: value.width, height: value.height, captured_at_ms: now(), processing: 'local', retained: false };
    } finally { entry.inflight = false; }
  }
  return { start, frame, stop, stopAll };
}

module.exports = { createScreenCaptureManager, chooseSource };
