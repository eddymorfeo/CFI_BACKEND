module.exports = {
  apps: [
    {
      name: "cfi-backend-prod",
      cwd: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_BACKEND",
      script: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_BACKEND/venv/Scripts/python.exe",
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8000",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      env: {
        APP_ENV: "production",
      },
    },
    {
      name: "cfi-frontend-prod",
      cwd: "C:/Users/etejeda/Desktop/Proyectos/CFI/CFI_FRONTEND",
      script: "npm.cmd",
      args: "start",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
