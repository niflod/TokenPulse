/**
 * js/providers.js — Safe provider management in Settings and selector sync.
 * Immune to DOM XSS and inline scripts: uses DOM API and addEventListener exclusively.
 */

const Providers = {
  _list: [],

  async load() {
    const { data, error } = await API.getProviders();
    if (error) {
      console.warn('Failed to load providers from backend', error);
      return [];
    }
    this._list = data || [];
    this.renderSettingsList();
    this.populateSelects();
    return this._list;
  },

  getList() {
    return this._list;
  },

  populateSelects() {
    const globalSelect = document.getElementById('select-global-provider');
    const logSelect = document.getElementById('filter-log-provider');

    const renderOpts = (sel) => {
      if (!sel) return;
      const cur = sel.value;
      sel.textContent = '';

      const defOpt = document.createElement('option');
      defOpt.value = '';
      defOpt.textContent = 'Todos os Provedores';
      sel.appendChild(defOpt);

      this._list.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = p.display_name || p.name.toUpperCase();
        sel.appendChild(opt);
      });
      sel.value = cur;
    };

    renderOpts(globalSelect);
    renderOpts(logSelect);
  },

  renderSettingsList() {
    const container = document.getElementById('settings-providers-list');
    if (!container) return;

    container.textContent = '';

    if (this._list.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'text-muted text-center';
      emptyDiv.style.padding = '16px';
      emptyDiv.textContent = 'Nenhum provedor configurado. Use o formulário acima para adicionar.';
      container.appendChild(emptyDiv);
      return;
    }

    this._list.forEach((p) => {
      const item = document.createElement('div');
      item.className = 'configured-provider-item';

      const leftCol = document.createElement('div');
      const strong = document.createElement('strong');
      strong.textContent = p.display_name || p.name.toUpperCase();

      const badge = document.createElement('span');
      badge.className = 'badge-tag';
      badge.style.marginLeft = '8px';
      badge.textContent = p.name;

      const keyStatus = document.createElement('div');
      keyStatus.style.fontSize = '11px';
      keyStatus.style.color = 'var(--text-dim)';
      keyStatus.style.marginTop = '2px';
      keyStatus.textContent = p.has_api_key ? 'Chave: ••••••••' : 'Chave: Não configurada';
      if (!p.has_api_key) {
        keyStatus.className = 'text-warning';
      }

      leftCol.appendChild(strong);
      leftCol.appendChild(badge);
      leftCol.appendChild(keyStatus);

      const rightCol = document.createElement('div');
      rightCol.className = 'flex-row gap-2';

      const toggleBtn = document.createElement('button');
      toggleBtn.className = 'btn btn-secondary btn-sm';
      toggleBtn.textContent = p.enabled ? 'Desativar' : 'Ativar';
      toggleBtn.addEventListener('click', () => this.toggle(p.name));

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-danger btn-sm';
      const trashIcon = document.createElement('i');
      trashIcon.setAttribute('data-lucide', 'trash-2');
      deleteBtn.appendChild(trashIcon);
      deleteBtn.addEventListener('click', () => this.delete(p.name));

      rightCol.appendChild(toggleBtn);
      rightCol.appendChild(deleteBtn);

      item.appendChild(leftCol);
      item.appendChild(rightCol);
      container.appendChild(item);
    });

    if (window.lucide) lucide.createIcons();
  },

  async add(payload) {
    const { data, error } = await API.addProvider(payload);
    if (error) {
      Alerts.toast(`Erro ao salvar provedor: ${error.message}`, 'error');
      return false;
    }
    Alerts.toast(`Provedor '${payload.display_name}' salvo com sucesso!`, 'success');
    await this.load();
    return true;
  },

  async toggle(name) {
    const { error } = await API.toggleProvider(name);
    if (error) {
      Alerts.toast(`Erro ao alternar provedor: ${error.message}`, 'error');
      return;
    }
    await this.load();
    if (window.App && App.refresh) App.refresh();
  },

  async delete(name) {
    if (!confirm(`Deseja realmente remover o provedor ${name.toUpperCase()}?`)) return;
    const { error } = await API.deleteProvider(name);
    if (error) {
      Alerts.toast(`Erro ao remover provedor: ${error.message}`, 'error');
      return;
    }
    Alerts.toast(`Provedor ${name.toUpperCase()} removido.`, 'info');
    await this.load();
    if (window.App && App.refresh) App.refresh();
  },
};
