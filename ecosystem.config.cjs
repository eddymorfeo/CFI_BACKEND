module.exports = {
  apps: [
    {
      name: "cfi-backend-prod",
      cwd: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_BACKEND",

      script: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_BACKEND/venv/Scripts/pythonw.exe",
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8000",

      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 5,
      restart_delay: 5000,
      windowsHide: true,

      out_file: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_BACKEND/logs/backend-out.log",
      error_file: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_BACKEND/logs/backend-error.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",

      env: {
        APP_ENV: "production",
        APP_HOST: "0.0.0.0",
        APP_PORT: "8000",
        POSTGRES_DB: "CFI"
      }
    },
    {
      name: "cfi-frontend-prod",
      cwd: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_FRONTEND",

      script: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_FRONTEND/node_modules/vite/bin/vite.js",
      args: [
        "preview",
        "--host",
        "0.0.0.0",
        "--port",
        "5173",
        "--strictPort"
      ],

      exec_mode: "fork",
      interpreter: "C:/Program Files/nodejs/node.exe",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 5,
      restart_delay: 5000,
      windowsHide: true,

      out_file: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_BACKEND/logs/frontend-out.log",
      error_file: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_BACKEND/logs/frontend-error.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",

      env: {
        NODE_ENV: "production"
      }
    }
  ]
};
