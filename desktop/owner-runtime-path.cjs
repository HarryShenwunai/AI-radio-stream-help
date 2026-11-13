'use strict';
const path = require('node:path');

function ownerRuntimePaths({ userData, backendCwd, environment = process.env }) {
  const data = path.resolve(backendCwd,environment.COMPANION_DATA || path.join(userData,'profile-data'));
  return { schema_version:1, data_root:data,
    live2d_runtime_root:path.resolve(backendCwd,environment.COMPANION_LIVE2D_RUNTIME || path.join(data,'live2d-runtime')) };
}
module.exports = { ownerRuntimePaths };
