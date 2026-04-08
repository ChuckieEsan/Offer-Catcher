import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // API 代理配置：将 /api 请求转发到后端 FastAPI
  // 这样前端请求同一域名，无需处理跨域
  async rewrites() {
    const apiUrl = process.env.BACKEND_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
      // 健康检查端点
      {
        source: "/health",
        destination: `${apiUrl}/health`,
      },
    ];
  },
};

export default nextConfig;
