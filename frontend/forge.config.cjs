module.exports = {
  packagerConfig: {
    name: 'LotTrace',
    executableName: 'LotTrace',
    asar: true,
    extraResource: [
      {from: 'dist', to: 'frontend'},
      {from: '../dist/lottrace-backend', to: 'backend'},
    ],
  },
  makers: [
    {
      name: '@electron-forge/maker-squirrel',
      config: {
        name: 'LotTrace',
        authors: 'Mikhail Simanian',
        description: 'Local dealership vehicle arrival, departure, and evidence system',
        setupExe: 'LotTrace-Setup.exe',
      },
    },
  ],
};
