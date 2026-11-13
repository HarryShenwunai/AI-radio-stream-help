'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {assertWindowsX64PE}=require('../windows-artifact.cjs');
test('Windows assembly rejects ELF, truncated files and x86 PE without executing artifacts',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'companion-pe-'));
 try {
  const file=path.join(dir,'artifact.exe'),data=Buffer.alloc(160);
  fs.writeFileSync(file,Buffer.from('\x7fELF'));assert.throws(()=>assertWindowsX64PE(file));
  data.write('MZ');data.writeUInt32LE(80,60);data.write('PE\0\0',80,'binary');data.writeUInt16LE(0x8664,84);data.writeUInt16LE(0x20b,104);fs.writeFileSync(file,data);
  assert.doesNotThrow(()=>assertWindowsX64PE(file));
  data.writeUInt16LE(0x14c,84);fs.writeFileSync(file,data);assert.throws(()=>assertWindowsX64PE(file));
 } finally { fs.rmSync(dir,{recursive:true,force:true}); }
});
