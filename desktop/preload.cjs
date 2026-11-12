'use strict';
const { contextBridge, ipcRenderer } = require('electron');
const call = (name, value) => ipcRenderer.invoke('companion:desktop', name, value);
contextBridge.exposeInMainWorld('companionDesktop', Object.freeze({
  getState: () => call('get-state'),
  setExpanded: value => call('set-expanded', value),
  setClickThrough: value => call('set-click-through', value),
  hide: () => call('hide'), restore: () => call('restore'), quit: () => call('quit'),
  startScreenPreview: () => {
    // This runs in the isolated preload world, not a renderer-supplied boolean.
    if (!navigator.userActivation.isActive) return Promise.reject(new Error('请点击屏幕预览按钮。'));
    return ipcRenderer.invoke('companion:screen-preview', 'start');
  },
  getScreenPreviewFrame: captureId => ipcRenderer.invoke('companion:screen-preview', 'frame', captureId),
  stopScreenPreview: captureId => ipcRenderer.invoke('companion:screen-preview', 'stop', captureId),
  getDisplays: () => ipcRenderer.invoke('companion:display-output', 'list'),
  setDisplayOutput: id => {
    if (!navigator.userActivation.isActive) return Promise.reject(new Error('请点击选择显示器。'));
    return ipcRenderer.invoke('companion:display-output', 'select', id);
  },
  restoreDisplayOutput: () => ipcRenderer.invoke('companion:display-output', 'restore'),
  onState: callback => {
    if (typeof callback !== 'function') throw new TypeError('Expected a callback');
    const listener = (_event, value) => callback(value);
    ipcRenderer.on('companion:desktop-state', listener);
    return () => ipcRenderer.removeListener('companion:desktop-state', listener);
  },
}));
