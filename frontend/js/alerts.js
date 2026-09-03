/**
 * js/alerts.js — Safe visual notifications, banners and active anomaly renderers.
 * Immune to DOM XSS: strictly uses textContent and DOM API instead of innerHTML.
 */

const Alerts = {
  toast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toastEl = document.createElement('div');
    toastEl.className = `toast toast-${type}`;

    let iconName = 'info';
    if (type === 'success') iconName = 'check-circle';
    if (type === 'warning') iconName = 'alert-triangle';
    if (type === 'error') iconName = 'alert-octagon';

    const icon = document.createElement('i');
    icon.setAttribute('data-lucide', iconName);

    const span = document.createElement('span');
    span.textContent = message;

    toastEl.appendChild(icon);
    toastEl.appendChild(span);
    container.appendChild(toastEl);

    if (window.lucide) lucide.createIcons();

    setTimeout(() => {
      toastEl.style.opacity = '0';
      toastEl.style.transform = 'translateX(100%)';
      toastEl.style.transition = 'all 0.3s ease';
      setTimeout(() => toastEl.remove(), 300);
    }, duration);
  },

  renderAnomalies(containerEl, anomalies = []) {
    if (!containerEl) return;

    // Clear existing content safely
    containerEl.textContent = '';

    if (!anomalies || anomalies.length === 0) {
      containerEl.classList.add('hidden');
      return;
    }

    containerEl.classList.remove('hidden');

    anomalies.forEach((a) => {
      const alertDiv = document.createElement('div');
      alertDiv.className = `anomaly-alert ${a.severity || 'warning'}`;

      const icon = document.createElement('i');
      icon.setAttribute('data-lucide', 'alert-triangle');
      icon.className = 'text-warning';

      const contentDiv = document.createElement('div');
      const strong = document.createElement('strong');
      strong.textContent = 'ANOMALIA DETECTADA: ';

      const msgSpan = document.createElement('span');
      msgSpan.textContent = a.message || 'Comportamento anormal identificado';

      contentDiv.appendChild(strong);
      contentDiv.appendChild(msgSpan);

      alertDiv.appendChild(icon);
      alertDiv.appendChild(contentDiv);
      containerEl.appendChild(alertDiv);
    });

    if (window.lucide) lucide.createIcons();
  },
};
