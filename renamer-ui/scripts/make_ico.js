// make_ico.js — convert a PNG to a minimal ICO file for Windows
// Uses only Node.js built-ins — no npm packages needed.
// Usage: node make_ico.js input.png output.ico
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const [,, src, dst] = process.argv;
if (!src || !dst) {
  console.error('Usage: node make_ico.js <input.png> <output.ico>');
  process.exit(1);
}

const pngBuf = fs.readFileSync(src);
const pngSize = pngBuf.length;

// ICO format: header (6) + one image entry (16) + PNG data
// Using PNG-in-ICO (valid since Vista): store the raw PNG in the ICO.
const header = Buffer.alloc(6);
header.writeUInt16LE(0, 0);      // reserved
header.writeUInt16LE(1, 2);      // type: 1 = ICO
header.writeUInt16LE(1, 4);      // image count

const entry = Buffer.alloc(16);
entry.writeUInt8(0, 0);          // width  0 = 256
entry.writeUInt8(0, 1);          // height 0 = 256
entry.writeUInt8(0, 2);          // colour palette
entry.writeUInt8(0, 3);          // reserved
entry.writeUInt16LE(1, 4);       // colour planes
entry.writeUInt16LE(32, 6);      // bits per pixel
entry.writeUInt32LE(pngSize, 8); // size of image data
entry.writeUInt32LE(22, 12);     // offset: 6 (header) + 16 (entry)

const ico = Buffer.concat([header, entry, pngBuf]);
fs.mkdirSync(path.dirname(dst), { recursive: true });
fs.writeFileSync(dst, ico);
console.log(`Written ${ico.length} bytes to ${dst}`);
