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
    // Check JWT authentication
    const token = localStorage.getItem('tp_token');
    if (!token) {
      window.location.href = '/login.html';
      return;
    }

    const username = localStorage.getItem('tp_username') || 'admin';
    const userDisplay = document.getElementById('user-display-name');
    if (userDisplay) userDisplay.textContent = username;

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

  async _initSSE() {
    if (this._isDemoMode) {
      this._setSseStatus('disconnected', 'DEMO');
      return;
    }
    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }
    this._setSseStatus(null, 'CONECTANDO');
    this._eventSource = await API.connectRealtime(
      (data) => {
        this._setSseStatus('connected', 'AO VIVO');
        if ((data.type === 'request.completed' || data.type === 'request.failed') && !this._isDemoMode) {
          if (this._currentPage === 'dashboard') {
            this.refresh();
          } else if (this._currentPage === 'logs') {
            this._loadLogs();
          }
          if (data.type === 'request.completed' && data.data) {
            Alerts.toast(`⚡ Telemetria recebida: ${data.data.provider?.toUpperCase()} • ${data.data.model} (${data.data.latency_ms}ms)`, 'info', 2500);
          }
        } else if (data.type === 'metrics_tick' && this._currentPage === 'dashboard' && !this._isDemoMode) {
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
        this._setSseStatus('disconnected', 'DESCONECTADO');
        // Fallback gracefully to timer polling
      }
    );
  },

  _setSseStatus(state, label) {
    const el = document.getElementById('sse-indicator');
    const txt = document.getElementById('sse-status-text');
    if (!el) return;
    el.classList.remove('connected', 'disconnected');
    if (state) el.classList.add(state);
    if (txt) txt.textContent = label;
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

    // Close mobile sidebar if open
    document.getElementById('sidebar')?.classList.remove('open');

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

    const errBanner = document.getElementById('dashboard-error-banner');
    const errMsg = document.getElementById('dashboard-error-msg');

    if (this._isDemoMode) {
      if (errBanner) errBanner.classList.add('hidden');
      const demo = await API.getDemoData();
      summary = demo.data || {};
      timeseries = summary.timeseries || [];
      anomalies = summary.anomalies || [];
    } else {
      Metrics.showSkeletonLoading();
      const [sumRes, timeRes, anomRes] = await Promise.all([
        API.getSummary(provider),
        API.getTimeseries(provider, null, 24),
        API.getAnomalies(),
      ]);
      Metrics.hideSkeletonLoading();

      if (sumRes.error) {
        if (errBanner) {
          errBanner.classList.remove('hidden');
          if (errMsg) errMsg.textContent = sumRes.error.message || 'Falha ao conectar com o backend.';
        }
      } else {
        if (errBanner) errBanner.classList.add('hidden');
      }

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

    // Render Cache Savings
    if (!this._isDemoMode) {
      API.getCacheStats().then((res) => {
        if (res && res.data) {
          const cStats = res.data;
          const savingsEl = document.getElementById('mini-cache-savings');
          const hitRateEl = document.getElementById('mini-cache-hit-rate');
          if (savingsEl) savingsEl.textContent = `$${Number(cStats.total_saved_cost_usd || 0).toFixed(4)}`;
          if (hitRateEl) hitRateEl.textContent = `${cStats.cache_hit_rate_pct || 0}% hit rate (${cStats.total_hits || 0} hits)`;
        }
      });
    }

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
      span.textContent = `Limite: ${a.threshold}${a.webhook_url ? ' • Webhook ativo' : ''}`;
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

    // Render Client Keys (Ticket 05)
    const keysContainer = document.getElementById('client-keys-list');
    if (keysContainer) {
      keysContainer.textContent = '';
      const { data: clientKeys } = await API.getClientKeys();
      if (!clientKeys || clientKeys.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-muted text-center';
        empty.style.padding = '16px';
        empty.textContent = 'Nenhuma chave de cliente emitida.';
        keysContainer.appendChild(empty);
      } else {
        clientKeys.forEach((k) => {
          const item = document.createElement('div');
          item.className = 'configured-provider-item';

          const left = document.createElement('div');
          const strong = document.createElement('strong');
          strong.textContent = k.name;
          const badge = document.createElement('span');
          badge.className = k.enabled ? 'badge-tag' : 'badge-tag text-muted';
          badge.style.marginLeft = '8px';
          badge.textContent = k.enabled ? 'Ativa' : 'Desabilitada';

          const prefixDiv = document.createElement('div');
          prefixDiv.style.fontFamily = 'var(--font-mono)';
          prefixDiv.style.fontSize = '12px';
          prefixDiv.style.color = 'var(--accent)';
          prefixDiv.style.marginTop = '2px';
          prefixDiv.textContent = `Prefixo: ${k.key_prefix} (RPM: ${k.rate_limit_rpm || '∞'})`;

          left.appendChild(strong);
          left.appendChild(badge);
          left.appendChild(prefixDiv);

          const actions = document.createElement('div');
          actions.className = 'flex-row gap-2';

          const btnToggle = document.createElement('button');
          btnToggle.type = 'button';
          btnToggle.className = 'btn btn-secondary btn-sm';
          btnToggle.textContent = k.enabled ? 'Desativar' : 'Ativar';
          btnToggle.addEventListener('click', async () => {
            await API.toggleClientKey(k.id);
            this._loadSettings();
          });

          const btnDel = document.createElement('button');
          btnDel.type = 'button';
          btnDel.className = 'btn btn-danger btn-sm';
          btnDel.textContent = 'Revogar';
          btnDel.addEventListener('click', async () => {
            if (confirm(`Deseja revogar a chave ${k.name}?`)) {
              await API.deleteClientKey(k.id);
              Alerts.toast(`Chave ${k.name} revogada.`, 'info');
              this._loadSettings();
            }
          });

          actions.appendChild(btnToggle);
          actions.appendChild(btnDel);
          item.appendChild(left);
          item.appendChild(actions);
          keysContainer.appendChild(item);
        });
      }
    }

    // Render Fallback Rules
    const fbContainer = document.getElementById('fallback-rules-list');
    if (fbContainer) {
      fbContainer.replaceChildren();
      const { data: fbRules } = await API.getFallbackRules();
      if (!fbRules || fbRules.length === 0) {
        const emptyP = document.createElement('p');
        emptyP.className = 'text-muted text-sm';
        emptyP.style.padding = '8px 0';
        emptyP.textContent = 'Nenhuma regra de fallback configurada.';
        fbContainer.appendChild(emptyP);
      } else {
        fbRules.forEach((r) => {
          const item = document.createElement('div');
          item.className = 'configured-provider-item';

          const left = document.createElement('div');
          const strong = document.createElement('strong');
          strong.textContent = `${r.source_provider}/${r.source_model} ➔ ${r.target_provider}/${r.target_model}`;

          const badge = document.createElement('span');
          badge.className = r.enabled ? 'badge-tag' : 'badge-tag text-muted';
          badge.style.marginLeft = '8px';
          badge.textContent = r.enabled ? `Prioridade ${r.priority}` : 'Desabilitada';

          left.appendChild(strong);
          left.appendChild(badge);

          const actions = document.createElement('div');
          actions.className = 'flex-row gap-2';

          const btnToggle = document.createElement('button');
          btnToggle.type = 'button';
          btnToggle.className = 'btn btn-secondary btn-sm';
          btnToggle.textContent = r.enabled ? 'Desativar' : 'Ativar';
          btnToggle.addEventListener('click', async () => {
            await API.toggleFallbackRule(r.id);
            this._loadSettings();
          });

          const btnDel = document.createElement('button');
          btnDel.type = 'button';
          btnDel.className = 'btn btn-danger btn-sm';
          btnDel.textContent = 'Excluir';
          btnDel.addEventListener('click', async () => {
            if (confirm(`Excluir regra de fallback ${r.source_model} ➔ ${r.target_model}?`)) {
              await API.deleteFallbackRule(r.id);
              Alerts.toast('Regra de fallback excluída.', 'info');
              this._loadSettings();
            }
          });

          actions.appendChild(btnToggle);
          actions.appendChild(btnDel);
          item.appendChild(left);
          item.appendChild(actions);
          fbContainer.appendChild(item);
        });
      }
    }

    // Render Cache Config & Stats
    const cacheStatsText = document.getElementById('cache-stats-text');
    const inputCacheEnabled = document.getElementById('input-cache-enabled');
    const inputCacheTtl = document.getElementById('input-cache-ttl');

    if (cacheStatsText) {
      const [{ data: cStats }, { data: cConfig }] = await Promise.all([
        API.getCacheStats(),
        API.getCacheConfig(),
      ]);

      if (cConfig) {
        if (inputCacheEnabled) inputCacheEnabled.value = String(cConfig.enabled);
        if (inputCacheTtl) inputCacheTtl.value = cConfig.default_ttl_seconds || 3600;
      }

      if (cStats) {
        cacheStatsText.textContent = `${cStats.active_entries} entradas ativas | ${cStats.total_hits} hits | $${cStats.total_saved_cost_usd} economizados (${cStats.cache_hit_rate_pct}% taxa de acerto)`;
      } else {
        cacheStatsText.textContent = 'Não foi possível carregar estatísticas do cache.';
      }
    }

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
    // Mobile Hamburger Menu
    document.getElementById('btn-hamburger')?.addEventListener('click', (e) => {
      e.stopPropagation();
      document.getElementById('sidebar')?.classList.toggle('open');
    });
    document.addEventListener('click', (e) => {
      const sidebar = document.getElementById('sidebar');
      if (sidebar && !sidebar.contains(e.target) && !e.target.closest('#btn-hamburger')) {
        sidebar.classList.remove('open');
      }
    });

    // Navigation items
    document.querySelectorAll('.nav-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const page = btn.getAttribute('data-page');
        this.navigate(page);
      });
    });

    // Refresh Button & Retry Button
    document.getElementById('btn-refresh')?.addEventListener('click', () => this.refresh());
    document.getElementById('btn-retry-dashboard')?.addEventListener('click', () => this.refresh());

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

    // Logout Button
    document.getElementById('btn-logout')?.addEventListener('click', () => {
      localStorage.removeItem('tp_token');
      localStorage.removeItem('tp_username');
      window.location.href = '/login.html';
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
      const webhook = document.getElementById('input-alert-webhook')?.value?.trim() || null;

      await API.addAlertConfig({
        provider: 'all',
        metric: metric,
        threshold: threshold,
        webhook_url: webhook,
      });

      Alerts.toast('Regra de alerta adicionada!', 'success');
      document.getElementById('input-alert-threshold').value = '';
      if (document.getElementById('input-alert-webhook')) {
        document.getElementById('input-alert-webhook').value = '';
      }
      this._loadSettings();
    });

    // Settings: Create Client API Key
    document.getElementById('form-create-client-key')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('input-client-key-name')?.value?.trim();
      const rpm = parseInt(document.getElementById('input-client-key-rpm')?.value, 10) || 60;
      if (!name) return;

      const res = await API.createClientKey({ name, rate_limit_rpm: rpm });
      if (res.error) {
        Alerts.toast(res.error.message || 'Erro ao emitir chave.', 'error');
        return;
      }

      const fullKey = res.data.api_key;
      prompt('COPIE SUA CHAVE VIRTUAL TOKENPULSE (Não será exibida novamente):', fullKey);
      Alerts.toast('Chave virtual emitida com sucesso!', 'success');
      document.getElementById('input-client-key-name').value = '';
      this._loadSettings();
    });

    // Settings: Create Fallback Rule
    document.getElementById('form-create-fallback-rule')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const source_provider = document.getElementById('input-fb-source-provider')?.value?.trim();
      const source_model = document.getElementById('input-fb-source-model')?.value?.trim();
      const target_provider = document.getElementById('input-fb-target-provider')?.value?.trim();
      const target_model = document.getElementById('input-fb-target-model')?.value?.trim();
      const priority = parseInt(document.getElementById('input-fb-priority')?.value, 10) || 1;

      if (!source_provider || !source_model || !target_provider || !target_model) return;

      const res = await API.createFallbackRule({
        source_provider,
        source_model,
        target_provider,
        target_model,
        priority,
        enabled: true,
      });

      if (res.error) {
        Alerts.toast(res.error.message || 'Erro ao criar regra de fallback.', 'error');
        return;
      }

      Alerts.toast('Regra de fallback criada com sucesso!', 'success');
      document.getElementById('input-fb-source-model').value = '';
      document.getElementById('input-fb-target-model').value = '';
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

    // Settings: Save Cache Config
    document.getElementById('form-cache-config')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const enabled = document.getElementById('input-cache-enabled')?.value === 'true';
      const ttl = parseInt(document.getElementById('input-cache-ttl')?.value, 10) || 3600;

      const res = await API.updateCacheConfig({ enabled, default_ttl: ttl });
      if (res.error) {
        Alerts.toast(res.error.message || 'Erro ao salvar configuração do cache.', 'error');
        return;
      }
      Alerts.toast('Configuração de cache atualizada com sucesso!', 'success');
      this._loadSettings();
    });

    // Settings: Flush Cache
    document.getElementById('btn-flush-cache')?.addEventListener('click', async () => {
      if (confirm('Tem certeza que deseja invalidar e apagar todas as entradas de cache do Gateway?')) {
        const res = await API.flushCache();
        if (res.error) {
          Alerts.toast(res.error.message || 'Erro ao limpar cache.', 'error');
          return;
        }
        Alerts.toast(res.data?.message || 'Cache limpo com sucesso!', 'success');
        this._loadSettings();
      }
    });

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

    // Settings: Change Admin Password
    document.getElementById('form-change-password')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const current = document.getElementById('input-current-password')?.value || '';
      const next = document.getElementById('input-new-password')?.value || '';
      const btn = document.getElementById('btn-change-password');
      if (btn) btn.disabled = true;

      const res = await API.changePassword(current, next);
      if (btn) btn.disabled = false;

      if (res.error) {
        Alerts.toast(res.error.message || 'Erro ao alterar senha.', 'error');
      } else {
        Alerts.toast('Senha alterada com sucesso!', 'success');
        document.getElementById('input-current-password').value = '';
        document.getElementById('input-new-password').value = '';
      }
    });

    // Settings: Prune Logs (>90 days)
    document.getElementById('btn-prune-logs')?.addEventListener('click', async () => {
      if (confirm('Deseja expurgar logs anteriores a 90 dias?')) {
        const res = await API.pruneLogs(90);
        if (res.error) {
          Alerts.toast(res.error.message || 'Erro ao expurgar logs.', 'error');
        } else {
          Alerts.toast(`Logs expurgados! Registros removidos: ${res.data?.deleted_count || 0}`, 'success');
          this._logsOffset = 0;
          this.refresh();
        }
      }
    });

    // Settings: Clear all logs
    document.getElementById('btn-clear-all-logs')?.addEventListener('click', async () => {
      if (confirm('Atenção: deseja realmente limpar TODOS os logs do sistema?')) {
        const res = await API.clearLogs();
        if (res.error) {
          Alerts.toast(res.error.message || 'Erro ao limpar logs.', 'error');
        } else {
          Alerts.toast('Todos os logs foram apagados com sucesso.', 'info');
          this._logsOffset = 0;
          this.refresh();
        }
      }
    });
  },
};

// Global App kickoff on DOM ready
document.addEventListener('DOMContentLoaded', () => App.init());
