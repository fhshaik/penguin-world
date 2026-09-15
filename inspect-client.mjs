import fs from 'node:fs/promises';
const tabs = await (await fetch('http://127.0.0.1:19222/json/list')).json();
const tab = tabs.find(t => t.url.startsWith('http://play.localhost:8088'));
if (!tab) throw new Error('Local client page not found');
const ws = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((resolve,reject) => { ws.onopen=resolve; ws.onerror=reject; });
let next=0; const waiting = new Map();
ws.onmessage = e => { const m=JSON.parse(e.data); if (m.id) { const p=waiting.get(m.id); waiting.delete(m.id); m.error?p.reject(m.error):p.resolve(m.result); } };
const call=(method,params={}) => new Promise((resolve,reject)=>{ const id=++next; waiting.set(id,{resolve,reject}); ws.send(JSON.stringify({id,method,params})); });
if (process.argv.includes('--reload')) await call('Runtime.evaluate',{expression: "location.hash='/login'"});
const expression = process.argv[2] || 'JSON.stringify({text:document.body.innerText,objects:Array.from(document.querySelectorAll("object,embed")).map(e=>e.outerHTML)})';
console.log(JSON.stringify(await call('Runtime.evaluate',{expression,returnByValue:true})));
if (process.argv.includes('--shot')) {
 await call('Page.bringToFront');
 const shot = await Promise.race([call('Page.captureScreenshot',{format:'png'}), new Promise((_,reject)=>setTimeout(()=>reject(new Error('Screenshot timed out')),10000))]);
 await fs.writeFile('client-check.png',Buffer.from(shot.data,'base64'));
}
ws.close();