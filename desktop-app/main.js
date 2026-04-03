/**
 * Magic Desktop — native window for the local Magic API.
 * Starts uvicorn only if /health is unreachable; shuts down only the server we started.
 */
const { app, BrowserWindow, shell, dialog, systemPreferences, session } = require("electron");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");

const MAGIC_ROOT = path.resolve(__dirname, "..");
const DEFAULT_PORT = Number(process.env.MAGIC_PORT || "8787");
const APP_ICON = path.join(MAGIC_ROOT, "Magic.app", "Contents", "Resources", "Magic.icns");
const DOCK_ICON = path.join(MAGIC_ROOT, "app", "static", "magic-icon-256.png");

let serverProc = null;
/** True only if this process spawned uvicorn (do not kill an API started elsewhere). */
let serverStartedByUs = false;
let serverErrorLog = "";
let mainWindow = null;
let activePort = DEFAULT_PORT;

function baseUrl() {
  return `http://127.0.0.1:${activePort}`;
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
  process.exit(0);
}

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  }
});

function pythonBin() {
  const venv = path.join(MAGIC_ROOT, ".venv", "bin", "python3");
  const venvPy = path.join(MAGIC_ROOT, ".venv", "bin", "python");
  if (fs.existsSync(venv)) return venv;
  if (fs.existsSync(venvPy)) return venvPy;
  return "python3";
}

function startServer() {
  if (serverProc) return;
  const py = pythonBin();
  const port = String(activePort);
  const args = [
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    port,
  ];
  serverProc = spawn(py, args, {
    cwd: MAGIC_ROOT,
    env: { ...process.env, PYTHONPATH: MAGIC_ROOT, MAGIC_PORT: port },
    stdio: ["ignore", "pipe", "pipe"],
  });
  serverStartedByUs = true;
  serverErrorLog = "";
  serverProc.stdout?.on("data", (d) => { console.log(String(d)); });
  serverProc.stderr?.on("data", (d) => {
    serverErrorLog += String(d);
    if (serverErrorLog.length > 3000) serverErrorLog = serverErrorLog.slice(-3000);
    console.error(String(d));
  });
  serverProc.on("exit", (code) => {
    console.log("Magic server exited", code);
    serverStartedByUs = false;
  });
}

function killServerIfWeStarted() {
  if (!serverStartedByUs || !serverProc || serverProc.killed) return;
  try {
    serverProc.kill("SIGTERM");
  } catch {
    /* ignore */
  }
  serverProc = null;
  serverStartedByUs = false;
}

function request(url, timeoutMs = 4000) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => resolve({ statusCode: res.statusCode, headers: res.headers, body }));
    });
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error("request timeout"));
    });
    req.on("error", reject);
  });
}

async function probeServer(port) {
  const base = `http://127.0.0.1:${port}`;
  try {
    const health = await request(`${base}/health`, 2500);
    if (health.statusCode !== 200) return false;
    const parsed = JSON.parse(health.body || "{}");
    if (parsed.status !== "ok") return false;

    const root = await request(`${base}/`, 2500);
    const body = root.body || "";
    const type = String(root.headers["content-type"] || "");
    const htmlOk =
      root.statusCode === 200 &&
      type.includes("text/html") &&
      /<title>[^<]*Magic[^<]*<\/title>/i.test(body);
    const hasComposer =
      body.includes('id="cmd"') ||
      body.includes('id="chatInput"') ||
      body.includes("textarea") ||
      body.includes("data-magic");
    return htmlOk && hasComposer;
  } catch {
    return false;
  }
}

function isPortAvailable(port) {
  return new Promise((resolve) => {
    const tester = net.createServer();
    tester.once("error", () => resolve(false));
    tester.once("listening", () => {
      tester.close(() => resolve(true));
    });
    tester.listen(port, "127.0.0.1");
  });
}

async function findLaunchPort() {
  if (await isPortAvailable(DEFAULT_PORT)) return DEFAULT_PORT;
  for (let port = DEFAULT_PORT + 1; port <= DEFAULT_PORT + 20; port += 1) {
    if (await isPortAvailable(port)) return port;
  }
  throw new Error("Could not find a free local port for Magic.");
}

function waitForHealth(timeoutMs = 120000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = async () => {
      if (serverStartedByUs && serverProc && serverProc.exitCode !== null) {
        reject(new Error(`Backend service stopped unexpectedly (code ${serverProc.exitCode}).\n\nLogs:\n${serverErrorLog.trim().slice(-600)}`));
        return;
      }
      if (Date.now() - start > timeoutMs) {
        reject(new Error("Timed out waiting for Magic API to start."));
        return;
      }
      if (await probeServer(activePort)) {
        resolve(true);
        return;
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

async function ensureServer() {
  if (await probeServer(activePort)) {
    serverStartedByUs = false;
    return;
  }

  activePort = await findLaunchPort();
  startServer();
  await waitForHealth();
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 920,
    minWidth: 980,
    minHeight: 700,
    title: "Magic",
    backgroundColor: "#050508",
    vibrancy: process.platform === "darwin" ? "under-window" : undefined,
    visualEffectState: "active",
    show: false,
    icon: fs.existsSync(APP_ICON) ? APP_ICON : undefined,
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : undefined,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      spellcheck: true,
    },
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());

  let loadRetries = 0;
  const load = () => {
    mainWindow.loadURL(`${baseUrl()}/`);
  };

  mainWindow.webContents.on("did-finish-load", () => {
    loadRetries = 0;
  });

  mainWindow.webContents.on("did-fail-load", (_e, code, _desc, url) => {
    if (!url.startsWith(baseUrl()) || code === -3) return;
    if (loadRetries >= 5) {
      mainWindow.loadURL(
        `data:text/html,${encodeURIComponent(`
          <html>
            <body style="margin:0;background:#0c0a14;color:#f4f2ff;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;padding:32px">
              <h1 style="margin-top:0">Magic could not load its interface</h1>
              <p>The backend started, but the UI page did not load correctly.</p>
              <p>Try reopening Magic. If it still fails, run the app from:</p>
              <pre style="padding:16px;background:#1b1e27;border-radius:12px;white-space:pre-wrap">${MAGIC_ROOT}</pre>
              <p>Expected URL: ${baseUrl()}/</p>
            </body>
          </html>
        `)}`,
      );
      return;
    }
    loadRetries += 1;
    setTimeout(load, 600);
  });

  load();

  mainWindow.setMenuBarVisibility(false);
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(async () => {
  try {
    await ensureServer();
  } catch (e) {
    console.error(e);
    dialog.showErrorBox(
      "Magic is having trouble starting",
      "Magic's background service couldn't start. This usually means a missing dependency or API key.\n\n" +
      "1. Open Terminal in the Magic folder.\n" +
      "2. Run: source .venv/bin/activate && pip install -r requirements.txt\n" +
      "3. Check that your .env file has a valid GOOGLE_API_KEY.\n\n" +
      `Details: ${e.message.split('\n')[0]}`
    );
    app.quit();
    return;
  }
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    if (permission === "media" || permission === "microphone") {
      callback(true);
      return;
    }
    callback(false);
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => permission === "media" || permission === "microphone");
  if (process.platform === "darwin") {
    try {
      const access = systemPreferences.getMediaAccessStatus("microphone");
      if (access !== "granted") {
        systemPreferences.askForMediaAccess("microphone").catch(() => { });
      }
    } catch {
      /* ignore */
    }
  }
  if (process.platform === "darwin" && app.dock && fs.existsSync(DOCK_ICON)) {
    app.dock.setIcon(DOCK_ICON);
  }
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    killServerIfWeStarted();
    app.quit();
  }
});

app.on("before-quit", () => {
  killServerIfWeStarted();
});
