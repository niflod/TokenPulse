/**
 * js/utils.js — Formatting, date conversions and display helpers.
 */

const Utils = {
  /**
   * Format numbers with abbreviations (e.g. 1.2M, 45.2K)
   */
  formatNumber(n) {
    if (n === null || n === undefined) return 'N/D';
    if (typeof n !== 'number') n = Number(n);
    if (isNaN(n)) return 'N/D';
    
    if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + 'B';
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
    return n.toLocaleString('pt-BR');
  },

  /**
   * Format token counts with suffix
   */
  formatTokens(n) {
    if (n === null || n === undefined) return 'N/D';
    return this.formatNumber(n) + ' tok';
  },

  /**
   * Format USD currency
   */
  formatCost(n) {
    if (n === null || n === undefined) return 'N/D';
    if (typeof n !== 'number') n = Number(n);
    if (isNaN(n)) return 'N/D';

    if (n === 0) return '$0.00';
    if (n < 0.01) return '$' + n.toFixed(4);
    return '$' + n.toFixed(2);
  },

  /**
   * Format latency in ms or seconds
   */
  formatLatency(ms) {
    if (ms === null || ms === undefined) return 'N/D';
    if (ms >= 1000) return (ms / 1000).toFixed(2) + 's';
    return Math.round(ms) + 'ms';
  },

  /**
   * Format percentage (0.684 -> 68.4%)
   */
  formatPct(ratio) {
    if (ratio === null || ratio === undefined) return 'N/D';
    return (ratio * 100).toFixed(1) + '%';
  },

  /**
   * Format ISO string in local browser time (HH:mm:ss)
   */
  formatTime(isoString) {
    if (!isoString) return '--:--:--';
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return '--:--:--';
    return d.toLocaleTimeString('pt-BR');
  },

  /**
   * Format ISO string in local date and time
   */
  formatDateTime(isoString) {
    if (!isoString) return 'N/D';
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return 'N/D';
    return d.toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  },

  /**
   * Return risk category based on ratio (0.0 to 1.0)
   */
  getRiskLevel(ratio) {
    if (ratio === null || ratio === undefined) return 'normal';
    if (ratio >= 0.95) return 'critical';
    if (ratio >= 0.80) return 'high';
    if (ratio >= 0.60) return 'warning';
    return 'normal';
  },

  /**
   * Label for risk category
   */
  getRiskLabel(level) {
    switch (level) {
      case 'critical': return 'Crítico (95%+)';
      case 'high': return 'Alto (80%+)';
      case 'warning': return 'Atenção (60%+)';
      default: return 'Normal';
    }
  },

  /**
   * Debounce helper
   */
  debounce(func, wait) {
    let timeout;
    return function (...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  }
};
