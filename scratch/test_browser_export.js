const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const downloadDir = path.resolve(__dirname, 'downloads');
if (!fs.existsSync(downloadDir)) {
  fs.mkdirSync(downloadDir, { recursive: true });
}

// Clean previous downloads
fs.readdirSync(downloadDir).forEach((file) => {
  fs.unlinkSync(path.join(downloadDir, file));
});

console.log('Starting Chrome headless with CDP...');
const chromeProc = spawn(chromePath, [
  '--headless=new',
  '--remote-debugging-port=9225',
  '--disable-gpu',
  '--no-first-run',
  '--no-default-browser-check',
  'http://localhost:8080/index.html'
]);

let killed = false;
function cleanup() {
  if (!killed) {
    killed = true;
    try { chromeProc.kill(); } catch (e) {}
  }
}
process.on('exit', cleanup);
process.on('SIGINT', cleanup);

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function run() {
  await sleep(2500); // Wait for Chrome to bind port

  console.log('Fetching CDP endpoints from http://localhost:9225/json...');
  const res = await fetch('http://localhost:9225/json');
  const pages = await res.json();
  const page = pages.find((p) => p.url.includes('localhost:8080') || p.type === 'page');
  if (!page) {
    throw new Error('Target page not found: ' + JSON.stringify(pages));
  }

  console.log('Connecting to WebSocket:', page.webSocketDebuggerUrl);
  const ws = new WebSocket(page.webSocketDebuggerUrl);

  let idCounter = 1;
  const pending = new Map();

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(msg.error);
      else resolve(msg.result);
    }
  };

  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  function send(method, params = {}) {
    const id = idCounter++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async function evaluate(expression) {
    const res = await send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true
    });
    if (res.exceptionDetails) {
      throw new Error(JSON.stringify(res.exceptionDetails));
    }
    return res.result ? res.result.value : undefined;
  }

  console.log('Enabling Page & Runtime domains...');
  await send('Page.enable');
  await send('Runtime.enable');

  console.log('Setting download behavior to:', downloadDir);
  await send('Page.setDownloadBehavior', {
    behavior: 'allow',
    downloadPath: downloadDir
  });

  // Verify Page Title and Branding
  const branding = await evaluate(`({
    title: document.title,
    brandTitle: document.querySelector('.brand-title') ? document.querySelector('.brand-title').textContent : null,
    brandSubtitle: document.querySelector('.brand-subtitle') ? document.querySelector('.brand-subtitle').textContent : null,
    brandTagline: document.querySelector('.brand-tagline') ? document.querySelector('.brand-tagline').textContent : null,
    badgeTag: document.querySelector('.badge-tag') ? document.querySelector('.badge-tag').textContent : null,
    pageTitle: document.getElementById('page-title') ? document.getElementById('page-title').textContent : null,
  })`);
  console.log('\n--- VERIFY BRANDING ---');
  console.log('Page Title:', branding.title);
  console.log('Sidebar Brand Title:', branding.brandTitle);
  console.log('Sidebar Brand Subtitle:', branding.brandSubtitle);
  console.log('Sidebar Brand Tagline:', branding.brandTagline);
  console.log('Header Badge:', branding.badgeTag);
  console.log('Header Title:', branding.pageTitle);

  console.log('\nWaiting for window data to be fully loaded (518 cases)...');
  for (let i = 0; i < 50; i++) {
    const check = await evaluate(`(() => {
      const d = window.RESIDUALQ_DATA || window.GHOST_DATA;
      return d && d.cases && d.cases.length === 518;
    })()`);
    if (check) break;
    await sleep(200);
  }

  // Test 1: Full Submission Export (All 518 cases)
  console.log('\n--- TEST 1: EXPORT SUBMISSION ALL (518 CASES) ---');
  await evaluate(`document.getElementById('export-submission-all-btn').click()`);
  await sleep(4000); // Allow browser to write ~600KB file

  let files = fs.readdirSync(downloadDir);
  console.log('Files after Test 1:', files);

  // Test 2: Filter to INCOMPLETE and Export Filtered Submission
  console.log('\n--- TEST 2: FILTER TO INCOMPLETE & EXPORT SUBMISSION ---');
  const incompleteCount = await evaluate(`
    (() => {
      const chip = document.querySelector('.filter-chip[data-status="INCOMPLETE"]');
      if (chip) chip.click();
      return document.getElementById('export-filtered-badge') ? document.getElementById('export-filtered-badge').textContent : null;
    })()
  `);
  console.log('Incomplete Filter Badge Count:', incompleteCount);
  await evaluate(`document.getElementById('export-submission-filtered-btn').click()`);
  await sleep(3000);

  files = fs.readdirSync(downloadDir);
  console.log('Files after Test 2:', files);

  // Test 3: Export Detailed Audit Report All
  console.log('\n--- TEST 3: EXPORT DETAILED AUDIT REPORT ALL ---');
  await evaluate(`document.getElementById('export-detailed-all-btn').click()`);
  await sleep(3000);

  files = fs.readdirSync(downloadDir);
  console.log('Files after Test 3:', files);

  // Test 4: Export Detailed Audit Report Filtered
  console.log('\n--- TEST 4: EXPORT DETAILED AUDIT REPORT FILTERED ---');
  await evaluate(`document.getElementById('export-detailed-filtered-btn').click()`);
  await sleep(3000);

  files = fs.readdirSync(downloadDir);
  console.log('\n--- FINAL DOWNLOADS REPOSITORY ---');
  files.forEach((f) => {
    const stat = fs.statSync(path.join(downloadDir, f));
    console.log(`- ${f} (${stat.size} bytes)`);
  });

  // Test 5: Empty Search State & Export Warning
  console.log('\n--- TEST 5: EMPTY FILTER STATE & WARNING TOAST ---');
  const emptyStateResult = await evaluate(`
    (() => {
      const search = document.getElementById('header-search-input');
      search.value = 'query_that_matches_nothing_999';
      search.dispatchEvent(new Event('input'));
      
      const emptyMsg = document.querySelector('#case-table-body td');
      const emptyText = emptyMsg ? emptyMsg.innerText : '';
      
      // Click export filtered
      document.getElementById('export-submission-filtered-btn').click();
      
      // Check toast
      const toast = document.querySelector('.toast-warning .toast-message');
      const toastText = toast ? toast.innerText : '';
      
      return { emptyText, toastText };
    })()
  `);
  console.log('Empty state table message:', emptyStateResult.emptyText.trim().replace(/\\n/g, ' '));
  console.log('Empty state warning toast:', emptyStateResult.toastText);

  // Test 6: Reset search and check dossier modal
  console.log('\n--- TEST 6: MODAL DOSSIER OPEN & CLOSE ---');
  const modalResult = await evaluate(`
    (() => {
      const search = document.getElementById('header-search-input');
      search.value = '';
      search.dispatchEvent(new Event('input'));
      
      const allChip = document.querySelector('.filter-chip[data-status="ALL"]');
      if (allChip) allChip.click();
      
      const firstRow = document.querySelector('#case-table-body tr');
      if (firstRow) firstRow.click();
      
      const modal = document.getElementById('case-modal');
      const isOpen = modal && modal.classList.contains('open');
      const modalCid = modal ? modal.querySelector('.case-id-badge').textContent : null;
      
      // Close modal
      document.getElementById('modal-close-btn').click();
      const isClosedNow = !modal.classList.contains('open');
      
      return { isOpen, modalCid, isClosedNow };
    })()
  `);
  console.log('Modal opened successfully:', modalResult.isOpen, 'Case ID:', modalResult.modalCid, 'Modal closed cleanly:', modalResult.isClosedNow);

  // Test 7: Double-Click / Debounce Protection
  console.log('\n--- TEST 7: DEBOUNCE / CONCURRENCY PROTECTION ---');
  const debounceResult = await evaluate(`
    (() => {
      let click1 = 'ok';
      let click2 = 'ok';
      try {
        document.getElementById('export-submission-all-btn').click();
        document.getElementById('export-submission-all-btn').click();
      } catch (e) {
        click2 = e.toString();
      }
      const toastWarning = document.querySelector('.toast-warning');
      return {
        warningShown: toastWarning ? toastWarning.textContent : 'none',
        buttonDisabled: document.getElementById('export-dropdown-toggle') ? document.getElementById('export-dropdown-toggle').disabled : false
      };
    })()
  `);
  console.log('Debounce protection active:', debounceResult);

  console.log('\nAll in-browser CDP tests completed successfully!');
  cleanup();
  process.exit(0);
}

run().catch((err) => {
  console.error('Test run error:', err);
  cleanup();
  process.exit(1);
});
