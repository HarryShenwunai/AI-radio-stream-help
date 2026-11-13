'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { installMediaPermissions } = require('../media-policy.cjs');
const flush = () => new Promise(resolve => setImmediate(resolve));
function fixture(options = {}) {
  const base = 'http://127.0.0.1:8765/';
  const contents = new EventEmitter(); contents.mainFrame = { url: base }; contents.isDestroyed = () => false;
  const session = contents.session = {
    setPermissionCheckHandler(value) { this.check = value; },
    setPermissionRequestHandler(value) { this.permission = value; },
    setDisplayMediaRequestHandler(value) { this.display = value; },
  };
  const owner = new EventEmitter(); owner.webContents = contents; owner.isDestroyed = () => false;
  let current = owner, answer = { response: 1 }, sources = [{ id: 'screen:0:0', name: 'Display 1' }, { id: 'window:12:0', name: 'Study & notes' }];
  const calls = { dialogs: [], enumerations: [], menus: [], callbacks: [] };
  const dialog = { async showMessageBox(_window, value) { calls.dialogs.push(value); return typeof answer === 'function' ? answer() : answer; } };
  const desktopCapturer = { async getSources(value) { calls.enumerations.push(value); return typeof sources === 'function' ? sources() : sources; } };
  const Menu = { buildFromTemplate(template) {
    const menu = { template, closeCount: 0,
      popup(value) { this.options = value; }, closePopup() { this.closeCount++; },
      select(group = 2, index = 0) { this.template[group].submenu[index].click(); this.options.callback(); },
      cancel() { this.options.callback(); },
    }; calls.menus.push(menu); return menu;
  } };
  const policy = installMediaPermissions({ getWindow: () => current, getBackendURL: () => base, dialog, desktopCapturer, Menu, ...options });
  const details = { isMainFrame: true, requestingUrl: base, securityOrigin: base.slice(0, -1), mediaTypes: ['video'] };
  const request = { frame: contents.mainFrame, securityOrigin: base.slice(0, -1), userGesture: true, videoRequested: true, audioRequested: false };
  return { session, contents, owner, calls, policy, details, request,
    answer(value) { answer = value; }, sources(value) { sources = value; }, detach() { current = null; },
    permission(permission = 'media', override = {}, sender = contents) {
      return session.permission(sender, permission, value => calls.callbacks.push(value), { ...details, ...override });
    },
    display(override = {}) { return session.display({ ...request, ...override }, value => calls.callbacks.push(value)); },
  };
}
test('camera and microphone each require a new native decision; checks never reuse grants', async () => {
  const f = fixture();
  for (const types of [['audio'], ['video'], ['audio', 'video']]) await f.permission('media', { mediaTypes: types });
  assert.deepEqual(f.calls.callbacks, [true, true, true]); assert.equal(f.calls.dialogs.length, 3);
  assert.equal(f.session.check(f.contents, 'media', 'http://127.0.0.1:8765', f.details), false);
  f.answer({ response: 0 }); await f.permission(); assert.equal(f.calls.callbacks.at(-1), false);
});
test('foreign windows, origins, frames and unsupported permission scopes are rejected before prompting', async () => {
  const f = fixture();
  for (const [permission, details, sender] of [
    ['media', {}, {}], ['media', { isMainFrame: false }], ['media', { requestingUrl: 'https://evil.invalid/' }],
    ['media', { securityOrigin: 'http://127.0.0.1:9999' }], ['media', { mediaTypes: [] }],
    ['media', { mediaTypes: ['unknown'] }], ['media', { mediaTypes: ['audio', 'audio'] }], ['geolocation', {}],
  ]) await f.permission(permission, details, sender);
  assert.ok(f.calls.callbacks.every(value => value === false)); assert.equal(f.calls.dialogs.length, 0);
});
test('permission confirmation cannot outlive hiding, navigating, destroying or replacing the owner', async () => {
  for (const event of ['hide', 'navigation', 'closed', 'replacement']) {
    const f = fixture(); let finish;
    f.answer(() => new Promise(resolve => { finish = resolve; })); const pending = f.permission();
    if (event === 'navigation') f.contents.emit('did-start-navigation', {}, 'http://127.0.0.1:8765/', false, true);
    else if (event === 'replacement') f.detach(); else f.owner.emit(event);
    finish({ response: 1 }); await pending;
    assert.deepEqual(f.calls.callbacks, [false], event);
  }
});
test('parallel permission requests cannot create stacked dialogs or take over a pending request', async () => {
  const f = fixture(); let finish; f.answer(() => new Promise(resolve => { finish = resolve; }));
  const pending = f.permission(); await f.permission('media', { mediaTypes: ['audio'] });
  assert.deepEqual(f.calls.callbacks, [false]); assert.equal(f.calls.dialogs.length, 1);
  finish({ response: 1 }); await pending; assert.deepEqual(f.calls.callbacks, [false, true]);
});
test('screen sharing rejects absent gesture, audio, foreign origin/frame before enumerating', async () => {
  const f = fixture();
  for (const request of [{ userGesture: false }, { audioRequested: true }, { videoRequested: false },
    { securityOrigin: 'https://evil.invalid' }, { frame: { url: 'http://127.0.0.1:8765/' } }, { frame: null }]) await f.display(request);
  assert.deepEqual(f.calls.callbacks, Array(6).fill(null)); assert.equal(f.calls.enumerations.length, 0);
});
test('main UI display permission and display handler always deny legacy and standard desktop capture', async () => {
  const f = fixture();
  await f.permission('display-capture'); await f.permission('display-capture', { mediaTypes: ['audio','video'] });
  await f.display(); await f.display();
  assert.deepEqual(f.calls.callbacks, [false,false,null,null]);
  assert.equal(f.calls.enumerations.length,0); assert.equal(f.calls.menus.length,0);
});
test('timed-out media and display requests terminate once and ignore later approvals', async () => {
  const f = fixture({ timeoutMs: 5 }); let finish;
  f.answer(() => new Promise(resolve => { finish = resolve; })); const pending = f.permission();
  await new Promise(resolve => setTimeout(resolve, 15)); finish({ response: 1 }); await pending;
  assert.deepEqual(f.calls.callbacks, [false]);
  await f.display(); await new Promise(resolve => setTimeout(resolve, 15));
  assert.deepEqual(f.calls.callbacks, [false, null]);
});
