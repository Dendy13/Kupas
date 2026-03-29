/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '*.kemdikbud.go.id' },
      { protocol: 'https', hostname: '*.kemdikdasmen.go.id' },
      { protocol: 'https', hostname: '*.cloudapp.web.id' },
      { protocol: 'https', hostname: 'kupas.dendyfajark.page' },
    ],
  },
}

export default nextConfig
