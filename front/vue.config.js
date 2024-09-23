module.exports = {
    // 选项会传递给 webpack-dev-server，在开发环境中使用
    devServer: {
      // 设置前端应用在本地开发时的默认端口
      port: 8080,
      // 只用于本地开发时的代理，生产环境下由 Nginx 处理
      proxy: {
        "/api/go": {
          target: "http://localhost:3001", // Go 服务地址
          changeOrigin: true,
          pathRewrite: { "^/api/go": "" }, // 移除 /api/go 前缀
          timeout: 5000, // 设置为5秒
          onProxyReq: function (proxyReq, req, res) {
            proxyReq.setHeader("Connection", "keep-alive");
          },
        },
        "/api/fastapi": {
          target: "http://localhost:8006", // FastAPI 服务地址
          changeOrigin: true,
          pathRewrite: { "^/api/fastapi": "" },
          timeout: 5000, // 设置为5秒
          onProxyReq: function (proxyReq, req, res) {
            proxyReq.setHeader("Connection", "keep-alive");
          },
        },
        "/api/flask": {
          target: "http://localhost:8005", // Flask 服务地址
          changeOrigin: true,
          pathRewrite: { "^/api/flask": "" },
          timeout: 5000, // 设置为5秒
          onProxyReq: function (proxyReq, req, res) {
            proxyReq.setHeader("Connection", "keep-alive");
          },
        },
      },
    },
  
    // 生产环境下的配置
    outputDir: "dist", // 这是 Vue build 后的默认输出目录
    publicPath: "/", // 确保资源从根路径加载
  };
  