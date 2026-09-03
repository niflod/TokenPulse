/**
 * js/api.js — HTTP Client for backend communication with retry, admin key support, and SSE.
 */

const API = {
  BASE_URL: (() => {
    if (window.location.protocol === 'file:') return 'http://127.0.0.1:8000';
    if (window.location.port !== '8000' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
      return `http://${window.location.hostname}:8000`;
    }
    return '';
  })(),

  async _request(endpoint, options = {}, timeoutMs = 15000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const url = `${this.BASE_URL}${endpoint}`;
      const defaultHeaders = { 'Content-Type': 'application/json' };

      // JWT auth token
      const token = localStorage.getItem('tp_token');
      if (token) {
        defaultHeaders['Authorization'] = `Bearer ${token}`;
      }

      // Optional Admin Key from non-sensitive preference storage
      const adminKey = window.Storage ? Storage.get('aum_admin_key') : null;
      if (adminKey) {
        defaultHeaders['X-Admin-Key'] = adminKey;
      }

      const config = {
        ...options,
        signal: controller.signal,
        headers: { ...defaultHeaders, ...(options.headers || {}) },
      };

      const res = await fetch(url, config);
      clearTimeout(timeoutId);

      // Redirect to login on authentication failure
      if (res.status === 401) {
        localStorage.removeItem('tp_token');
        localStorage.removeItem('tp_username');
        window.location.href = '/login.html';
        return { data: null, error: { status: 401, message: 'Sessão expirada.' } };
      }

      if (res.status === 204) {
        return { data: null, error: null };
      }

      const isJson = res.headers.get('content-type')?.includes('application/json');
      const data = isJson ? await res.json() : await res.text();

      if (!res.ok) {
        const errorMsg = data?.detail || `HTTP ${res.status}: ${res.statusText}`;
        return { data: null, error: { status: res.status, message: errorMsg } };
      }

      return { data, error: null };
    } catch (err) {
      clearTimeout(timeoutId);
      const isTimeout = err.name === 'AbortError';
      return {
        data: null,
        error: {
          status: 0,
          message: isTimeout
            ? 'Tempo limite de conexão esgotado (timeout).'
            : 'Falha de conexão com o servidor backend. Verifique se o backend está em execução.',
        },
      };
    }
  },

  async ping() {
    return this._request('/api/ping');
  },

  async getProviders() {
    return this._request('/api/providers');
  },

  async addProvider(payload) {
    return this._request('/api/providers', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async deleteProvider(name) {
    return this._request(`/api/providers/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
  },

  async toggleProvider(name) {
    return this._request(`/api/providers/${encodeURIComponent(name)}/toggle`, {
      method: 'PUT',
    });
  },

  async getHealth() {
    return this._request('/api/health');
  },

  async getMetricsSummary(provider = null, model = null) {
    const params = new URLSearchParams();
    if (provider) params.append('provider', provider);
    if (model) params.append('model', model);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this._request(`/api/metrics/summary${qs}`);
  },

  async getSummary(provider = null, model = null) {
    return this.getMetricsSummary(provider, model);
  },

  async getTimeseries(provider = null, model = null, hours = 24) {
    const params = new URLSearchParams({ hours });
    if (provider) params.append('provider', provider);
    if (model) params.append('model', model);
    return this._request(`/api/metrics/timeseries?${params.toString()}`);
  },

  async getAnomalies() {
    return this._request('/api/metrics/anomalies');
  },

  async getDemoData() {
    return this._request('/api/metrics/demo');
  },

  async getModels(provider = null) {
    const params = new URLSearchParams();
    if (provider) params.append('provider', provider);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this._request(`/api/models${qs}`);
  },

  async getModelDetail(provider, modelId) {
    return this._request(`/api/models/${encodeURIComponent(provider)}/${encodeURIComponent(modelId)}`);
  },

  async getLogs(params = {}) {
    const q = new URLSearchParams(params);
    return this._request(`/api/logs?${q.toString()}`);
  },

  async clearLogs() {
    return this._request('/api/logs?confirm=true', { method: 'DELETE' });
  },

  async getAlerts() {
    return this._request('/api/alerts');
  },

  async getAlertConfigs() {
    return this._request('/api/alerts/config');
  },

  async createAlertConfig(payload) {
    return this._request('/api/alerts/config', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async deleteAlertConfig(id) {
    return this._request(`/api/alerts/config/${id}`, {
      method: 'DELETE',
    });
  },

  async pruneLogs(retentionDays = 90) {
    return this._request('/api/logs/prune', {
      method: 'POST',
      body: JSON.stringify({ retention_days: retentionDays }),
    });
  },

  async changePassword(currentPassword, newPassword) {
    return this._request('/api/auth/password', {
      method: 'PUT',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
  },

  exportCSV(provider = '') {
    const token = localStorage.getItem('tp_token') || '';
    const qs = new URLSearchParams();
    if (provider) qs.append('provider', provider);
    if (token) qs.append('token', token);
    const url = `${this.BASE_URL}/api/export/csv?${qs.toString()}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = `tokenpulse_export_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  },

  exportJSON(provider = '') {
    const token = localStorage.getItem('tp_token') || '';
    const qs = new URLSearchParams();
    if (provider) qs.append('provider', provider);
    if (token) qs.append('token', token);
    const url = `${this.BASE_URL}/api/export/json?${qs.toString()}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = `tokenpulse_export_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  },

  /**
   * Connect to Server-Sent Events (SSE) stream for real-time telemetry updates.
   */
  connectRealtime(onEvent, onError) {
    const token = localStorage.getItem('tp_token');
    const qs = token ? `?token=${encodeURIComponent(token)}` : '';
    const url = `${this.BASE_URL}/api/realtime/stream${qs}`;
    try {
      const eventSource = new EventSource(url);
      eventSource.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data);
          if (onEvent) onEvent(payload);
        } catch (parseErr) {
          console.error('SSE JSON parse error:', parseErr);
        }
      };
      eventSource.onerror = (err) => {
        if (onError) onError(err);
      };
      return eventSource;
    } catch (err) {
      if (onError) onError(err);
      return null;
    }
  },

  // Client API Keys
  async getClientKeys() {
    return this._request('/api/keys');
  },

  async createClientKey(data) {
    return this._request('/api/keys', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async deleteClientKey(id) {
    return this._request(`/api/keys/${id}`, { method: 'DELETE' });
  },

  async toggleClientKey(id) {
    return this._request(`/api/keys/${id}/toggle`, { method: 'PUT' });
  },
};
