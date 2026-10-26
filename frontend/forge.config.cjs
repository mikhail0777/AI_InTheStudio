const certificateFile = process.env.WINDOWS_CERTIFICATE_FILE;
const certificatePassword = process.env.WINDOWS_CERTIFICATE_PASSWORD;
if (Boolean(certificateFile) !== Boolean(certificatePassword)) {
  throw new Error('Set both WINDOWS_CERTIFICATE_FILE and WINDOWS_CERTIFICATE_PASSWORD, or neither.');
}
const windowsSign = certificateFile ? {
  certificateFile,
  certificatePassword,
  timestampServer: process.env.WINDOWS_TIMESTAMP_SERVER || 'http://timestamp.digicert.com',
  description: 'LotTrace dealership vehicle evidence application',
  continueOnError: false,
} : undefined;

module.exports = {
  packagerConfig: {
    name: 'LotTrace',
    executableName: 'LotTrace',
    asar: true,
    appVersion: require('./package.json').version,
    win32metadata: {CompanyName:'LotTrace',FileDescription:'LotTrace dealership vehicle evidence',ProductName:'LotTrace'},
    ...(windowsSign ? {windowsSign} : {}),
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
        ...(windowsSign ? {windowsSign,certificateFile,certificatePassword} : {}),
      },
    },
  ],
};
