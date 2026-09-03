/**
 * js/app.js — Application Bootstrap and Navigation Controller.
 */

const App = {
  _refreshTimer: null,
  _currentPage: 'dashboard',
  _isDemoMode: false,
  _latestSummary: null,
  _logsOffset: 0,
  _logsLimit: 50,

  async init() {
    this._isDemoMode = Storage.getDemoMode();
    this.updateDemoBanner();

    // Initialize Lucide icons
    if (window.lucide) lucide.createIcons();

    // Bind DOM events
    this._bindEvents();

    // Check backend health
    await this.checkBackendStatus();

    // Load configured providers
    await Providers.load();

    // Check if we should default to demo mode if no providers configured
    if (!this._isDemoMode && Providers.getList().length === 0) {
      // Auto enable demo mode on clean startup so user immediately sees live graphs
      this._isDemoMode = true;
      Storage.setDemoMode(true);
      this.updateDemoBanner();
      Alerts.toast('Modo Demonstração ativado automaticamente (nenhuma chave configurada).', 'info');
    }

    // Load initial data for current page
    await this.refresh();

    // Initialize real-time SSE stream
    this._initSSE();

    // Start auto-refresh polling as fallback
    this.startAutoRefresh();
  },

  _initSSE() {
    if (this._isDemoMode) return;
    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }
    this._eventSource = API.connectRealtime(
      (data) => {
        if (data.type === 'metrics_tick' && this._currentPage === 'dashboard' && !this._isDemoMode) {
          if (data.summary) {
            Metrics.renderUsageCards(data.summary, this._latestSummary?.limits || {});
            Metrics.renderMiniCards(data.summary.today);
          }
          if (data.projection) {
            Metrics.renderProjection(data.projection);
          }
          this.updateTimestamp();
        }
      },
      () => {
        // Fallback gracefully to timer polling
      }
    );
  },

  updateDemoBanner() {
    const banner = document.getElementById('demo-banner');
    const toggleBtnTxt = document.getElementById('txt-demo-toggle');
    if (!banner || !toggleBtnTxt) return;

    if (this._isDemoMode) {
      banner.classList.remove('hidden');
      toggleBtnTxt.textContent = 'Modo Real';
    } else {
      banner.classList.add('hidden');
      toggleBtnTxt.textContent = 'Demo Mode';
    }
  },

  async checkBackendStatus() {
    const dot = document.getElementById('backend-status-dot');
    const txt = document.getElementById('backend-status-text');
    const { data, error } = await API.ping();

    if (error) {
      if (dot) {
        dot.className = 'status-indicator-dot offline';
      }
      if (txt) txt.textContent = 'Backend Offline';
    } else {
      if (dot) {
        dot.className = 'status-indicator-dot online';
      }
      if (txt) txt.textContent = 'Backend Conectado';
    }
  },

  /**
   * Navigation Controller
   */
  navigate(pageId) {
    this._currentPage = pageId;

    // Update Nav Buttons
    document.querySelectorAll('.nav-item').forEach((btn) => {
      if (btn.getAttribute('data-page') === pageId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Update Pages Visibility
    document.querySelectorAll('.page-content').forEach((sec) => {
      if (sec.id === `page-${pageId}`) {
        sec.classList.add('active');
      } else {
        sec.classList.remove('active');
      }
    });

    // Update Topbar Heading
    const titleEl = document.getElementById('page-title');
    const headings = {
      dashboard: 'Dashboard de Uso',
      models: 'Modelos de Inteligência Artificial',
      logs: 'Histórico de Requisições',
      health: 'Disponibilidade e Status das APIs',
      settings: 'Configurações do Monitor',
    };
    if (titleEl) titleEl.textContent = headings[pageId] || 'AI Usage Monitor';

    this.refresh();
  },

  /**
   * Main Refresh Cycle
   */
  async refresh() {
    const icon = document.getElementById('icon-refresh');
    if (icon) icon.style.animation = 'spin 0.6s linear';

    const provider = Storage.getSelectedProvider();

    try {
      if (this._currentPage === 'dashboard') {
        await this._loadDashboard(provider);
      } else if (this._currentPage === 'models') {
        await this._loadModels(provider);
      } else if (this._currentPage === 'logs') {
        await this._loadLogs(provider);
      } else if (this._currentPage === 'health') {
        await this._loadHealth();
      } else if (this._currentPage === 'settings') {
        await this._loadSettings();
      }

      // Update timestamp
      const timeEl = document.getElementById('last-update-time');
      if (timeEl) timeEl.textContent = Utils.formatTime(new Date().toISOString());
    } finally {
      if (icon) {
        setTimeout(() => {
          icon.style.animation = '';
        }, 600);
      }
      if (window.lucide) lucide.createIcons();
    }
  },

  async _loadDashboard(provider) {
    let summary;
    let timeseries;
    let anomalies;

    if (this._isDemoMode) {
      const demo = await API.getDemoData();
      summary = demo.data || {};
      timeseries = summary.timeseries || [];
      anomalies = summary.anomalies || [];
    } else {
      const [sumRes, timeRes, anomRes] = await Promise.all([
        API.getSummary(provider),
        API.getTimeseries(provider, 24),
        API.getAnomalies(),
      ]);
      summary = sumRes.data || {};
      timeseries = timeRes.data || [];
      anomalies = anomRes.data || [];
    }

    this._latestSummary = summary;

    // Render components
    Metrics.renderUsageCards(summary.summary || {}, summary.limits || {});
    Metrics.renderMiniCards(summary.summary?.today || {});
    Metrics.renderProjection(summary.projection || {});
    Alerts.renderAnomalies(document.getElementById('anomalies-container'), anomalies);

    // Render charts
    Charts.renderTimeline('chart-timeline', timeseries);
    Charts.renderProviders('chart-providers', summary.byProvider || []);
    Charts.renderInputOutput('chart-input-output', timeseries);
    Charts.renderHourly('chart-hourly', timeseries);
  },

  async _loadModels(provider) {
    if (this._isDemoMode) {
      const demo = await API.getDemoData();
      Metrics.setModelsData(demo.data?.byModel || []);
    } else {
      const { data } = await API.getModels(provider);
      Metrics.setModelsData(data || []);
    }
  },

  async _loadLogs(provider) {
    const statusVal = document.getElementById('filter-log-status')?.value || '';
    const res = await API.getLogs({
      provider: provider,
      status: statusVal,
      limit: this._logsLimit,
      offset: this._logsOffset,
    });
    const logs = res.data?.items || [];
    const total = res.data?.total || 0;
    Metrics.renderLogsTable(logs, total, this._logsOffset, this._logsLimit);
  },

  async _loadHealth() {
    const { data } = await API.getHealth();
    Metrics.renderHealthCards(data || []);

    // Update sidebar dot
    const badge = document.getElementById('health-badge');
    if (badge && data) {
      const hasOffline = data.some((h) => h.status === 'OFFLINE');
      const hasDegraded = data.some((h) => h.status === 'DEGRADED');
      if (hasOffline) badge.className = 'badge-status-dot offline';
      else if (hasDegraded) badge.className = 'badge-status-dot degraded';
      else badge.className = 'badge-status-dot online';
    }
  },

  async _loadSettings() {
    await Providers.load();
    const { data } = await API.getAlertConfigs();
    const listEl = document.getElementById('settings-alerts-list');
    if (!listEl) return;

    listEl.textContent = '';

    if (!data || data.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'text-muted text-center';
      empty.style.padding = '16px';
      empty.textContent = 'Nenhuma regra configurada.';
      listEl.appendChild(empty);
      return;
    }

    data.forEach((a) => {
      const item = document.createElement('div');
      item.className = 'alert-config-item';

      const left = document.createElement('div');
      const strong = document.createElement('strong');
      strong.textContent = a.metric;
      const span = document.createElement('span');
      span.style.color = 'var(--text-dim)';
      span.style.marginLeft = '6px';
      span.textContent = `Limite: ${a.threshold}`;
      left.appendChild(strong);
      left.appendChild(span);

      const btn = document.createElement('button');
      btn.className = 'btn btn-danger btn-sm';
      const icon = document.createElement('i');
      icon.setAttribute('data-lucide', 'trash-2');
      btn.appendChild(icon);
      btn.addEventListener('click', () => this.deleteAlert(a.id));

      item.appendChild(left);
      item.appendChild(btn);
      listEl.appendChild(item);
    });

    if (window.lucide) lucide.createIcons();
  },

  async openModelDetail(provider, modelId) {
    const modal = document.getElementById('modal-model-detail');
    if (!modal) return;

    modal.classList.remove('hidden');

    if (this._isDemoMode) {
      const demo = await API.getDemoData();
      const model = demo.data?.byModel?.find((m) => m.model === modelId) || {
        model: modelId,
        provider: provider,
      };
      Metrics.renderModelModal({
        model: model.model,
        provider: model.provider,
        overview: { name: model.model, status: 'ONLINE', contextWindow: 128000, maxTokens: 8192 },
        usage: { requests: model.requests, inputTokens: model.inputTokens, outputTokens: model.outputTokens, totalTokens: model.totalTokens },
        performance: { avgLatency: model.latency, p50: model.latency * 0.9, p95: model.latency * 1.3, p99: model.latency * 1.8 },
        reliability: { successRate: 1 - model.errorRate, errorRate: model.errorRate },
        limits: { rpm: 500, tpm: 150000 },
        cost: { inputCost: model.cost * 0.7, outputCost: model.cost * 0.3, totalCost: model.cost },
      });
    } else {
      const { data } = await API.getModelDetail(provider, modelId);
      Metrics.renderModelModal(data);
    }
  },

  closeModal() {
    const modal = document.getElementById('modal-model-detail');
    if (modal) modal.classList.add('hidden');
  },

  async deleteAlert(id) {
    await API.deleteAlertConfig(id);
    Alerts.toast('Regra de alerta removida.', 'info');
    await this._loadSettings();
  },

  startAutoRefresh() {
    this.stopAutoRefresh();
    const interval = Storage.getRefreshInterval();
    if (interval > 0) {
      this._refreshTimer = setInterval(() => this.refresh(), interval);
    }
  },

  stopAutoRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  },

  /**
   * Bind DOM Events
   */
  _bindEvents() {
    // Navigation items
    document.querySelectorAll('.nav-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const page = btn.getAttribute('data-page');
        this.navigate(page);
      });
    });

    // Refresh Button
    document.getElementById('btn-refresh')?.addEventListener('click', () => this.refresh());

    // Demo Mode Toggles
    document.getElementById('btn-toggle-demo')?.addEventListener('click', () => {
      this._isDemoMode = !this._isDemoMode;
      Storage.setDemoMode(this._isDemoMode);
      this.updateDemoBanner();
      Alerts.toast(this._isDemoMode ? 'Modo Demonstração ATIVADO.' : 'Modo Demonstração DESATIVADO (Modo Real).', 'info');
      this.refresh();
    });

    document.getElementById('btn-exit-demo')?.addEventListener('click', () => {
      this._isDemoMode = false;
      Storage.setDemoMode(false);
      this.updateDemoBanner();
      Alerts.toast('Modo Demonstração DESATIVADO (Modo Real).', 'info');
      this.refresh();
    });

    // Global Provider Selector
    document.getElementById('select-global-provider')?.addEventListener('change', (e) => {
      Storage.setSelectedProvider(e.target.value);
      this.refresh();
    });

    // Export Dropdown Trigger
    const btnExport = document.getElementById('btn-export');
    const menuExport = document.getElementById('export-menu');
    btnExport?.addEventListener('click', (e) => {
      e.stopPropagation();
      menuExport?.classList.toggle('hidden');
    });

    document.addEventListener('click', () => {
      menuExport?.classList.add('hidden');
    });

    // Export Actions
    document.getElementById('export-csv')?.addEventListener('click', () => {
      Export.downloadCSV(Storage.getSelectedProvider());
    });
    document.getElementById('export-json')?.addEventListener('click', () => {
      Export.downloadJSON(Storage.getSelectedProvider());
    });
    document.getElementById('export-report')?.addEventListener('click', () => {
      Export.downloadReport(this._latestSummary);
    });

    // Timeline metric pill toggles
    document.querySelectorAll('.chart-legend-controls .pill').forEach((pill) => {
      pill.addEventListener('click', (e) => {
        document.querySelectorAll('.chart-legend-controls .pill').forEach((p) => p.classList.remove('pill-active'));
        pill.classList.add('pill-active');
        const metric = pill.getAttribute('data-metric');
        Charts.setTimelineMetric(metric);
        this.refresh();
      });
    });

    // Models Table Search
    document.getElementById('filter-models-input')?.addEventListener(
      'input',
      Utils.debounce((e) => {
        Metrics.renderModelsTable(e.target.value);
      }, 200)
    );

    // Models Table Sort Headers
    document.querySelectorAll('#table-models th[data-sort]').forEach((th) => {
      th.addEventListener('click', () => {
        const col = th.getAttribute('data-sort');
        Metrics.sortModels(col);
      });
    });

    // Logs Filters
    document.getElementById('filter-log-provider')?.addEventListener('change', () => {
      this._logsOffset = 0;
      this._loadLogs();
    });
    document.getElementById('filter-log-status')?.addEventListener('change', () => {
      this._logsOffset = 0;
      this._loadLogs();
    });

    // Logs Pagination
    document.getElementById('btn-prev-page')?.addEventListener('click', () => {
      if (this._logsOffset >= this._logsLimit) {
        this._logsOffset -= this._logsLimit;
        this._loadLogs();
      }
    });
    document.getElementById('btn-next-page')?.addEventListener('click', () => {
      this._logsOffset += this._logsLimit;
      this._loadLogs();
    });

    // Clear Logs Button
    document.getElementById('btn-clear-logs')?.addEventListener('click', async () => {
      if (confirm('Tem certeza de que deseja apagar todo o histórico de logs?')) {
        await API.clearLogs();
        Alerts.toast('Histórico de logs limpo com sucesso.', 'info');
        this._logsOffset = 0;
        this._loadLogs();
      }
    });

    // Health Test Button
    document.getElementById('btn-health-check-now')?.addEventListener('click', () => {
      this._loadHealth();
      Alerts.toast('Checagem de conexões disparada.', 'info');
    });

    // Modal Close
    document.getElementById('modal-close')?.addEventListener('click', () => this.closeModal());
    document.getElementById('modal-model-detail')?.addEventListener('click', (e) => {
      if (e.target.id === 'modal-model-detail') this.closeModal();
    });

    // Settings: Provider Form
    document.getElementById('form-provider')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const type = document.getElementById('input-provider-type').value;
      const name = document.getElementById('input-provider-name').value;
      const key = document.getElementById('input-provider-key').value;
      const url = document.getElementById('input-provider-url').value;

      const success = await Providers.add({
        name: type,
        display_name: name,
        api_key: key || null,
        base_url: url || null,
      });

      if (success) {
        document.getElementById('input-provider-key').value = '';
        this._loadSettings();
      }
    });

    // Settings: Toggle Password visibility
    document.getElementById('btn-toggle-key')?.addEventListener('click', () => {
      const inp = document.getElementById('input-provider-key');
      if (inp) {
        inp.type = inp.type === 'password' ? 'text' : 'password';
      }
    });

    // Settings: Alert Form
    document.getElementById('form-alert')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const metric = document.getElementById('input-alert-metric').value;
      const threshold = parseFloat(document.getElementById('input-alert-threshold').value);

      await API.addAlertConfig({
        provider: 'all',
        metric: metric,
        threshold: threshold,
      });

      Alerts.toast('Regra de alerta adicionada!', 'success');
      document.getElementById('input-alert-threshold').value = '';
      this._loadSettings();
    });

    // Settings: Refresh Interval
    const selInterval = document.getElementById('select-refresh-interval');
    if (selInterval) {
      selInterval.value = Storage.getRefreshInterval();
      selInterval.addEventListener('change', (e) => {
        Storage.setRefreshInterval(e.target.value);
        this.startAutoRefresh();
        Alerts.toast('Intervalo de atualização salvo!', 'info');
      });
    }

    // Settings: Admin API Key
    const inpAdminKey = document.getElementById('input-admin-key');
    if (inpAdminKey) {
      inpAdminKey.value = Storage.get('aum_admin_key', '');
    }
    document.getElementById('btn-save-admin-key')?.addEventListener('click', () => {
      const val = document.getElementById('input-admin-key')?.value?.trim() || '';
      Storage.set('aum_admin_key', val);
      Alerts.toast(val ? 'Chave Administrativa salva localmente!' : 'Chave Administrativa removida.', 'success');
    });
  },
};

// Global App kickoff on DOM ready
document.addEventListener('DOMContentLoaded', () => App.init());
