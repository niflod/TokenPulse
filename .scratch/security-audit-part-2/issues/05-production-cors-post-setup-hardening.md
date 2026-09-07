# 05: CORS de Produção Netlify, CSP Especializado e Blindagem Pós-Setup

**What to build:**
Concluir o hardening de produção da aplicação garantindo conectividade CORS legítima para o domínio oficial da plataforma, endurecendo o CSP contra resíduos de desenvolvimento e fechando o acesso público ao endpoint de setup após o primeiro uso. Atualmente, a lista padrão de origens CORS não inclui os domínios do Netlify (`https://tknpulse.netlify.app` / `https://tokenpulse.netlify.app`), forçando intervenções manuais ou risco de uso de coringas. Adicionalmente, o CSP do backend libera `http://localhost:*` e `ws:` mesmo quando executado em produção, e o endpoint `/api/auth/setup` permanece na lista de prefixos públicos do middleware após a configuração inicial do administrador.

Este ticket deve entregar:
1. **Inclusão dos Domínios Netlify no CORS Padrão:**
   - Em `backend/config.py`, incluir `https://tknpulse.netlify.app` e `https://tokenpulse.netlify.app` na lista padrão de `cors_origins`.
   - Assegurar que a variável de ambiente `CORS_ORIGINS` continue permitindo extensões dinâmicas (como domínios personalizados de clientes).
2. **CSP Especializado por Ambiente:**
   - Em `backend/main.py:add_security_headers`, diferenciar a diretiva `connect-src`:
     - Em desenvolvimento: manter `http://localhost:* http://127.0.0.1:* ws:` para conveniência local.
     - Em produção (`is_production == True`): restringir a `'self' https://tknpulse.netlify.app https://tokenpulse.netlify.app https://tokenpulse-backend.onrender.com`, eliminando origens de desenvolvimento.
3. **Bloqueio Pós-Setup no Middleware de Autenticação:**
   - Em `backend/main.py`, desativar a isenção de autenticação pública para `/api/auth/setup` caso o setup inicial já tenha sido realizado, evitando exposição desnecessária da rota de setup após a criação do administrador.
4. **Atualização da Documentação de Deploy e Startup:**
   - Atualizar `backend/.env.example` e `README.md` destacando a exigência de `ENVIRONMENT=production` e `SECRET_KEY` de 64 caracteres no Render e Docker.
5. **Cobertura de Testes de Produção:**
   - Criar testes verificando que a origem Netlify é aceita nos cabeçalhos de preflight OPTIONS CORS.
   - Criar teste validando que o CSP gerado em produção não inclui `localhost` nem `ws:`.
   - Testar o comportamento de `/api/auth/setup` antes e depois do setup ser concluído.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Origens de produção do Netlify incluídas na lista padrão de `cors_origins`.
- [x] Diretiva `connect-src` do CSP ajustada estritamente para produção sem origens de desenvolvimento locais.
- [x] Endpoint `/api/auth/setup` desabilitado de prefixos públicos após o setup estar concluído.
- [x] Documentação de deploy (`.env.example` e `README.md`) atualizada com os requisitos de produção.
- [x] Testes automatizados cobrindo CORS, CSP de produção e pós-setup aprovados.
