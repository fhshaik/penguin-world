const { app, BrowserWindow } = require('electron');
const path = require('path');
const home = 'http://play.localhost:8088';
app.commandLine.appendSwitch('ppapi-flash-path', path.join(__dirname, 'pepflashplayer.dll'));
app.commandLine.appendSwitch('ppapi-flash-version', '31.0.0.122');
app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 1280, height: 900, title: 'Penguin World', autoHideMenuBar: true,
    webPreferences: { plugins: true, nodeIntegration: false, contextIsolation: true } });
  win.webContents.on('new-window', event => event.preventDefault());
  win.webContents.on('will-navigate', (event, url) => { if (new URL(url).origin !== home) event.preventDefault(); });
  win.loadURL(home + '/#/login');
});
app.on('window-all-closed', () => app.quit());
