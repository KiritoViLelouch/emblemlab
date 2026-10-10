const exporting = process.env.STATIC_EXPORT === 'true';
if (exporting && process.env.NEXT_PUBLIC_API_URL !== 'same-origin') {
  const api = new URL(process.env.NEXT_PUBLIC_API_URL || '');
  if (api.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(api.hostname)) {
    throw new Error('Static export requires an HTTPS NEXT_PUBLIC_API_URL');
  }
}
const config = {
  ...(exporting ? {output: 'export', trailingSlash: true} : {}),
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || '',
  images: {unoptimized: true},
  // Write Pages artifacts to a separate, explicitly uploaded directory.
  distDir: exporting ? '.next-export' : '.next',
};

export default config;
