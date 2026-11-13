'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { ownerRuntimePaths } = require('../owner-runtime-path.cjs');
test('owner path uses the exact Electron userData supplied by the host, without guessing APPDATA',()=>{
  const result=ownerRuntimePaths({userData:'/private/真实 用户',backendCwd:'/portable/resources',environment:{APPDATA:'/not-the-actual-electron-profile'}});
  assert.deepEqual(result,{schema_version:1,data_root:path.resolve('/private/真实 用户/profile-data'),live2d_runtime_root:path.resolve('/private/真实 用户/profile-data/live2d-runtime')});
});
test('relative overrides are resolved against the actual backend working directory',()=>{
  const result=ownerRuntimePaths({userData:'/ignored',backendCwd:'/portable/resources',environment:{COMPANION_DATA:'../private data',COMPANION_LIVE2D_RUNTIME:'../my licensed runtime'}});
  assert.equal(result.data_root,path.resolve('/portable/private data'));assert.equal(result.live2d_runtime_root,path.resolve('/portable/my licensed runtime'));
});
test('explicit data/runtime overrides do not leak other environment variables',()=>{
  const result=ownerRuntimePaths({userData:'/ignored',backendCwd:'/portable/resources',environment:{COMPANION_DATA:'/selected/data',COMPANION_LIVE2D_RUNTIME:'/selected/runtime',SECRET:'not exposed'}});
  assert.equal(result.data_root,path.resolve('/selected/data'));assert.equal(result.live2d_runtime_root,path.resolve('/selected/runtime'));
  assert.deepEqual(Object.keys(result).sort(),['data_root','live2d_runtime_root','schema_version']);
});
