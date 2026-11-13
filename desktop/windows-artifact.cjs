'use strict';
const fs = require('node:fs');
// Recognize Windows x64 PE artifacts without executing them on the build host.
function assertWindowsX64PE(file) {
  const fd = fs.openSync(file, 'r');
  try {
    const header = Buffer.alloc(64); if (fs.readSync(fd, header, 0, 64, 0) !== 64 || header.toString('ascii',0,2) !== 'MZ') throw new Error('Missing DOS/PE header: '+file);
    const offset=header.readUInt32LE(60);if(offset<64||offset>16*1024*1024)throw new Error('Invalid PE offset: '+file);
    const pe=Buffer.alloc(26);if(fs.readSync(fd,pe,0,26,offset)!==26||pe.toString('binary',0,4)!=='PE\0\0'||pe.readUInt16LE(4)!==0x8664||pe.readUInt16LE(24)!==0x20b)throw new Error('Expected Windows x64 PE32+ artifact: '+file);
  } finally { fs.closeSync(fd); }
}
module.exports={assertWindowsX64PE};
