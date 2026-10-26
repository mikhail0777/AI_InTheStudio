module.exports = {
  packagerConfig: {
    name: 'LotTrace',
    executableName: 'LotTrace',
    asar: true,
    extraResource: [
      'dist',
      '../dist/lottrace-backend',
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
