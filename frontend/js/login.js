/**
 * js/login.js — Client-side logic for TokenPulse login and first-run setup.
 */

const API_BASE = (() => {
  if (window.location.protocol === 'file:') return 'http://127.0.0.1:8000';
  if (window.location.port !== '8000' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
    return `http://${window.location.hostname}:8000`;
  }
  return window.location.origin;
})();

const DASHBOARD_URL = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000/' : '/';

// If already authenticated, redirect to dashboard
const existingToken = localStorage.getItem('tp_token');
if (existingToken) {
  window.location.href = DASHBOARD_URL;
}

function showError(msg) {
  const el = document.getElementById('error-msg');
  if (el) {
    el.textContent = msg;
    el.style.display = 'block';
  }
  const succ = document.getElementById('success-msg');
  if (succ) succ.style.display = 'none';
}

function showSuccess(msg) {
  const el = document.getElementById('success-msg');
  if (el) {
    el.textContent = msg;
    el.style.display = 'block';
  }
  const err = document.getElementById('error-msg');
  if (err) err.style.display = 'none';
}

async function checkSetupStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/auth/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const setupForm = document.getElementById('setup-form');
    const loginForm = document.getElementById('login-form');

    if (data.setup_completed) {
      if (setupForm) setupForm.style.display = 'none';
      if (loginForm) {
        loginForm.style.display = 'block';
        document.getElementById('login-username')?.focus();
      }
    } else {
      if (loginForm) loginForm.style.display = 'none';
      if (setupForm) {
        setupForm.style.display = 'block';
        document.getElementById('setup-username')?.focus();
      }
    }
  } catch (err) {
    console.error('Falha de conexão com backend:', err);
    showError(`Não foi possível conectar ao backend (${API_BASE}). Verifique se o servidor está rodando em http://127.0.0.1:8000`);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Lucide icons
  if (window.lucide) {
    lucide.createIcons();
  }

  // Check setup status
  checkSetupStatus();

  // Setup form handler (first run)
  document.getElementById('form-setup')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('setup-username')?.value.trim();
    const password = document.getElementById('setup-password')?.value;
    const confirm = document.getElementById('setup-confirm')?.value;

    if (password !== confirm) {
      showError('As senhas não coincidem.');
      return;
    }

    const btn = document.getElementById('btn-setup');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Criando...';
    }

    try {
      const res = await fetch(`${API_BASE}/api/auth/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.detail || 'Erro ao criar administrador.');
        if (btn) {
          btn.disabled = false;
          btn.textContent = 'Criar e Entrar';
        }
        return;
      }

      localStorage.setItem('tp_token', data.token);
      localStorage.setItem('tp_username', data.username);
      showSuccess('Administrador criado! Redirecionando...');
      setTimeout(() => { window.location.href = DASHBOARD_URL; }, 600);
    } catch (err) {
      showError('Erro de conexão com o servidor.');
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Criar e Entrar';
      }
    }
  });

  // Login form handler
  document.getElementById('form-login')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username')?.value.trim();
    const password = document.getElementById('login-password')?.value;

    const btn = document.getElementById('btn-login');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Autenticando...';
    }

    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.detail || 'Credenciais inválidas.');
        if (btn) {
          btn.disabled = false;
          btn.textContent = 'Entrar';
        }
        return;
      }

      localStorage.setItem('tp_token', data.token);
      localStorage.setItem('tp_username', data.username);
      window.location.href = DASHBOARD_URL;
    } catch (err) {
      showError('Erro de conexão com o servidor.');
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Entrar';
      }
    }
  });
});
