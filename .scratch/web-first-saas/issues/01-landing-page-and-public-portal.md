# 01: Landing Page Pública e Portal Web

**What to build:**
Desenvolver uma Landing Page pública institucional na raiz do frontend (`/index.html`) com visual escuro consistente com o design system do TokenPulse. A página deve conter:
1. Navbar com marca, links para seções (Recursos, Provedores, Segurança), botão "Entrar" e CTA "Criar Conta Grátis".
2. Hero section com proposta de valor ("Observe seu consumo de IA em tempo real"), subtítulo explicativo, CTA de cadastro e botão "Ver Demonstração ao Vivo".
3. Cards de recursos (Sincronização Direta sem Terminal, Telemetria e Alertas, Burn Rate & Projeções de Custo, Multi-Provedor).
4. Vitrine de provedores suportados (OpenAI, Anthropic, Gemini, Groq, OpenRouter).
5. Seção de segurança e privacidade (criptografia simétrica Fernet de chaves, isolamento multi-tenant).
6. Detecção de sessão ativa: se o usuário já possui token salvo, exibe botão "Ir para o Dashboard" no topo.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Criar estrutura semântica HTML5 e estilos responsivos da Landing Page.
- [x] Implementar botões de ação direcionando para `/signup.html`, `/login.html` e `/dashboard.html?demo=true`.
- [x] Integrar verificação de token local para alterar CTAs se o usuário já estiver logado.
