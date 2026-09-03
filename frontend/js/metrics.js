/**
 * js/metrics.js — Safe DOM Renderers for cards, tables, projections, health status and model modals.
 * Immune to DOM XSS: strictly uses DOM APIs and textContent instead of innerHTML.
 */

const Metrics = {
  _modelsData: [],
  _sortColumn: 'requests',
  _sortDirection: 'desc',

  showSkeletonLoading() {
    const ids = [
      'val-pct-today', 'val-pct-week', 'val-pct-month',
      'mini-tokens-today', 'mini-input-tokens', 'mini-output-tokens',
      'mini-cost-today', 'mini-latency-today', 'mini-error-rate',
      'proj-burn-rate', 'proj-eta', 'proj-daily-est', 'proj-daily-cost'
    ];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.classList.add('skeleton');
    });
  },

  hideSkeletonLoading() {
    const ids = [
      'val-pct-today', 'val-pct-week', 'val-pct-month',
      'mini-tokens-today', 'mini-input-tokens', 'mini-output-tokens',
      'mini-cost-today', 'mini-latency-today', 'mini-error-rate',
      'proj-burn-rate', 'proj-eta', 'proj-daily-est', 'proj-daily-cost'
    ];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.classList.remove('skeleton');
    });
  },

  /**
   * Render Top 3 Usage Cards (Daily, Weekly, Monthly)
   */
  renderUsageCards(summary = {}, limits = {}) {
    const today = summary.today || {};
    const week = summary.week || {};
    const month = summary.month || {};

    const dailyLimit = limits.daily || null;
    const weeklyLimit = limits.weekly || null;
    const monthlyLimit = limits.monthly || null;

    this._updateCard('today', today.requests || 0, dailyLimit);
    this._updateCard('week', week.requests || 0, weeklyLimit);
    this._updateCard('month', month.requests || 0, monthlyLimit);
  },

  _updateCard(period, used, limit) {
    const pctEl = document.getElementById(`val-pct-${period}`);
    const barEl = document.getElementById(`bar-${period}`);
    const badgeEl = document.getElementById(`badge-risk-${period}`);
    const usedEl = document.getElementById(`val-used-${period}`);
    const leftEl = document.getElementById(`val-left-${period}`);

    if (!pctEl || !barEl) return;

    if (limit && limit > 0) {
      const ratio = used / limit;
      const pct = Math.min(ratio * 100, 100);
      const remaining = Math.max(limit - used, 0);
      const riskLevel = Utils.getRiskLevel(ratio);

      pctEl.textContent = pct.toFixed(1) + '%';
      barEl.style.width = pct + '%';
      barEl.className = `progress-bar-fill fill-${riskLevel}`;

      if (badgeEl) {
        badgeEl.textContent = Utils.getRiskLabel(riskLevel);
        badgeEl.className = `card-risk-badge badge-${riskLevel}`;
      }

      usedEl.textContent = `${Utils.formatNumber(used)} / ${Utils.formatNumber(limit)} req`;
      leftEl.textContent = `${Utils.formatNumber(remaining)} restantes`;
    } else {
      pctEl.textContent = 'N/D';
      barEl.style.width = '0%';
      if (badgeEl) {
        badgeEl.textContent = 'Sem Limite';
        badgeEl.className = 'card-risk-badge badge-normal';
      }
      usedEl.textContent = `${Utils.formatNumber(used)} req`;
      leftEl.textContent = 'Limite N/D';
    }
  },

  /**
   * Render Mini Metric Cards
   */
  renderMiniCards(today = {}) {
    const tokensEl = document.getElementById('mini-tokens-today');
    const inputEl = document.getElementById('mini-input-tokens');
    const outputEl = document.getElementById('mini-output-tokens');
    const costEl = document.getElementById('mini-cost-today');
    const latEl = document.getElementById('mini-latency-today');
    const errEl = document.getElementById('mini-error-rate');

    if (tokensEl) tokensEl.textContent = Utils.formatTokens(today.totalTokens);
    if (inputEl) inputEl.textContent = Utils.formatTokens(today.inputTokens);
    if (outputEl) outputEl.textContent = Utils.formatTokens(today.outputTokens);
    if (costEl) costEl.textContent = Utils.formatCost(today.cost);
    if (latEl) latEl.textContent = Utils.formatLatency(today.avgLatencyMs);
    if (errEl) errEl.textContent = today.errorRate !== undefined ? Utils.formatPct(today.errorRate) : 'N/D';
  },

  /**
   * Render Burn Rate & Projections
   */
  renderProjection(proj = {}) {
    const rateEl = document.getElementById('proj-burn-rate');
    const tokensRateEl = document.getElementById('proj-tokens-rate');
    const etaEl = document.getElementById('proj-eta');
    const dailyEstEl = document.getElementById('proj-daily-est');
    const dailyPctEl = document.getElementById('proj-daily-pct');
    const dailyCostEl = document.getElementById('proj-daily-cost');

    if (rateEl) rateEl.textContent = proj.requestsPerHour ? `${Utils.formatNumber(proj.requestsPerHour)} req/h` : '-- req/h';
    if (tokensRateEl) tokensRateEl.textContent = proj.tokensPerHour ? `${Utils.formatTokens(proj.tokensPerHour)}/h` : '-- tok/h';

    if (etaEl) {
      if (proj.etaRequestsLimit) {
        etaEl.textContent = `Em ~ ${proj.etaRequestsLimit}`;
        etaEl.className = 'burn-rate-val text-warning';
      } else {
        etaEl.textContent = 'Sem risco iminente';
        etaEl.className = 'burn-rate-val text-muted';
      }
    }

    if (dailyEstEl) {
      dailyEstEl.textContent = proj.projectedDailyRequests ? Utils.formatNumber(proj.projectedDailyRequests) + ' req' : '--';
    }
    if (dailyPctEl) {
      const pct = proj.projectedUtilizationPct || 0;
      dailyPctEl.textContent = `${pct.toFixed(1)}% do limite`;
      dailyPctEl.className = `proj-sub-stat ${pct > 90 ? 'text-danger' : (pct > 75 ? 'text-warning' : 'text-accent')}`;
    }
    if (dailyCostEl) {
      dailyCostEl.textContent = Utils.formatCost(proj.projectedDailyCost);
    }
  },

  setModelsData(models = []) {
    this._modelsData = models;
    this.renderModelsTable();
  },

  setSort(column) {
    if (this._sortColumn === column) {
      this._sortDirection = this._sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      this._sortColumn = column;
      this._sortDirection = 'desc';
    }
    this.renderModelsTable();
  },

  /**
   * Render Models Table securely using DOM nodes
   */
  renderModelsTable(filterQuery = '') {
    const tbody = document.getElementById('tbody-models');
    if (!tbody) return;

    tbody.textContent = '';

    let list = [...this._modelsData];

    if (filterQuery) {
      const q = filterQuery.toLowerCase();
      list = list.filter((m) => (m.name || '').toLowerCase().includes(q) || (m.provider || '').toLowerCase().includes(q));
    }

    list.sort((a, b) => {
      let vA = a[this._sortColumn];
      let vB = b[this._sortColumn];
      if (vA === null || vA === undefined) vA = -Infinity;
      if (vB === null || vB === undefined) vB = -Infinity;
      if (typeof vA === 'string') {
        return this._sortDirection === 'asc' ? vA.localeCompare(vB) : vB.localeCompare(vA);
      }
      return this._sortDirection === 'asc' ? vA - vB : vB - vA;
    });

    if (list.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 10;
      td.className = 'text-center';
      td.style.padding = '32px';
      td.style.color = 'var(--text-dim)';
      td.textContent = 'Nenhum modelo encontrado. Configure um provedor nas configurações para listar os modelos.';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    list.forEach((m) => {
      const tr = document.createElement('tr');
      tr.className = 'clickable-row';
      tr.addEventListener('click', () => {
        if (window.App && App.openModelDetail) App.openModelDetail(m.provider, m.id);
      });

      // Name
      const tdName = document.createElement('td');
      const strongName = document.createElement('strong');
      strongName.textContent = m.name || m.id;
      tdName.appendChild(strongName);

      // Provider
      const tdProvider = document.createElement('td');
      const badgeProvider = document.createElement('span');
      badgeProvider.className = 'badge-tag';
      badgeProvider.textContent = (m.provider || '').toUpperCase();
      tdProvider.appendChild(badgeProvider);

      // Requests
      const tdReqs = document.createElement('td');
      tdReqs.className = 'text-right font-mono';
      tdReqs.textContent = Utils.formatNumber(m.requests);

      // Input
      const tdIn = document.createElement('td');
      tdIn.className = 'text-right font-mono';
      tdIn.textContent = Utils.formatTokens(m.inputTokens);

      // Output
      const tdOut = document.createElement('td');
      tdOut.className = 'text-right font-mono';
      tdOut.textContent = Utils.formatTokens(m.outputTokens);

      // Total
      const tdTot = document.createElement('td');
      tdTot.className = 'text-right font-mono';
      const strongTot = document.createElement('strong');
      strongTot.textContent = Utils.formatTokens(m.totalTokens);
      tdTot.appendChild(strongTot);

      // Latency
      const tdLat = document.createElement('td');
      tdLat.className = 'text-right font-mono';
      tdLat.textContent = Utils.formatLatency(m.latency);

      // Error rate
      const tdErr = document.createElement('td');
      tdErr.className = `text-right font-mono ${m.errorRate > 0.05 ? 'text-danger' : ''}`;
      tdErr.textContent = Utils.formatPct(m.errorRate);

      // Cost
      const tdCost = document.createElement('td');
      tdCost.className = 'text-right font-mono text-accent';
      tdCost.textContent = Utils.formatCost(m.cost);

      // Action Button
      const tdAction = document.createElement('td');
      tdAction.className = 'text-center';
      const btn = document.createElement('button');
      btn.className = 'btn btn-secondary btn-sm';
      btn.textContent = 'Detalhes';
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (window.App && App.openModelDetail) App.openModelDetail(m.provider, m.id);
      });
      tdAction.appendChild(btn);

      tr.appendChild(tdName);
      tr.appendChild(tdProvider);
      tr.appendChild(tdReqs);
      tr.appendChild(tdIn);
      tr.appendChild(tdOut);
      tr.appendChild(tdTot);
      tr.appendChild(tdLat);
      tr.appendChild(tdErr);
      tr.appendChild(tdCost);
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    });
  },

  /**
   * Render Request Log Table securely
   */
  renderLogsTable(logs = [], total = 0, offset = 0, limit = 50) {
    const tbody = document.getElementById('tbody-logs');
    const infoEl = document.getElementById('logs-pagination-info');
    const prevBtn = document.getElementById('btn-prev-page');
    const nextBtn = document.getElementById('btn-next-page');

    if (!tbody) return;

    tbody.textContent = '';

    if (logs.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 7;
      td.className = 'text-center';
      td.style.padding = '32px';
      td.style.color = 'var(--text-dim)';
      td.textContent = 'Nenhuma requisição registrada ainda.';
      tr.appendChild(td);
      tbody.appendChild(tr);

      if (infoEl) infoEl.textContent = 'Mostrando 0 de 0 requisições';
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
      return;
    }

    logs.forEach((l) => {
      const tr = document.createElement('tr');

      const tdTime = document.createElement('td');
      tdTime.className = 'font-mono';
      tdTime.textContent = Utils.formatTime(l.timestamp);

      const tdProv = document.createElement('td');
      const badgeProv = document.createElement('span');
      badgeProv.className = 'badge-tag';
      badgeProv.textContent = (l.provider || '').toUpperCase();
      tdProv.appendChild(badgeProv);

      const tdModel = document.createElement('td');
      const strongModel = document.createElement('strong');
      strongModel.textContent = l.model;
      tdModel.appendChild(strongModel);
      if (l.request_id) {
        const reqIdSpan = document.createElement('span');
        reqIdSpan.className = 'font-mono';
        reqIdSpan.style.cssText = 'display: block; font-size: 10px; color: var(--text-dim); margin-top: 2px;';
        reqIdSpan.textContent = l.request_id;
        tdModel.appendChild(reqIdSpan);
      }

      const tdTokens = document.createElement('td');
      tdTokens.className = 'text-right font-mono';
      tdTokens.textContent = Utils.formatTokens(l.total_tokens);
      if (l.cached_input_tokens) {
        const cacheTag = document.createElement('span');
        cacheTag.className = 'badge-tag';
        cacheTag.style.cssText = 'font-size: 9px; margin-left: 4px; color: var(--color-normal);';
        cacheTag.textContent = `⚡${Utils.formatTokens(l.cached_input_tokens)}`;
        cacheTag.title = 'Cached tokens';
        tdTokens.appendChild(cacheTag);
      }

      const tdLat = document.createElement('td');
      tdLat.className = 'text-right font-mono';
      tdLat.textContent = Utils.formatLatency(l.latency_ms);
      if (l.time_to_first_token_ms) {
        const ttftTag = document.createElement('span');
        ttftTag.className = 'badge-tag';
        ttftTag.style.cssText = 'font-size: 9px; margin-left: 4px; color: var(--ai-accent); border: 1px solid var(--border-color);';
        ttftTag.textContent = `TTFT ${Math.round(l.time_to_first_token_ms)}ms`;
        ttftTag.title = 'Time-to-first-token';
        tdLat.appendChild(document.createElement('br'));
        tdLat.appendChild(ttftTag);
      }

      const tdStatus = document.createElement('td');
      tdStatus.className = 'text-center';
      const badgeStatus = document.createElement('span');
      const isSuccess = l.status_code ? (l.status_code >= 200 && l.status_code < 400) : true;
      const statusClass = isSuccess ? 'badge-http-200' : (l.status_code === 429 ? 'badge-http-429' : 'badge-http-500');
      badgeStatus.className = `badge-tag ${statusClass}`;
      badgeStatus.textContent = l.status_code ? `${l.status_code}` : '200 OK';
      if (l.finish_reason) {
        badgeStatus.title = `Finish reason: ${l.finish_reason}`;
      }
      tdStatus.appendChild(badgeStatus);

      const tdCost = document.createElement('td');
      tdCost.className = 'text-right font-mono text-accent';
      tdCost.textContent = Utils.formatCost(l.cost_total);

      tr.appendChild(tdTime);
      tr.appendChild(tdProv);
      tr.appendChild(tdModel);
      tr.appendChild(tdTokens);
      tr.appendChild(tdLat);
      tr.appendChild(tdStatus);
      tr.appendChild(tdCost);

      tbody.appendChild(tr);
    });

    const start = offset + 1;
    const end = Math.min(offset + limit, total);
    if (infoEl) infoEl.textContent = `Mostrando ${start}–${end} de ${total} requisições`;
    if (prevBtn) prevBtn.disabled = offset === 0;
    if (nextBtn) nextBtn.disabled = offset + limit >= total;
  },

  /**
   * Render System Health Cards securely
   */
  renderHealthCards(healthList = []) {
    const grid = document.getElementById('health-grid');
    if (!grid) return;

    grid.textContent = '';

    if (healthList.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'text-center';
      emptyDiv.style.gridColumn = 'span 3';
      emptyDiv.style.color = 'var(--text-dim)';
      emptyDiv.style.padding = '40px';
      emptyDiv.textContent = 'Nenhum status disponível.';
      grid.appendChild(emptyDiv);
      return;
    }

    healthList.forEach((h) => {
      const card = document.createElement('div');
      card.className = 'health-card';

      const header = document.createElement('div');
      header.className = 'card-header';

      const title = document.createElement('h3');
      title.className = 'card-title';
      title.textContent = h.displayName || (h.provider || '').toUpperCase();

      const statusBadge = document.createElement('span');
      const status = h.status || 'UNKNOWN';
      statusBadge.className = `health-status-badge ${status}`;

      const dot = document.createElement('span');
      dot.className = `status-indicator-dot ${status.toLowerCase()}`;
      statusBadge.appendChild(dot);
      statusBadge.appendChild(document.createTextNode(` ${status}`));

      header.appendChild(title);
      header.appendChild(statusBadge);

      const metaList = document.createElement('div');
      metaList.className = 'health-meta-list';

      const createRow = (label, value, isMono = false) => {
        const row = document.createElement('div');
        row.className = 'health-meta-row';
        const lbl = document.createElement('span');
        lbl.className = 'text-muted';
        lbl.textContent = label;
        const val = document.createElement('span');
        if (isMono) val.className = 'font-mono';
        val.textContent = value;
        row.appendChild(lbl);
        row.appendChild(val);
        return row;
      };

      metaList.appendChild(createRow('Latência de Sondagem:', Utils.formatLatency(h.latency_ms), true));
      metaList.appendChild(createRow('Última Verificação:', Utils.formatTime(h.last_check), true));

      const diagRow = document.createElement('div');
      diagRow.className = 'health-meta-row';
      const diagLbl = document.createElement('span');
      diagLbl.className = 'text-muted';
      diagLbl.textContent = 'Diagnóstico:';
      const diagVal = document.createElement('span');
      if (h.details?.reason) {
        diagVal.className = 'text-warning';
        diagVal.textContent = h.details.reason;
      } else {
        diagVal.textContent = 'Operacional';
      }
      diagRow.appendChild(diagLbl);
      diagRow.appendChild(diagVal);
      metaList.appendChild(diagRow);

      card.appendChild(header);
      card.appendChild(metaList);
      grid.appendChild(card);
    });
  },

  /**
   * Render Model Detail Modal Content securely
   */
  renderModelModal(data) {
    const body = document.getElementById('modal-model-body');
    const title = document.getElementById('modal-model-title');
    const provider = document.getElementById('modal-model-provider');

    if (!body || !data) return;

    if (title) title.textContent = data.model;
    if (provider) provider.textContent = (data.provider || '').toUpperCase();

    body.textContent = '';

    const ov = data.overview || {};
    const us = data.usage || {};
    const pf = data.performance || {};
    const rel = data.reliability || {};
    const lim = data.limits || {};
    const cs = data.cost || {};

    const grid = document.createElement('div');
    grid.className = 'modal-section-grid';

    const createSection = (titleText, statRows) => {
      const sec = document.createElement('div');
      sec.className = 'modal-section';
      const h4 = document.createElement('h4');
      h4.textContent = titleText;
      sec.appendChild(h4);

      statRows.forEach(([lbl, val, cls]) => {
        const row = document.createElement('div');
        row.className = 'modal-stat-row';
        const labelSpan = document.createElement('span');
        labelSpan.className = 'text-muted';
        labelSpan.textContent = lbl;
        const valSpan = document.createElement('span');
        if (cls) valSpan.className = cls;
        valSpan.textContent = val;
        row.appendChild(labelSpan);
        row.appendChild(valSpan);
        sec.appendChild(row);
      });
      return sec;
    };

    // Overview
    grid.appendChild(createSection('Overview', [
      ['Nome do Modelo:', ov.name || data.model, 'font-bold'],
      ['Status:', `● ${ov.status || 'ONLINE'}`, 'text-accent'],
      ['Context Window:', ov.contextWindow ? Utils.formatNumber(ov.contextWindow) + ' tokens' : 'N/D', 'font-mono'],
      ['Max Output:', ov.maxTokens ? Utils.formatNumber(ov.maxTokens) + ' tokens' : 'N/D', 'font-mono'],
    ]));

    // Usage
    grid.appendChild(createSection('Uso Acumulado', [
      ['Total Requests:', Utils.formatNumber(us.requests), 'font-mono font-bold'],
      ['Input Tokens:', Utils.formatTokens(us.inputTokens), 'font-mono'],
      ['Output Tokens:', Utils.formatTokens(us.outputTokens), 'font-mono'],
      ['Total de Tokens:', Utils.formatTokens(us.totalTokens), 'font-mono text-accent font-bold'],
    ]));

    // Performance
    grid.appendChild(createSection('Performance & Latência', [
      ['Latência Média:', Utils.formatLatency(pf.avgLatency), 'font-mono font-bold'],
      ['P50 (Mediana):', Utils.formatLatency(pf.p50), 'font-mono'],
      ['P95:', Utils.formatLatency(pf.p95), 'font-mono'],
      ['P99:', Utils.formatLatency(pf.p99), 'font-mono'],
    ]));

    // Reliability & Limits
    grid.appendChild(createSection('Confiabilidade & Limites', [
      ['Taxa de Sucesso:', Utils.formatPct(rel.successRate), 'font-mono'],
      ['Taxa de Erro:', Utils.formatPct(rel.errorRate), `font-mono ${rel.errorRate > 0.05 ? 'text-danger' : ''}`],
      ['Limite de RPM:', lim.rpm ? Utils.formatNumber(lim.rpm) + ' req/min' : 'Desconhecido / N/D', 'font-mono'],
      ['Limite de TPM:', lim.tpm ? Utils.formatNumber(lim.tpm) + ' tok/min' : 'Desconhecido / N/D', 'font-mono'],
    ]));

    body.appendChild(grid);

    // Cost Breakdown
    const costSec = document.createElement('div');
    costSec.className = 'modal-section';
    const costH4 = document.createElement('h4');
    costH4.textContent = 'Custos Estimados';
    costSec.appendChild(costH4);

    const costGrid = document.createElement('div');
    costGrid.className = 'modal-section-grid';
    costGrid.style.marginBottom = '0';

    const costRows = [
      ['Custo Input (acumulado):', Utils.formatCost(cs.inputCost)],
      ['Custo Output (acumulado):', Utils.formatCost(cs.outputCost)],
    ];
    costRows.forEach(([lbl, val]) => {
      const row = document.createElement('div');
      row.className = 'modal-stat-row';
      const l = document.createElement('span');
      l.className = 'text-muted';
      l.textContent = lbl;
      const v = document.createElement('span');
      v.className = 'font-mono';
      v.textContent = val;
      row.appendChild(l);
      row.appendChild(v);
      costGrid.appendChild(row);
    });
    costSec.appendChild(costGrid);

    const totalRow = document.createElement('div');
    totalRow.className = 'modal-stat-row';
    totalRow.style.marginTop = '10px';
    totalRow.style.borderTop = '1px solid var(--border-color)';
    totalRow.style.paddingTop = '10px';

    const totalLabel = document.createElement('span');
    const strongLabel = document.createElement('strong');
    strongLabel.textContent = 'Custo Total Estimado:';
    totalLabel.appendChild(strongLabel);

    const totalVal = document.createElement('span');
    totalVal.className = 'font-mono text-accent';
    totalVal.style.fontSize = '16px';
    const strongVal = document.createElement('strong');
    strongVal.textContent = Utils.formatCost(cs.totalCost);
    totalVal.appendChild(strongVal);

    totalRow.appendChild(totalLabel);
    totalRow.appendChild(totalVal);
    costSec.appendChild(totalRow);

    body.appendChild(costSec);
  },
};
