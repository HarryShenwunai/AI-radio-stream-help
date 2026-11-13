'use strict';
// Native-only harness: real Electron/Blink, native dialog and source picker.
// Synthetic camera is explicitly enabled by the invoking test, never the app.
const { app, BrowserWindow, dialog, desktopCapturer, Menu } = require('electron');
const { installMediaPermissions } = require('../media-policy.cjs');
const { chooseSource } = require('../screen-capture.cjs');
const origin = process.argv.find(value => value.startsWith('--fixture-origin=')).slice(17);
let owner;
app.whenReady().then(async () => {
  owner = new BrowserWindow({ width: 900, height: 700, webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false } });
  const session = owner.webContents.session;
  const permissionSetter = session.setPermissionRequestHandler.bind(session);
  session.setPermissionRequestHandler = handler => permissionSetter((contents, permission, callback, details) => {
    console.log('permission-request', JSON.stringify({ permission, main: details.isMainFrame, types: details.mediaTypes }));
    if (process.argv.includes('--investigate-display-preflight') && permission === 'display-capture') return callback(true);
    return handler(contents, permission, value => { console.log('permission-result', permission, value); callback(value); }, details);
  });
  const displaySetter = session.setDisplayMediaRequestHandler.bind(session);
  session.setDisplayMediaRequestHandler = (handler, options) => displaySetter((request, callback) => {
    console.log('display-request', JSON.stringify({ main: request.frame === owner.webContents.mainFrame, gesture: request.userGesture, video: request.videoRequested, audio: request.audioRequested }));
    if (process.argv.includes('--investigate-display-preflight')) {
      void chooseSource({ owner, desktopCapturer, Menu, valid: () => !owner.isDestroyed() }).then(source => callback(source ? { video: source } : null));
      return;
    }
    return handler(request, value => { console.log('display-result', Boolean(value), Object.keys(value || {})); callback(value); });
  }, options);
  installMediaPermissions({ getWindow: () => owner, getBackendURL: () => origin, dialog, desktopCapturer, Menu });
  owner.on('closed', () => app.quit()); await owner.loadURL(origin);
});
app.on('window-all-closed', () => app.quit());
