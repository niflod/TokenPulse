/**
 * js/charts.js — Chart.js configurations and data updates with dark mode styling.
 */

const Charts = {
  _instances: {},
  _currentTimelineMetric: 'requests',

  _getDarkDefaults() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      color: '#9499ad',
      font: { family: "'Inter', sans-serif", size: 11 },
      plugins: {
        legend: {
          display: true,
          labels: { color: '#9499ad', boxWidth: 12, padding: 16 },
        },
        tooltip: {
          backgroundColor: '#1b1e2c',
          titleColor: '#f3f4f6',
          bodyColor: '#9499ad',
          borderColor: '#232738',
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.04)' },
          ticks: { color: '#60667d', maxRotation: 0 },
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.04)' },
          ticks: { color: '#60667d' },
          beginAtZero: true,
        },
      },
    };
  },

  setTimelineMetric(metric) {
    this._currentTimelineMetric = metric;
  },

  /**
   * 1. Line Chart: Timeline (Requests, Tokens or Cost)
   */
  renderTimeline(canvasId, timeseries = []) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const labels = timeseries.map((pt) => {
      const d = new Date(pt.timestamp);
      return isNaN(d.getTime()) ? '' : d.getHours() + ':00';
    });

    let datasetLabel = 'Requisições';
    let dataValues = timeseries.map((pt) => pt.requests || 0);
    let borderColor = '#6366f1';
    let bgColor = 'rgba(99, 102, 241, 0.12)';

    if (this._currentTimelineMetric === 'tokens') {
      datasetLabel = 'Total de Tokens';
      dataValues = timeseries.map((pt) => pt.totalTokens || 0);
      borderColor = '#38bdf8';
      bgColor = 'rgba(56, 189, 248, 0.12)';
    } else if (this._currentTimelineMetric === 'cost') {
      datasetLabel = 'Custo ($ USD)';
      dataValues = timeseries.map((pt) => pt.cost || 0.0);
      borderColor = '#10b981';
      bgColor = 'rgba(16, 185, 129, 0.12)';
    }

    if (this._instances[canvasId]) {
      const chart = this._instances[canvasId];
      chart.data.labels = labels;
      chart.data.datasets[0].label = datasetLabel;
      chart.data.datasets[0].data = dataValues;
      chart.data.datasets[0].borderColor = borderColor;
      chart.data.datasets[0].backgroundColor = bgColor;
      chart.update();
      return;
    }

    const config = {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: datasetLabel,
            data: dataValues,
            borderColor: borderColor,
            backgroundColor: bgColor,
            fill: true,
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 2,
            pointHoverRadius: 5,
          },
        ],
      },
      options: this._getDarkDefaults(),
    };

    this._instances[canvasId] = new Chart(ctx, config);
  },

  /**
   * 2. Doughnut Chart: By Provider
   */
  renderProviders(canvasId, byProvider = []) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const labels = byProvider.map((p) => p.provider.toUpperCase());
    const dataValues = byProvider.map((p) => p.requests || 0);
    const colors = ['#6366f1', '#f59e0b', '#10b981', '#ec4899', '#8b5cf6'];

    if (this._instances[canvasId]) {
      const chart = this._instances[canvasId];
      chart.data.labels = labels.length ? labels : ['Sem Dados'];
      chart.data.datasets[0].data = dataValues.length ? dataValues : [1];
      chart.update();
      return;
    }

    const config = {
      type: 'doughnut',
      data: {
        labels: labels.length ? labels : ['Sem Dados'],
        datasets: [
          {
            data: dataValues.length ? dataValues : [1],
            backgroundColor: colors.slice(0, Math.max(labels.length, 1)),
            borderColor: '#141620',
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#9499ad', boxWidth: 10, padding: 14 },
          },
        },
      },
    };

    this._instances[canvasId] = new Chart(ctx, config);
  },

  /**
   * 3. Stacked Bar Chart: Input vs Output Tokens
   */
  renderInputOutput(canvasId, timeseries = []) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const labels = timeseries.map((pt) => {
      const d = new Date(pt.timestamp);
      return isNaN(d.getTime()) ? '' : d.getHours() + ':00';
    });
    const inputData = timeseries.map((pt) => pt.inputTokens || 0);
    const outputData = timeseries.map((pt) => pt.outputTokens || 0);

    if (this._instances[canvasId]) {
      const chart = this._instances[canvasId];
      chart.data.labels = labels;
      chart.data.datasets[0].data = inputData;
      chart.data.datasets[1].data = outputData;
      chart.update();
      return;
    }

    const opts = this._getDarkDefaults();
    opts.scales.x.stacked = true;
    opts.scales.y.stacked = true;

    const config = {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Input Tokens',
            data: inputData,
            backgroundColor: '#6366f1',
            borderRadius: 4,
          },
          {
            label: 'Output Tokens',
            data: outputData,
            backgroundColor: '#a855f7',
            borderRadius: 4,
          },
        ],
      },
      options: opts,
    };

    this._instances[canvasId] = new Chart(ctx, config);
  },

  /**
   * 4. Bar Chart: Hourly Request Distribution
   */
  renderHourly(canvasId, timeseries = []) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const labels = timeseries.map((pt) => {
      const d = new Date(pt.timestamp);
      return isNaN(d.getTime()) ? '' : d.getHours() + ':00';
    });
    const reqData = timeseries.map((pt) => pt.requests || 0);

    if (this._instances[canvasId]) {
      const chart = this._instances[canvasId];
      chart.data.labels = labels;
      chart.data.datasets[0].data = reqData;
      chart.update();
      return;
    }

    const config = {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Requisições / Hora',
            data: reqData,
            backgroundColor: 'rgba(16, 185, 129, 0.7)',
            borderColor: '#10b981',
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: this._getDarkDefaults(),
    };

    this._instances[canvasId] = new Chart(ctx, config);
  },

  destroyAll() {
    Object.values(this._instances).forEach((inst) => inst.destroy());
    this._instances = {};
  },
};
