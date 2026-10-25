const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const downloadDir = path.resolve('scratch/downloads');

async function test() {
  // Clear download dir
  fs.readdirSync(downloadDir).forEach((file) => fs.unlinkSync(path.join(downloadDir, file)));

  const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
    '--headless=new',
    '--remote-debugging-port=9224',
    '--disable-gpu',
    'http://localhost:8080/index.html'
  ]);

  await new Promise((r) => setTimeout(r, 2000));
  const res = await fetch('http://localhost:9224/json');
  const pages = await res.json();
  const page = pages.find((p) => p.url.includes('localhost:8080'));
  if (!page) throw new Error('No page found');

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 1;
  const send = (m, p = {}) =>
    new Promise((resolve) => {
      const cur = id++;
      const onm = (e) => {
        const d = JSON.parse(e.data);
        if (d.id === cur) {
          ws.removeEventListener('message', onm);
          resolve(d.result);
        }
      };
      ws.addEventListener('message', onm);
      ws.send(JSON.stringify({ id: cur, method: m, params: p }));
    });

  await new Promise((r) => (ws.onopen = r));
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: downloadDir });

  ws.addEventListener('message', (e) => {
    const d = JSON.parse(e.data);
    if (d.method === 'Runtime.consoleAPICalled') {
      console.log('CONSOLE:', d.params.type, d.params.args.map((a) => a.value || JSON.stringify(a)));
    }
    if (d.method === 'Runtime.exceptionThrown') {
      console.log('EXCEPTION:', JSON.stringify(d.params.exceptionDetails));
    }
  });

  console.log('Calling exportSubmissionAll directly via evaluate...');
  const ret = await send('Runtime.evaluate', {
    expression: `(() => {
      try {
        console.log('Cases in window:', (window.RESIDUALQ_DATA || window.GHOST_DATA).cases.length);
        const btn = document.getElementById('export-submission-all-btn');
        btn.click();
        return 'SUCCESS';
      } catch (e) {
        return 'ERROR: ' + e.stack;
      }
    })()`,
    returnByValue: true
  });
  console.log('Evaluate result:', ret);

  await new Promise((r) => setTimeout(r, 4000));
  console.log('Files in downloads:', fs.readdirSync(downloadDir));

  chrome.kill();
  process.exit(0);
}

test().catch((e) => {
  console.error(e);
  process.exit(1);
});
