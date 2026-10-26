const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('lottraceDesktop', Object.freeze({
  importExistingData: () => ipcRenderer.invoke('lottrace:import-existing-data'),
  platform: process.platform,
}));
