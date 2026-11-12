'use strict';
const { trustedNavigation } = require('./window-policy.cjs');

// Permissions are deliberately session-local and never inferred from a device
// preference. Every new capture needs a new native decision.
function installMediaPermissions({ getWindow, getBackendURL, dialog, desktopCapturer, Menu,
  timeoutMs = 60_000, now = Date.now }) {
  const owner = getWindow(), contents = owner.webContents, session = contents.session;
  let epoch = 0, pending = null;
  const originMatches = value => {
    try { return new URL(value).origin === new URL(getBackendURL()).origin; } catch { return false; }
  };
  function current(frame, ticket) {
    const live = getWindow();
    return live === owner && !owner.isDestroyed() && !contents.isDestroyed() &&
      frame === contents.mainFrame && ticket === epoch &&
      trustedNavigation(frame.url, getBackendURL());
  }
  function trustedRequest(sender, details) {
    return sender === contents && details?.isMainFrame === true &&
      trustedNavigation(details.requestingUrl, getBackendURL()) &&
      (!details.securityOrigin || originMatches(details.securityOrigin)) &&
      current(contents.mainFrame, epoch);
  }
  function invalidate() {
    epoch++;
    if (pending) pending.cancel();
  }
  owner.on('hide', invalidate); owner.on('closed', invalidate);
  contents.on('render-process-gone', invalidate);
  contents.on('did-start-navigation', (_event, _url, _inPlace, mainFrame) => { if (mainFrame) invalidate(); });
  // False makes Chromium request permission rather than reuse a previous grant.
  session.setPermissionCheckHandler(() => false);

  function transaction(callback) {
    if (pending) { callback(null); return null; }
    let done = false, menu = null;
    const ticket = epoch, frame = contents.mainFrame;
    const task = {
      ticket, frame, valid: () => !done && current(frame, ticket),
      setMenu(value) { menu = value; },
      finish(value) {
        if (done) return;
        done = true; clearTimeout(timer);
        if (pending === task) pending = null;
        if (menu) { try { menu.closePopup(owner); } catch {} }
        // Destroyed frames can throw in Electron callbacks; no retry or grant.
        try { callback(value); } catch {}
      },
      cancel() { task.finish(null); },
    };
    const timer = setTimeout(() => task.cancel(), timeoutMs); timer.unref?.();
    pending = task; return task;
  }

  session.setPermissionRequestHandler(async (sender, permission, callback, details) => {
    if (!trustedRequest(sender, details)) return callback(false);
    const types = details.mediaTypes;
    if (permission === 'display-capture') return callback(false);
    if (permission !== 'media' || !Array.isArray(types) || !types.length ||
        types.some(type => !['audio', 'video'].includes(type)) || new Set(types).size !== types.length) return callback(false);
    const task = transaction(value => callback(value === true));
    if (!task) return;
    const label = types.includes('video') ? (types.includes('audio') ? '摄像头和麦克风' : '摄像头') : '麦克风';
    try {
      const answer = await dialog.showMessageBox(owner, { type: 'question',
        buttons: ['取消', '允许这次使用'], defaultId: 0, cancelId: 0,
        message: `允许这次使用${label}？`, detail: '仅在主动开启的功能中采集。关闭预览或切换角色会停止。' });
      task.finish(task.valid() && answer.response === 1);
    } catch { task.cancel(); }
  });

  // Main UI cannot bypass source binding via legacy chromeMediaSource.
  session.setDisplayMediaRequestHandler((_request, callback) => callback(null));
  return { invalidate };
}

module.exports = { installMediaPermissions };
