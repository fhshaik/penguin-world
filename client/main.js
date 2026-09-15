const { app, BrowserWindow } = require('electron');
const path = require('path');
const gameHome = 'http://play.localhost:8088';
const tradeHome = 'http://trade.localhost:8088';
app.commandLine.appendSwitch('ppapi-flash-path', path.join(__dirname, 'pepflashplayer.dll'));
app.commandLine.appendSwitch('ppapi-flash-version', '31.0.0.122');
app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 1280, height: 900, title: 'Penguin World', autoHideMenuBar: true,
    webPreferences: { plugins: true, nodeIntegration: false, contextIsolation: true } });
  let tradeWindow = null;
  const openTrade = sourceUrl => {
    const request = sourceUrl ? new URL(sourceUrl) : null;
    const target = request?.searchParams.get('target');
    const name = request?.searchParams.get('name');
    const tradeUrl = new URL(tradeHome);
    if (target) tradeUrl.searchParams.set('target', target);
    if (name) tradeUrl.searchParams.set('name', name);
    if (tradeWindow && !tradeWindow.isDestroyed()) {
      if (target) tradeWindow.loadURL(tradeUrl.toString());
      tradeWindow.show();
      tradeWindow.focus();
      return;
    }
    tradeWindow = new BrowserWindow({ width: 1160, height: 820, minWidth: 880, minHeight: 680,
      title: 'Penguin Trading Post', autoHideMenuBar: true, parent: win,
      webPreferences: { nodeIntegration: false, contextIsolation: true } });
    tradeWindow.on('closed', () => { tradeWindow = null; });
    tradeWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    tradeWindow.webContents.on('will-navigate', (event, url) => {
      if (new URL(url).origin !== tradeHome) event.preventDefault();
    });
    tradeWindow.loadURL(tradeUrl.toString());
  };
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('penguin-trade://')) openTrade(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (url.startsWith('penguin-trade://')) {
      event.preventDefault();
      openTrade(url);
    } else if (new URL(url).origin !== gameHome) {
      event.preventDefault();
    }
  });
  win.webContents.on('before-input-event', (_event, input) => {
    if (input.type === 'keyDown' && input.key === 'F8') openTrade();
  });
  win.loadURL(gameHome + '/#/login');
});
app.on('window-all-closed', () => app.quit());
