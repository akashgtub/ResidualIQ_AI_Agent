/**
 * ResidualQ AI Agent — Enterprise Deletion Audit Frontend Logic
 * Strictly Vanilla JS, accessible, reactive, and modular.
 */

(function () {
  'use strict';

  // Dynamic Data Accessor (prevents race conditions if data bundle loads asynchronously)
  function getData() {
    return window.RESIDUALQ_DATA || window.GHOST_DATA || null;
  }

  // App State
  const state = {
    currentTab: 'overview',
    searchQuery: '',
    statusFilter: 'ALL',
    systemFilter: 'ALL',
    riskFilter: 'ALL',
    page: 1,
    pageSize: 15,
    sortField: 'case_num',
    sortDir: 'asc',
    selectedCase: null,
  };

  // DOM Elements Cache
  const elements = {
    navItems: document.querySelectorAll('.nav-item'),
    viewSections: document.querySelectorAll('.view-section'),
    pageTitle: document.getElementById('page-title'),
    pageSubtitle: document.getElementById('page-subtitle'),
    headerSearch: document.getElementById('header-search-input'),
    caseTableBody: document.getElementById('case-table-body'),
    tablePagination: document.getElementById('table-pagination'),
    paginationInfo: document.getElementById('pagination-info'),
    paginationPages: document.getElementById('pagination-pages'),
    prevPageBtn: document.getElementById('prev-page-btn'),
    nextPageBtn: document.getElementById('next-page-btn'),
    filterChips: document.querySelectorAll('.filter-chip'),
    systemSelect: document.getElementById('filter-system-select'),
    riskSelect: document.getElementById('filter-risk-select'),
    modalOverlay: document.getElementById('case-modal'),
    modalCloseBtn: document.getElementById('modal-close-btn'),
    modalBody: document.getElementById('modal-body-content'),
    exportDropdownToggle: document.getElementById('export-dropdown-toggle'),
    exportMenu: document.getElementById('export-menu'),
    exportBtnLabel: document.getElementById('export-btn-label'),
    exportFilteredBadge: document.getElementById('export-filtered-badge'),
    exportSubmissionAllBtn: document.getElementById('export-submission-all-btn'),
    exportSubmissionFilteredBtn: document.getElementById('export-submission-filtered-btn'),
    exportDetailedAllBtn: document.getElementById('export-detailed-all-btn'),
    exportDetailedFilteredBtn: document.getElementById('export-detailed-filtered-btn'),
    toastContainer: document.getElementById('toast-container'),
  };

  // Helper: Format ISO timestamp cleanly
  function formatDate(isoStr) {
    if (!isoStr) return '—';
    try {
      const dt = new Date(isoStr);
      return dt.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
    } catch (e) {
      return isoStr;
    }
  }

  // Helper: Get Badge HTML for Deletion Status
  function getStatusBadge(status) {
    switch (status) {
      case 'COMPLETE':
        return '<span class="status-badge badge-complete"><span class="status-dot"></span>COMPLETE</span>';
      case 'INCOMPLETE':
        return '<span class="status-badge badge-incomplete"><span class="status-dot" style="background-color: var(--critical)"></span>INCOMPLETE</span>';
      case 'NOT_APPLICABLE':
        return '<span class="status-badge badge-not-applicable">NOT APPLICABLE</span>';
      default:
        return `<span class="status-badge">${status}</span>`;
    }
  }

  // Helper: Get Reported Status Badge
  function getReportedBadge(reported) {
    switch (reported) {
      case 'COMPLETE':
        return '<span class="status-badge badge-reported-complete">COMPLETE</span>';
      case 'PARTIALLY_COMPLETE':
        return '<span class="status-badge badge-reported-partial">PARTIAL</span>';
      case 'NOT_STARTED':
        return '<span class="status-badge badge-reported-not-started">NOT STARTED</span>';
      default:
        return `<span class="status-badge">${reported || '—'}</span>`;
    }
  }

  // Helper: Show Toast Notification
  function showToast(message, type = 'info', duration = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let iconSvg = '';
    if (type === 'success') {
      iconSvg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>';
    } else if (type === 'error') {
      iconSvg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
    } else if (type === 'warning') {
      iconSvg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';
    } else {
      iconSvg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
    }

    toast.innerHTML = `
      ${iconSvg}
      <div class="toast-message">${message}</div>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // 1. Navigation & Routing
  function initNavigation() {
    elements.navItems.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const tab = btn.dataset.tab;
        if (!tab) return;
        switchTab(tab);
      });
    });
  }

  function switchTab(tabId) {
    state.currentTab = tabId;

    // Update sidebar active class
    elements.navItems.forEach((btn) => {
      if (btn.dataset.tab === tabId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Update Views visibility
    elements.viewSections.forEach((view) => {
      if (view.id === `view-${tabId}`) {
        view.style.display = 'block';
      } else {
        view.style.display = 'none';
      }
    });

    // Update Header Titles
    const titles = {
      overview: { title: 'ResidualQ Audit Intelligence Dashboard', subtitle: 'Global Deletion Verification & Risk Telemetry' },
      explorer: { title: 'ResidualQ Case Audit Explorer', subtitle: 'Interactive verification ledger across 518 evaluation requests' },
      radar: { title: 'ResidualQ Risk Topology', subtitle: 'Replication drift, active connectors, and unpurged data flows' },
      rules: { title: 'ResidualQ Policy & Deletion Rules Matrix', subtitle: '15 Ground-truth treatment classifications from deletion_rules.csv' },
    };

    const currentMeta = titles[tabId] || titles.overview;
    elements.pageTitle.textContent = currentMeta.title;
    elements.pageSubtitle.textContent = currentMeta.subtitle;

    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // 2. Filter & Search Logic
  function getFilteredCases() {
    const data = getData();
    if (!data || !data.cases) return [];
    return data.cases.filter((c) => {
      // Status chip
      if (state.statusFilter !== 'ALL' && c.deletion_status !== state.statusFilter) {
        return false;
      }
      // System select
      if (state.systemFilter !== 'ALL' && !c.systems.includes(state.systemFilter)) {
        return false;
      }
      // Risk select
      if (state.riskFilter === 'FLOW' && !c.has_active_flow) return false;
      if (state.riskFilter === 'RESTORE' && !c.has_restore_risk) return false;
      if (state.riskFilter === 'PII' && !c.has_exposed_pii) return false;
      if (state.riskFilter === 'RECORD' && !c.has_remaining_record) return false;

      // Text query
      if (state.searchQuery) {
        const q = state.searchQuery.toLowerCase();
        const matchCid = c.case_id.toLowerCase().includes(q);
        const matchEmail = c.email.toLowerCase().includes(q);
        const matchText = c.request_text && c.request_text.toLowerCase().includes(q);
        const matchResource = c.steps.some(
          (s) => (s.resource_id && s.resource_id.toLowerCase().includes(q)) || (s.evidence_id && s.evidence_id.toLowerCase().includes(q))
        );
        if (!matchCid && !matchEmail && !matchText && !matchResource) {
          return false;
        }
      }

      return true;
    });
  }

  // Sorting
  function sortCases(cases) {
    return [...cases].sort((a, b) => {
      let valA = a[state.sortField];
      let valB = b[state.sortField];

      if (typeof valA === 'string') valA = valA.toLowerCase();
      if (typeof valB === 'string') valB = valB.toLowerCase();

      if (valA < valB) return state.sortDir === 'asc' ? -1 : 1;
      if (valA > valB) return state.sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }

  // 3. Render Case Explorer Table
  function renderCaseTable() {
    const filtered = getFilteredCases();
    const sorted = sortCases(filtered);
    const total = sorted.length;

    // Update Filtered Count Badge in Export Menu
    if (elements.exportFilteredBadge) {
      elements.exportFilteredBadge.textContent = `${total}`;
    }

    // Pagination bounds
    const totalPages = Math.ceil(total / state.pageSize) || 1;
    if (state.page > totalPages) state.page = totalPages;
    const startIndex = (state.page - 1) * state.pageSize;
    const endIndex = Math.min(startIndex + state.pageSize, total);
    const pageItems = sorted.slice(startIndex, endIndex);

    // Update pagination UI
    elements.paginationInfo.textContent = `Showing ${total > 0 ? startIndex + 1 : 0} to ${endIndex} of ${total} cases`;
    elements.prevPageBtn.disabled = state.page <= 1;
    elements.nextPageBtn.disabled = state.page >= totalPages;

    // Render Page Numbers
    renderPaginationButtons(totalPages);

    // Render Rows
    if (pageItems.length === 0) {
      elements.caseTableBody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; padding: 48px; color: var(--text-secondary);">
            <div style="font-size: 16px; font-weight: 600; margin-bottom: 6px;">No matching cases found</div>
            <div style="font-size: 12px;">Try adjusting your search query, status chips, or system filters.</div>
          </td>
        </tr>
      `;
      return;
    }

    elements.caseTableBody.innerHTML = pageItems
      .map((c) => {
        const sysTags = c.systems
          .slice(0, 3)
          .map((s) => `<span class="sys-tag">${s.replace('_', ' ')}</span>`)
          .join('');
        const moreSys = c.systems.length > 3 ? `<span class="sys-tag">+${c.systems.length - 3}</span>` : '';

        return `
          <tr data-case-id="${c.case_id}">
            <td><span class="case-id-badge">${c.case_id}</span></td>
            <td>
              <div class="email-cell">${c.email}</div>
              <div style="font-size: 11px; color: var(--text-muted);">${formatDate(c.requested_at)}</div>
            </td>
            <td>${getReportedBadge(c.reported_status)}</td>
            <td>${getStatusBadge(c.deletion_status)}</td>
            <td>
              ${
                c.finding_count > 0
                  ? `<span style="color: var(--critical); font-weight: 700;">${c.finding_count} finding${c.finding_count > 1 ? 's' : ''}</span>`
                  : `<span style="color: var(--text-muted); font-size: 12px;">None (Clean)</span>`
              }
            </td>
            <td>
              <span style="font-weight: 600; color: var(--primary);">${c.remediation_count}</span>
              <span style="font-size: 11px; color: var(--text-secondary);"> steps</span>
            </td>
            <td>
              <div class="system-tag-list">${sysTags || '<span class="sys-tag">none</span>'}${moreSys}</div>
            </td>
            <td style="text-align: right;">
              <button class="btn-secondary view-case-btn" data-case-id="${c.case_id}" style="height: 30px; padding: 0 10px; font-size: 11px;">
                Investigate
              </button>
            </td>
          </tr>
        `;
      })
      .join('');

    // Attach row click handlers
    elements.caseTableBody.querySelectorAll('tr').forEach((row) => {
      row.addEventListener('click', (e) => {
        const cid = row.dataset.caseId;
        if (cid) openCaseModal(cid);
      });
    });
  }

  function renderPaginationButtons(totalPages) {
    let pagesHtml = '';
    const maxVisible = 5;
    let startPage = Math.max(1, state.page - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);

    if (endPage - startPage + 1 < maxVisible) {
      startPage = Math.max(1, endPage - maxVisible + 1);
    }

    for (let p = startPage; p <= endPage; p++) {
      pagesHtml += `
        <button class="page-btn ${p === state.page ? 'active' : ''}" data-page="${p}">
          ${p}
        </button>
      `;
    }
    elements.paginationPages.innerHTML = pagesHtml;

    elements.paginationPages.querySelectorAll('.page-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        state.page = parseInt(btn.dataset.page, 10);
        renderCaseTable();
      });
    });
  }

  // 4. Modal Investigation Deep-Dive
  function openCaseModal(caseId) {
    const data = getData();
    if (!data || !data.cases) return;
    const c = data.cases.find((item) => item.case_id === caseId);
    if (!c) return;

    state.selectedCase = c;

    // Build timeline steps
    const timelineHtml =
      c.steps.length === 0
        ? `<div style="padding: 24px; text-align: center; color: var(--text-secondary); background: var(--surface-alt); border-radius: var(--radius-md);">
            <strong>No plan steps required.</strong> Request classified as <code>NOT_APPLICABLE</code> (non-deletion intent).
          </div>`
        : c.steps
            .map((s) => {
              const phaseClass =
                s.phase === 'FINDING'
                  ? 'step-finding'
                  : s.phase === 'REMEDIATION'
                  ? 'step-remediation'
                  : 'step-verification';

              const phaseBadgeClass =
                s.phase === 'FINDING'
                  ? 'badge-phase-finding'
                  : s.phase === 'REMEDIATION'
                  ? 'badge-phase-remediation'
                  : 'badge-phase-verification';

              const evidenceBadge = s.evidence_id
                ? `<span class="step-evidence-link" title="Participant Evidence Citation">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                    ${s.evidence_id}
                  </span>`
                : `<span style="font-size: 11px; color: var(--text-muted); font-style: italic;">Contract empty evidence_id</span>`;

              return `
                <div class="timeline-step ${phaseClass}">
                  <div class="step-marker">${s.step_no}</div>
                  <div class="step-card">
                    <div class="step-header">
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="step-phase-badge ${phaseBadgeClass}">${s.phase}</span>
                        <span class="step-resource-tag">${s.system_id} / ${s.resource_id}</span>
                      </div>
                      ${evidenceBadge}
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 4px;">
                      <span class="step-operation-text">
                        <strong>Operation:</strong> <code>${s.operation}</code>
                      </span>
                      <span class="status-badge" style="font-size: 10px; padding: 2px 8px;">
                        State: ${s.state}
                      </span>
                    </div>
                  </div>
                </div>
              `;
            })
            .join('');

    // Modal Body Content
    elements.modalBody.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="case-id-badge" style="font-size: 16px; padding: 4px 12px;">${c.case_id}</span>
          ${getStatusBadge(c.deletion_status)}
        </div>
        <div>
          <button id="copy-json-btn" class="btn-secondary" style="height: 32px; font-size: 11px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            Copy steps_json
          </button>
        </div>
      </div>

      <div class="case-meta-grid">
        <div class="meta-field">
          <span class="meta-label">Subject Email</span>
          <span class="meta-value">${c.email}</span>
        </div>
        <div class="meta-field">
          <span class="meta-label">Reported Claim</span>
          <span class="meta-value">${getReportedBadge(c.reported_status)}</span>
        </div>
        <div class="meta-field">
          <span class="meta-label">Audit Cutoff (audit_at)</span>
          <span class="meta-value">${formatDate(c.audit_at)}</span>
        </div>
        <div class="meta-field">
          <span class="meta-label">Submission Time</span>
          <span class="meta-value">${formatDate(c.requested_at)}</span>
        </div>
        <div class="meta-field">
          <span class="meta-label">Reported Claim Time</span>
          <span class="meta-value">${formatDate(c.reported_at)}</span>
        </div>
        <div class="meta-field">
          <span class="meta-label">Affected Systems</span>
          <span class="meta-value">${c.systems.join(', ') || 'None'}</span>
        </div>
      </div>

      <div>
        <div class="meta-label" style="margin-bottom: 6px;">Subject Request Text (Multilingual Intent Check)</div>
        <div class="request-text-card">
          "${c.request_text || 'No request text provided'}"
        </div>
      </div>

      <div>
        <div class="timeline-section-title">
          <span>Execution Plan (${c.steps.length} Steps)</span>
          <span style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">
            FINDING (${c.finding_count}) &rarr; REMEDIATION (${c.remediation_count}) &rarr; VERIFICATION (${c.verification_count})
          </span>
        </div>
        <div class="timeline">
          ${timelineHtml}
        </div>
      </div>
    `;

    // 1-Click Copy Steps JSON Handler
    const copyBtn = document.getElementById('copy-json-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(JSON.stringify(c.steps, null, 2)).then(() => {
          copyBtn.textContent = 'Copied to Clipboard!';
          setTimeout(() => {
            copyBtn.innerHTML = `
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              Copy steps_json
            `;
          }, 1500);
        });
      });
    }

    elements.modalOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    elements.modalOverlay.classList.remove('open');
    document.body.style.overflow = '';
    state.selectedCase = null;
  }

  // 5. Render Overview Dashboard Widgets
  function renderOverviewDashboard() {
    const data = getData();
    if (!data) return;
    // Top Systems Risk List
    const topSystemsList = document.getElementById('top-systems-risk-list');
    if (topSystemsList && data.system_findings) {
      const entries = Object.entries(data.system_findings).sort((a, b) => b[1] - a[1]);
      const maxCount = Math.max(...entries.map((e) => e[1])) || 1;

      topSystemsList.innerHTML = entries
        .map(([sys, count]) => {
          const pct = ((count / maxCount) * 100).toFixed(0);
          return `
            <div class="system-risk-item">
              <div class="system-risk-meta">
                <span class="system-name-tag">${sys}</span>
                <span class="system-risk-count">${count} ghost records</span>
              </div>
              <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: ${pct}%"></div>
              </div>
            </div>
          `;
        })
        .join('');
    }

    // Recent Critical Findings Table Preview
    const recentTable = document.getElementById('recent-critical-table-body');
    if (recentTable) {
      const criticalCases = data.cases.filter((c) => c.deletion_status === 'INCOMPLETE').slice(0, 6);
      recentTable.innerHTML = criticalCases
        .map(
          (c) => `
          <tr data-case-id="${c.case_id}">
            <td><span class="case-id-badge">${c.case_id}</span></td>
            <td><span class="email-cell">${c.email}</span></td>
            <td>${getReportedBadge(c.reported_status)}</td>
            <td><span style="font-weight: 700; color: var(--critical);">${c.finding_count} violations</span></td>
            <td style="text-align: right;">
              <button class="btn-secondary" style="height: 28px; padding: 0 8px; font-size: 11px;">Inspect</button>
            </td>
          </tr>
        `
        )
        .join('');

      recentTable.querySelectorAll('tr').forEach((row) => {
        row.addEventListener('click', () => {
          openCaseModal(row.dataset.caseId);
        });
      });
    }
  }

  // 6. Render Policy Rules Table
  function renderRulesMatrix() {
    const data = getData();
    const rulesBody = document.getElementById('rules-table-body');
    if (!rulesBody || !data || !data.rules) return;

    rulesBody.innerHTML = data.rules
      .map((r) => {
        let actClass = 'rule-delete';
        const act = (r.required_action || '').toUpperCase();
        if (act === 'REDACT') actClass = 'rule-redact';
        else if (act === 'ANONYMIZE') actClass = 'rule-anonymize';
        else if (act === 'RETAIN') actClass = 'rule-retain';
        else if (act === 'ACCOUNT_TOMBSTONE') actClass = 'rule-tombstone';

        return `
          <tr>
            <td><strong style="color: var(--primary); font-family: monospace;">Rule ${r.rule_id || '—'}</strong></td>
            <td><span style="font-weight: 600;">${r.data_category || '—'}</span></td>
            <td><span class="rule-treatment-badge ${actClass}">${r.required_action}</span></td>
            <td><code>${r.system_ids || '—'}</code></td>
            <td style="font-size: 12px; color: var(--text-secondary);">${r.condition || '—'}</td>
            <td style="font-size: 12px; line-height: 1.4;">${r.description || '—'}</td>
          </tr>
        `;
      })
      .join('');
  }

  // 7. CSV Export Logic (RFC 4180 Compliant + Unicode BOM + Safe Blob Download)
  let isExporting = false;

  function escapeCsvCell(val) {
    if (val === null || val === undefined) return '';
    const str = typeof val === 'string' ? val : String(val);
    if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
      return '"' + str.replace(/"/g, '""') + '"';
    }
    return str;
  }

  function downloadCsv(filename, rows) {
    if (isExporting) {
      showToast('An export is already in progress.', 'warning');
      return;
    }
    isExporting = true;

    // Visual feedback
    if (elements.exportBtnLabel) elements.exportBtnLabel.textContent = 'Generating...';
    if (elements.exportDropdownToggle) elements.exportDropdownToggle.disabled = true;

    try {
      // RFC 4180: CRLF record separators
      const csvBody = rows.map((row) => row.map(escapeCsvCell).join(',')).join('\r\n');
      
      // Prepend UTF-8 BOM (\uFEFF) for Microsoft Excel compatibility
      const blob = new Blob(['\uFEFF' + csvBody], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();

      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        isExporting = false;
        if (elements.exportBtnLabel) elements.exportBtnLabel.textContent = 'Export CSV';
        if (elements.exportDropdownToggle) elements.exportDropdownToggle.disabled = false;
      }, 500);

      // Close dropdown menu if open
      if (elements.exportMenu) {
        elements.exportMenu.classList.remove('show');
        if (elements.exportDropdownToggle) elements.exportDropdownToggle.setAttribute('aria-expanded', 'false');
      }

      showToast(`Export complete: ${rows.length - 1} records downloaded to ${filename}`, 'success');
    } catch (err) {
      console.error('CSV Export Error:', err);
      isExporting = false;
      if (elements.exportBtnLabel) elements.exportBtnLabel.textContent = 'Export CSV';
      if (elements.exportDropdownToggle) elements.exportDropdownToggle.disabled = false;
      showToast(`Export failed: ${err.message || 'Unknown error'}`, 'error');
    }
  }

  // Export 1: Official Submission Format — All 518 Cases
  function exportSubmissionAll() {
    const data = getData();
    if (!data || !data.cases || data.cases.length === 0) {
      showToast('No case data available for export.', 'warning');
      return;
    }
    const sorted = [...data.cases].sort((a, b) => a.case_num - b.case_num);
    const rows = [['case_id', 'deletion_status', 'steps_json']];
    sorted.forEach((c) => {
      const stepsStr = c.steps_json || JSON.stringify(c.steps || []);
      rows.push([c.case_id, c.deletion_status, stepsStr]);
    });
    downloadCsv('residualq_output.csv', rows);
  }

  // Export 2: Official Submission Format — Filtered Cases
  function exportSubmissionFiltered() {
    const filtered = getFilteredCases();
    if (filtered.length === 0) {
      showToast('No cases match the active filter criteria. Export cancelled.', 'warning');
      return;
    }
    const sorted = sortCases(filtered);
    const rows = [['case_id', 'deletion_status', 'steps_json']];
    sorted.forEach((c) => {
      const stepsStr = c.steps_json || JSON.stringify(c.steps || []);
      rows.push([c.case_id, c.deletion_status, stepsStr]);
    });
    const filterTag = state.statusFilter.toLowerCase();
    downloadCsv(`residualq_submission_filtered_${filterTag}.csv`, rows);
  }

  // Export 3: Detailed Audit Report — All 518 Cases
  function exportDetailedAll() {
    const data = getData();
    if (!data || !data.cases || data.cases.length === 0) {
      showToast('No case data available for export.', 'warning');
      return;
    }
    const sorted = [...data.cases].sort((a, b) => a.case_num - b.case_num);
    const headers = [
      'case_id',
      'email',
      'requested_at',
      'reported_status',
      'reported_at',
      'audit_at',
      'deletion_status',
      'finding_count',
      'remediation_count',
      'verification_count',
      'total_steps',
      'systems',
      'has_active_flow',
      'has_restore_risk',
      'has_exposed_pii',
      'has_remaining_record',
    ];
    const rows = [headers];
    sorted.forEach((c) => {
      rows.push([
        c.case_id,
        c.email,
        c.requested_at,
        c.reported_status,
        c.reported_at,
        c.audit_at,
        c.deletion_status,
        c.finding_count,
        c.remediation_count,
        c.verification_count,
        c.total_steps,
        (c.systems || []).join('; '),
        c.has_active_flow ? 'YES' : 'NO',
        c.has_restore_risk ? 'YES' : 'NO',
        c.has_exposed_pii ? 'YES' : 'NO',
        c.has_remaining_record ? 'YES' : 'NO',
      ]);
    });
    downloadCsv('residualq_audit_report_all.csv', rows);
  }

  // Export 4: Detailed Audit Report — Filtered Cases
  function exportDetailedFiltered() {
    const filtered = getFilteredCases();
    if (filtered.length === 0) {
      showToast('No cases match the active filter criteria. Export cancelled.', 'warning');
      return;
    }
    const sorted = sortCases(filtered);
    const headers = [
      'case_id',
      'email',
      'requested_at',
      'reported_status',
      'reported_at',
      'audit_at',
      'deletion_status',
      'finding_count',
      'remediation_count',
      'verification_count',
      'total_steps',
      'systems',
      'has_active_flow',
      'has_restore_risk',
      'has_exposed_pii',
      'has_remaining_record',
    ];
    const rows = [headers];
    sorted.forEach((c) => {
      rows.push([
        c.case_id,
        c.email,
        c.requested_at,
        c.reported_status,
        c.reported_at,
        c.audit_at,
        c.deletion_status,
        c.finding_count,
        c.remediation_count,
        c.verification_count,
        c.total_steps,
        (c.systems || []).join('; '),
        c.has_active_flow ? 'YES' : 'NO',
        c.has_restore_risk ? 'YES' : 'NO',
        c.has_exposed_pii ? 'YES' : 'NO',
        c.has_remaining_record ? 'YES' : 'NO',
      ]);
    });
    const filterTag = state.statusFilter.toLowerCase();
    downloadCsv(`residualq_audit_report_filtered_${filterTag}.csv`, rows);
  }

  // 8. Event Listeners Initialization
  function initEventListeners() {
    // Filter Chips
    elements.filterChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        elements.filterChips.forEach((c) => c.classList.remove('active'));
        chip.classList.add('active');
        state.statusFilter = chip.dataset.status;
        state.page = 1;
        renderCaseTable();
      });
    });

    // Select Filters
    if (elements.systemSelect) {
      elements.systemSelect.addEventListener('change', (e) => {
        state.systemFilter = e.target.value;
        state.page = 1;
        renderCaseTable();
      });
    }

    if (elements.riskSelect) {
      elements.riskSelect.addEventListener('change', (e) => {
        state.riskFilter = e.target.value;
        state.page = 1;
        renderCaseTable();
      });
    }

    // Search Input
    if (elements.headerSearch) {
      elements.headerSearch.addEventListener('input', (e) => {
        state.searchQuery = e.target.value.trim();
        state.page = 1;
        renderCaseTable();
      });
    }

    // Pagination buttons
    elements.prevPageBtn.addEventListener('click', () => {
      if (state.page > 1) {
        state.page--;
        renderCaseTable();
      }
    });

    elements.nextPageBtn.addEventListener('click', () => {
      state.page++;
      renderCaseTable();
    });

    // Modal Close
    elements.modalCloseBtn.addEventListener('click', closeModal);
    elements.modalOverlay.addEventListener('click', (e) => {
      if (e.target === elements.modalOverlay) closeModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (elements.modalOverlay.classList.contains('open')) {
          closeModal();
        }
        if (elements.exportMenu && elements.exportMenu.classList.contains('show')) {
          elements.exportMenu.classList.remove('show');
          if (elements.exportDropdownToggle) elements.exportDropdownToggle.setAttribute('aria-expanded', 'false');
        }
      }
    });

    // Dropdown Toggle & Outside Click
    if (elements.exportDropdownToggle && elements.exportMenu) {
      elements.exportDropdownToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = elements.exportMenu.classList.contains('show');
        if (isOpen) {
          elements.exportMenu.classList.remove('show');
          elements.exportDropdownToggle.setAttribute('aria-expanded', 'false');
        } else {
          elements.exportMenu.classList.add('show');
          elements.exportDropdownToggle.setAttribute('aria-expanded', 'true');
        }
      });

      // Close dropdown when clicking outside
      document.addEventListener('click', (e) => {
        if (!elements.exportDropdownToggle.contains(e.target) && !elements.exportMenu.contains(e.target)) {
          elements.exportMenu.classList.remove('show');
          elements.exportDropdownToggle.setAttribute('aria-expanded', 'false');
        }
      });
    }

    // Export Button Click Listeners
    if (elements.exportSubmissionAllBtn) {
      elements.exportSubmissionAllBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        exportSubmissionAll();
      });
    }

    if (elements.exportSubmissionFilteredBtn) {
      elements.exportSubmissionFilteredBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        exportSubmissionFiltered();
      });
    }

    if (elements.exportDetailedAllBtn) {
      elements.exportDetailedAllBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        exportDetailedAll();
      });
    }

    if (elements.exportDetailedFilteredBtn) {
      elements.exportDetailedFilteredBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        exportDetailedFiltered();
      });
    }
  }

  // App Initialization with polling retry for data bundle
  let initAttempts = 0;
  function init() {
    const data = getData();
    if (!data || !data.cases) {
      initAttempts++;
      if (initAttempts < 100) {
        setTimeout(init, 50);
      } else {
        console.error('ResidualQ bundle failed to load within timeout.');
      }
      return;
    }
    initNavigation();
    renderOverviewDashboard();
    renderRulesMatrix();
    renderCaseTable();
    initEventListeners();
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
