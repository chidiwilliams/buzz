// extract_electron.js — manually extract the cached Electron zip
const extract = require('extract-zip');
const path = require('path');
const fs = require('fs');

const zipPath = path.join(
  process.env.LOCALAPPDATA,
  'electron', 'Cache',
  'bc80a13ebe4734629db853b3fc870b18ba9e388b795710fdbbd075694e548d03',
  'electron-v42.3.0-win32-x64.zip'
);
const distPath = path.join(__dirname, 'node_modules', 'electron', 'dist');
const electronPkg = path.join(__dirname, 'node_modules', 'electron');

console.log('Extracting:', zipPath);
console.log('To:', distPath);

extract(zipPath, { dir: distPath }).then(() => {
  fs.writeFileSync(path.join(electronPkg, 'path.txt'), 'electron.exe');
  console.log('Done! path.txt written.');
}).catch(err => {
  console.error('Extraction failed:', err);
  process.exit(1);
});
