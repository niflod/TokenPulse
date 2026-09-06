/**
 * js/signup.js — Client-side registration logic for TokenPulse multi-tenant SaaS.
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

document.addEventListener('DOMContentLoaded', () => {
  const signupForm = document.getElementById('signup-form');
  const signupBtn = document.getElementById('signup-btn');

  if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('signup-username').value.trim();
      const email = document.getElementById('signup-email').value.trim();
      const password = document.getElementById('signup-password').value;

      if (!username || !email || !password) {
        showError('Preencha todos os campos.');
        return;
      }

      if (password.length < 8) {
        showError('A senha deve ter pelo menos 8 caracteres.');
        return;
      }

      if (signupBtn) signupBtn.disabled = true;

      try {
        const res = await fetch(`${API_BASE}/api/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, email, password }),
        });

        const data = await res.json();

        if (!res.ok) {
          showError(data.detail || 'Falha ao criar conta.');
          if (signupBtn) signupBtn.disabled = false;
          return;
        }

        localStorage.setItem('tp_token', data.token);
        localStorage.setItem('tp_username', data.username);
        showSuccess('Conta criada com sucesso! Redirecionando...');

        setTimeout(() => {
          window.location.href = DASHBOARD_URL;
        }, 800);
      } catch (err) {
        showError('Erro de conexão ao criar conta. Verifique sua conexão.');
        if (signupBtn) signupBtn.disabled = false;
      }
    });
  }
});
