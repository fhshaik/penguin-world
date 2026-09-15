const { app, BrowserView, BrowserWindow } = require('electron');
const path = require('path');
const gameHome = 'http://play.localhost:8088';
const tradeHome = 'http://trade.localhost:8088';
app.commandLine.appendSwitch('ppapi-flash-path', path.join(__dirname, 'pepflashplayer.dll'));
app.commandLine.appendSwitch('ppapi-flash-version', '31.0.0.122');
app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 1280, height: 900, title: 'Penguin World', autoHideMenuBar: true,
    webPreferences: { plugins: true, nodeIntegration: false, contextIsolation: true } });
  let tradeView = null;
  const sizeTradeView = () => {
    if (!tradeView) return;
    const [width, height] = win.getContentSize();
    const margin = width < 1000 ? 12 : 36;
    tradeView.setBounds({ x: margin, y: margin, width: width - margin * 2, height: height - margin * 2 });
  };
  const closeTrade = () => {
    if (!tradeView) return;
    win.removeBrowserView(tradeView);
    tradeView.webContents.destroy();
    tradeView = null;
    win.webContents.focus();
  };
  const openTrade = sourceUrl => {
    const request = sourceUrl ? new URL(sourceUrl) : null;
    const target = request?.searchParams.get('target');
    const name = request?.searchParams.get('name');
    const tradeUrl = new URL(tradeHome);
    if (target) tradeUrl.searchParams.set('target', target);
    if (name) tradeUrl.searchParams.set('name', name);
    if (tradeView) {
      if (target) tradeView.webContents.loadURL(tradeUrl.toString());
      tradeView.webContents.focus();
      return;
    }
    tradeView = new BrowserView({ webPreferences: { nodeIntegration: false, contextIsolation: true } });
    win.setBrowserView(tradeView);
    sizeTradeView();
    tradeView.setAutoResize({ width: true, height: true });
    tradeView.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    tradeView.webContents.on('will-navigate', (event, url) => {
      if (url === 'penguin-trade://close') {
        event.preventDefault();
        closeTrade();
      } else if (new URL(url).origin !== tradeHome) {
        event.preventDefault();
      }
    });
    tradeView.webContents.on('before-input-event', (_event, input) => {
      if (input.type === 'keyDown' && input.key === 'Escape') closeTrade();
    });
    tradeView.webContents.loadURL(tradeUrl.toString());
    tradeView.webContents.focus();
  };
  win.on('resize', sizeTradeView);
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
    if (input.type === 'keyDown' && input.key === 'F8') tradeView ? closeTrade() : openTrade();
  });
  win.loadURL(gameHome + '/#/login');
});
app.on('window-all-closed', () => app.quit());
