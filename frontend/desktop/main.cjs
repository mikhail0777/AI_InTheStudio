const {app, BrowserWindow, dialog, session} = require('electron');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');

let backend = null;
let backendLog = null;
let mainWindow = null;

function reservePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

function waitForBackend(url, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const check = () => {
      const request = http.get(url, response => {
        response.resume();
        if (response.statusCode >= 200 && response.statusCode < 400) return resolve();
        retry();
      });
      request.setTimeout(1500, () => request.destroy());
      request.on('error', retry);
    };
    const retry = () => Date.now() >= deadline
      ? reject(new Error('The local LotTrace service did not become ready.'))
      : setTimeout(check, 350);
    check();
  });
}

function backendLaunch(port) {
  const userData = app.getPath('userData');
  const dataDir = path.join(userData, 'data');
  const logDir = path.join(userData, 'logs');
  fs.mkdirSync(dataDir, {recursive: true});
  fs.mkdirSync(logDir, {recursive: true});
  backendLog = fs.createWriteStream(path.join(logDir, 'backend.log'), {flags: 'a'});

  const packaged = app.isPackaged;
  const projectRoot = path.resolve(__dirname, '..', '..');
  const frontendDir = packaged
    ? path.join(process.resourcesPath, 'frontend')
    : path.join(projectRoot, 'frontend', 'dist');
  const executable = packaged
    ? path.join(process.resourcesPath, 'backend', 'lottrace-backend.exe')
    : (process.env.LOTTRACE_PYTHON || 'python');
  const args = packaged
    ? []
    : ['-m', 'uvicorn', 'app.main:app', '--app-dir', path.join(projectRoot, 'backend'), '--host', '127.0.0.1', '--port', String(port)];
  if (!fs.existsSync(frontendDir)) throw new Error(`Packaged frontend is missing: ${frontendDir}`);
  if (packaged && !fs.existsSync(executable)) throw new Error(`Packaged backend is missing: ${executable}`);
  const developmentVehicleDir = path.join(projectRoot, 'datasets', 'extracted', 'training', 'vehicle_make_model_79_finetuned');
  const packagedVehicleDir = path.join(process.resourcesPath, 'models', 'vehicle-make-model');
  const vehicleDir = packaged ? packagedVehicleDir : developmentVehicleDir;
  const discoveredVehicleModel = path.join(vehicleDir, 'vehicle_attributes.pt2');
  const discoveredVehicleManifest = path.join(vehicleDir, 'labels.json');
  const vehicleEnvironment = (
    fs.existsSync(discoveredVehicleModel) && fs.existsSync(discoveredVehicleManifest)
  ) ? {
    LOTTRACE_VEHICLE_ATTRIBUTE_MODEL: process.env.LOTTRACE_VEHICLE_ATTRIBUTE_MODEL || discoveredVehicleModel,
    LOTTRACE_VEHICLE_ATTRIBUTE_MANIFEST: process.env.LOTTRACE_VEHICLE_ATTRIBUTE_MANIFEST || discoveredVehicleManifest,
  } : {};

  backend = spawn(executable, args, {
    cwd: packaged ? path.dirname(executable) : projectRoot,
    windowsHide: true,
    env: {
      ...process.env,
      AIEYE_DATA_DIR: dataDir,
      AIEYE_CORS_ORIGINS: `http://127.0.0.1:${port}`,
      LOTTRACE_BACKEND_HOST: '127.0.0.1',
      LOTTRACE_BACKEND_PORT: String(port),
      LOTTRACE_FRONTEND_DIR: frontendDir,
      LOTTRACE_DESKTOP: '1',
      PYTHONUNBUFFERED: '1',
      ...vehicleEnvironment,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  backend.stdout.pipe(backendLog);
  backend.stderr.pipe(backendLog);
  backend.on('exit', code => {
    backend = null;
    if (!app.isQuitting && code !== 0) {
      dialog.showErrorBox('LotTrace service stopped', `The local service exited unexpectedly. See ${backendLog.path}`);
    }
  });
}

function stopBackend() {
  if (backend) {
    backend.kill();
    backend = null;
  }
  if (backendLog) {
    backendLog.end();
    backendLog = null;
  }
}

function createWindow(origin) {
  mainWindow = new BrowserWindow({
    title: 'LotTrace',
    width: 1440,
    height: 920,
    minWidth: 1080,
    minHeight: 720,
    show: false,
    backgroundColor: '#f6f6f3',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      devTools: !app.isPackaged,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
  mainWindow.webContents.on('will-navigate', (event, target) => {
    if (!target.startsWith(origin)) event.preventDefault();
  });
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.loadURL(`${origin}/app/#/recording`);
}

async function start() {
  const port = await reservePort();
  const origin = `http://127.0.0.1:${port}`;
  backendLaunch(port);
  await waitForBackend(`${origin}/`);
  if (process.env.LOTTRACE_DESKTOP_SMOKE_TEST === '1') {
    await waitForBackend(`${origin}/app/`);
    app.quit();
    return;
  }
  createWindow(origin);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(() => {
    session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
    return start();
  }).catch(error => {
    dialog.showErrorBox('LotTrace could not start', `${error.message}\n\nLogs are stored under ${app.getPath('userData')}.`);
    app.exit(1);
  });
  app.on('before-quit', () => { app.isQuitting = true; stopBackend(); });
  app.on('window-all-closed', () => app.quit());
}
