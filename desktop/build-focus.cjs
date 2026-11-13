'use strict';
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
if (process.platform !== 'linux') throw new Error('X11 helper is Linux only');
const include = process.env.COMPANION_X11_INCLUDE;
const args = ['-O2', '-Wall', '-Wextra', '-Werror', ...(include ? ['-I', include] : []),
  path.join(__dirname, 'focus-x11.c'), '-Wl,-z,relro,-z,now', '-l:libX11.so.6', '-o', path.join(__dirname, 'focus-x11')];
const result = spawnSync(process.env.CC || 'cc', args, { stdio: 'inherit' });
if (result.status !== 0) throw new Error('Install X11 development headers or set COMPANION_X11_INCLUDE before building');
fs.chmodSync(path.join(__dirname, 'focus-x11'), 0o755);
