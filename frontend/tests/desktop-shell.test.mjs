import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const main=fs.readFileSync(new URL('../desktop/main.cjs',import.meta.url),'utf8');
const forge=fs.readFileSync(new URL('../forge.config.cjs',import.meta.url),'utf8');
const pkg=JSON.parse(fs.readFileSync(new URL('../package.json',import.meta.url),'utf8'));

test('desktop shell isolates the renderer and blocks navigation and permissions',()=>{
 assert.match(main,/contextIsolation:\s*true/);
 assert.match(main,/nodeIntegration:\s*false/);
 assert.match(main,/sandbox:\s*true/);
 assert.match(main,/webSecurity:\s*true/);
 assert.match(main,/setPermissionRequestHandler/);
 assert.match(main,/setWindowOpenHandler/);
 assert.match(main,/will-navigate/);
});

test('desktop shell owns a private backend and persistent application-data directory',()=>{
 assert.match(main,/127\.0\.0\.1/);
 assert.match(main,/app\.getPath\('userData'\)/);
 assert.match(main,/AIEYE_DATA_DIR/);
 assert.match(main,/LOTTRACE_FRONTEND_DIR/);
 assert.match(main,/LOTTRACE_VEHICLE_ATTRIBUTE_MODEL/);
 assert.match(main,/stopBackend/);
});

test('windows packaging includes the built frontend and packaged backend',()=>{
 assert.equal(pkg.main,'desktop/main.cjs');
 assert.ok(pkg.scripts['desktop:dev']);
 assert.ok(pkg.scripts['desktop:make']);
 assert.match(forge,/maker-squirrel/);
 assert.match(forge,/lottrace-backend/);
});
