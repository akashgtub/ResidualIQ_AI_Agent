const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const downloadDir = path.resolve('scratch/downloads');

async function testAll() {
  fs.readdirSync(downloadDir).forEach((file) => fs.unlinkSync(path.join(downloadDir, file)));

  const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
    '--headless=new',
    '--remote-debugging-port=9226',
    '--disable-gpu',
    'http://localhost:8080/index.html'
  ]);

  await new Promise((r) => setTimeout(r, 2000));
  const res = await fetch('http://localhost:9226/json');
  const pages = await res.json();
  const page = pages.find((p) => p.url.includes('localhost:8080'));
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
      console.log('CONSOLE:', d.params.type, d.params.args.map((a) => a.value || JSON.stringify(a)).join(' '));
    }
    if (d.method === 'Runtime.exceptionThrown') {
      console.log('PAGE EXCEPTION:', JSON.stringify(d.params.exceptionDetails));
    }
  });

  const evalCode = (code) =>
    send('Runtime.evaluate', {
      expression: code,
      returnByValue: true
    }).then((r) => r.result ? r.result.value : r);

  console.log('Waiting for window data to be fully loaded...');
  let loaded = false;
  for (let i = 0; i < 50; i++) {
    const check = await evalCode(`(() => {
      const d = window.RESIDUALQ_DATA || window.GHOST_DATA;
      return d && d.cases && d.cases.length === 518;
    })()`);
    if (check) {
      loaded = true;
      break;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  console.log('Data loaded ready state:', loaded);

  console.log('\n--- EXPORT 1: Full Submission All (518 cases) ---');
  const res1 = await evalCode(`(() => {
    try {
      document.getElementById('export-submission-all-btn').click();
      return 'CLICKED 1 OK';
    } catch (e) {
      return 'ERR: ' + e.stack;
    }
  })()`);
  console.log('Export 1 eval:', res1);
  await new Promise((r) => setTimeout(r, 4000));
  console.log('Downloads after Export 1:', fs.readdirSync(downloadDir));

  console.log('\n--- EXPORT 2: Filtered Submission (INCOMPLETE cases) ---');
  const res2 = await evalCode(`(() => {
    try {
      document.querySelector('.filter-chip[data-status="INCOMPLETE"]').click();
      document.getElementById('export-submission-filtered-btn').click();
      return 'CLICKED 2 OK';
    } catch (e) {
      return 'ERR: ' + e.stack;
    }
  })()`);
  console.log('Export 2 eval:', res2);
  await new Promise((r) => setTimeout(r, 4000));
  console.log('Downloads after Export 2:', fs.readdirSync(downloadDir));

  console.log('\n--- EXPORT 3: Detailed Report All (518 cases) ---');
  const res3 = await evalCode(`(() => {
    try {
      document.querySelector('.filter-chip[data-status="ALL"]').click();
      document.getElementById('export-detailed-all-btn').click();
      return 'CLICKED 3 OK';
    } catch (e) {
      return 'ERR: ' + e.stack;
    }
  })()`);
  console.log('Export 3 eval:', res3);
  await new Promise((r) => setTimeout(r, 4000));
  console.log('Downloads after Export 3:', fs.readdirSync(downloadDir));

  console.log('\n--- EXPORT 4: Detailed Report Filtered (INCOMPLETE cases) ---');
  const res4 = await evalCode(`(() => {
    try {
      document.querySelector('.filter-chip[data-status="INCOMPLETE"]').click();
      document.getElementById('export-detailed-filtered-btn').click();
      return 'CLICKED 4 OK';
    } catch (e) {
      return 'ERR: ' + e.stack;
    }
  })()`);
  console.log('Export 4 eval:', res4);
  await new Promise((r) => setTimeout(r, 4000));
  console.log('Downloads after Export 4:', fs.readdirSync(downloadDir));

  console.log('\n--- FINAL VERIFICATION OF DOWNLOADED FILES ---');
  const allFiles = fs.readdirSync(downloadDir);
  for (const f of allFiles) {
    const stat = fs.statSync(path.join(downloadDir, f));
    console.log(`- ${f}: ${stat.size} bytes`);
  }

  chrome.kill();
  process.exit(0);
}

testAll().catch((e) => {
  console.error(e);
  process.exit(1);
});
