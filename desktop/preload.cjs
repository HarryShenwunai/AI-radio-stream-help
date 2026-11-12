'use strict';
const { contextBridge, ipcRenderer } = require('electron');
const call = (name, value) => ipcRenderer.invoke('companion:desktop', name, value);
contextBridge.exposeInMainWorld('companionDesktop', Object.freeze({
  getState: () => call('get-state'),
  setExpanded: value => call('set-expanded', value),
  setClickThrough: value => call('set-click-through', value),
  hide: () => call('hide'), restore: () => call('restore'), quit: () => call('quit'),
  onState: callback => {
    if (typeof callback !== 'function') throw new TypeError('Expected a callback');
    const listener = (_event, value) => callback(value);
    ipcRenderer.on('companion:desktop-state', listener);
    return () => ipcRenderer.removeListener('companion:desktop-state', listener);
  },
}));
