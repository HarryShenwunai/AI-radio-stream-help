'use strict';
const { URL } = require('node:url');
const LOOPBACK = new Set(['127.0.0.1', 'localhost']);
function normalizeBackendURL(value) {
  if (typeof value !== 'string') throw new TypeError('Backend URL must be a string');
  const parsed = new URL(value);
  if (parsed.protocol !== 'http:' || !LOOPBACK.has(parsed.hostname) || !parsed.port ||
      parsed.username || parsed.password || parsed.search || parsed.hash ||
      (parsed.pathname !== '/' && parsed.pathname !== '')) {
    throw new Error('Only an explicit HTTP loopback origin is supported');
  }
  return parsed.origin + '/';
}
function trustedNavigation(value, base) {
  try {
    const url = new URL(value), backend = new URL(base);
    return url.origin === backend.origin && (url.pathname === '/' || url.pathname === '/index.html');
  } catch { return false; }
}
function validateCommand(command, value) {
  if (command === 'set-expanded' || command === 'set-click-through') {
    if (typeof value !== 'boolean') throw new TypeError('Expected a boolean');
    return value;
  }
  if (['get-state', 'hide', 'restore', 'quit'].includes(command)) {
    if (value !== undefined && value !== null) throw new TypeError('This action takes no payload');
    return undefined;
  }
  throw new Error('Unsupported desktop command');
}
function compactBounds(workArea) {
  const width = Math.min(330, workArea.width), height = Math.min(470, workArea.height);
  return { width, height, x: workArea.x + workArea.width - width - Math.min(24, workArea.width - width),
    y: workArea.y + workArea.height - height - Math.min(24, workArea.height - height) };
}
function expandedBounds(workArea) {
  const width = Math.min(1120, workArea.width), height = Math.min(850, workArea.height);
  return { width, height, x: workArea.x + Math.floor((workArea.width - width) / 2),
    y: workArea.y + Math.floor((workArea.height - height) / 2) };
}
module.exports = { normalizeBackendURL, trustedNavigation, validateCommand, compactBounds, expandedBounds };
