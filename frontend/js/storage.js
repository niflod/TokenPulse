/**
 * js/storage.js — Local storage manager for user preferences only.
 * IMPORTANT: NEVER store API keys in the browser localStorage.
 */

const Storage = {
  KEYS: {
    REFRESH_INTERVAL: 'ai_monitor_refresh_interval',
    DEMO_MODE: 'ai_monitor_demo_mode',
    SELECTED_PROVIDER: 'ai_monitor_selected_provider',
  },

  get(key, defaultValue = null) {
    try {
      const val = localStorage.getItem(key);
      return val !== null ? JSON.parse(val) : defaultValue;
    } catch (e) {
      return defaultValue;
    }
  },

  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      console.warn('Failed to write to localStorage', e);
    }
  },

  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch (e) {
      console.warn('Failed to delete from localStorage', e);
    }
  },

  getRefreshInterval() {
    return this.get(this.KEYS.REFRESH_INTERVAL, 30000);
  },

  setRefreshInterval(val) {
    this.set(this.KEYS.REFRESH_INTERVAL, Number(val));
  },

  getDemoMode() {
    return this.get(this.KEYS.DEMO_MODE, false);
  },

  setDemoMode(val) {
    this.set(this.KEYS.DEMO_MODE, Boolean(val));
  },

  getSelectedProvider() {
    return this.get(this.KEYS.SELECTED_PROVIDER, '');
  },

  setSelectedProvider(val) {
    this.set(this.KEYS.SELECTED_PROVIDER, val || '');
  }
};
