const fs = require('fs');
fs.writeFileSync('node_modules/electron/path.txt', 'electron.exe');
console.log('path.txt written: [' + fs.readFileSync('node_modules/electron/path.txt') + ']');
