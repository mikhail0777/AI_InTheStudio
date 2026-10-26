export {};

declare global {
  interface Window {
    lottraceDesktop?: {
      importExistingData: () => Promise<{status:'cancelled'|'restarting'}>;
      platform: string;
    };
  }
}
