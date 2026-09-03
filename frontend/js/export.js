/**
 * js/export.js — Client-side and server-side data export handlers.
 */

const Export = {
  downloadCSV(provider = '') {
    API.exportCSV(provider);
    Alerts.toast('Exportação CSV iniciada.', 'info');
  },

  downloadJSON(provider = '') {
    API.exportJSON(provider);
    Alerts.toast('Exportação JSON iniciada.', 'info');
  },

  downloadReport(summaryData) {
    if (!summaryData) {
      Alerts.toast('Nenhum dado disponível para o relatório.', 'warning');
      return;
    }

    const today = summaryData.summary?.today || {};
    const week = summaryData.summary?.week || {};
    const month = summaryData.summary?.month || {};
    const limits = summaryData.limits || {};
    const proj = summaryData.projection || {};

    const lines = [
      '====================================================',
      '       AI USAGE MONITOR — RELATÓRIO DE CONSUMO      ',
      '====================================================',
      `Data de Emissão: ${new Date().toLocaleString('pt-BR')}`,
      `Servidor: ${summaryData.serverTime || 'Local'}`,
      `Modo: ${summaryData.demo ? 'DEMO (Simulado)' : 'PRODUÇÃO'}`,
      '',
      '--- RESUMO DE CONSUMO ---',
      `Hoje:`,
      `  • Requisições: ${today.requests || 0} req`,
      `  • Total de Tokens: ${today.totalTokens || 0} (${today.inputTokens || 0} in / ${today.outputTokens || 0} out)`,
      `  • Custo Estimado: $${today.cost || 0.00}`,
      `  • Latência Média: ${today.avgLatencyMs || 'N/D'} ms`,
      `  • Taxa de Erro: ${((today.errorRate || 0) * 100).toFixed(2)}%`,
      '',
      `Esta Semana:`,
      `  • Requisições: ${week.requests || 0} req`,
      `  • Tokens: ${week.totalTokens || 0}`,
      `  • Custo: $${week.cost || 0.00}`,
      '',
      `Este Mês:`,
      `  • Requisições: ${month.requests || 0} req`,
      `  • Tokens: ${month.totalTokens || 0}`,
      `  • Custo: $${month.cost || 0.00}`,
      '',
      '--- LIMITES E PROJEÇÕES ---',
      `Limite Diário: ${limits.daily || 'N/D'} req`,
      `Velocidade Atual: ${proj.requestsPerHour || 0} req/hora`,
      `Projeção Final do Dia: ${proj.projectedDailyRequests || 0} req (${proj.projectedUtilizationPct || 0}%)`,
      `Previsão para Esgotar (ETA): ${proj.etaRequestsLimit || 'Nenhum risco detectado'}`,
      '',
      '--- MODELOS ATIVOS ---',
      ...(summaryData.byModel || []).map(
        (m) =>
          `• [${m.provider.toUpperCase()}] ${m.model}: ${m.requests} req | ${m.totalTokens} tok | Latência: ${m.latency}ms | Custo: $${m.cost || 0.00}`
      ),
      '',
      '====================================================',
      '               FIM DO RELATÓRIO                     ',
      '====================================================',
    ];

    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ai_usage_report_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    Alerts.toast('Relatório de consumo gerado!', 'success');
  }
};
