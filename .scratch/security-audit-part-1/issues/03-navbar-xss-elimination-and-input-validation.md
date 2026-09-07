# 03: Eliminação de XSS Armazenado na Navbar e Sanitização de Entradas de Registro

**What to build:**
Remover a vulnerabilidade de Cross-Site Scripting (XSS) armazenado/DOM na Landing Page pública e fortalecer as validações de entrada no backend. Atualmente, o script em `frontend/index.html` recupera `localStorage.getItem('tp_username')` e interpola o valor diretamente em uma string de template atribuída ao `innerHTML` do contêiner de navegação (`actionsEl.innerHTML = ...`). Como o endpoint de registro não impõe validação de conjunto de caracteres no nome de usuário, strings como `<img src=x onerror=...>` podem ser cadastradas e executadas no navegador do usuário visitante, contrariando a política de segurança da aplicação.

Este ticket deve entregar:
1. **Refatoração Segura do DOM na Navbar (`frontend/index.html`):**
   - Substituir a concatenação em `innerHTML` pela criação e montagem de nós nativos do DOM.
   - Utilizar a propriedade `textContent` para injetar a saudação do usuário (`Olá, Usuário`), garantindo que qualquer caractere especial seja tratado estritamente como texto inerte pelo motor do navegador.
   - Manter a renderização correta do botão "Ir para o Dashboard" e a reinicialização de ícones Lucide.
2. **Validação Estrita de Input no Cadastro de Usuários:**
   - Adicionar validação de formato no modelo `RegisterRequest` e `SetupRequest` no backend (`backend/routers/auth.py` e schemas).
   - Exigir que o `username` contenha exclusivamente caracteres alfanuméricos, pontos, hífens ou underscores (ex: regex `^[a-zA-Z0-9_.-]{3,32}$`), rejeitando explicitamente tags HTML, aspas, barras e caracteres de controle com HTTP 422.
3. **Higienização nos Scripts de Autenticação do Frontend:**
   - Verificar `login.js` e `signup.js` para garantir que campos de usuário e mensagens de status continuem usando `textContent` ou manipulação segura de nós, sem injeção crua em `innerHTML`.
4. **Cobertura de Testes Automatizados:**
   - Adicionar testes no backend validando que tentativas de registrar usuários com payloads contendo HTML ou scripts (`<script>`, `<img onerror=...>`, etc.) resultam em erro de validação (HTTP 422).
   - Testar o comportamento da interface garantindo que nomes de usuário com caracteres especiais sejam renderizados sem injeção de elementos DOM indesejados.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] A saudação na navbar da Landing Page (`frontend/index.html`) utiliza nós DOM nativos e `textContent`, sem interpolação direta em `innerHTML`.
- [x] O modelo de entrada de registro (`RegisterRequest`) rejeita caracteres não alfanuméricos perigosos e tags HTML com HTTP 422.
- [x] O modelo de setup administrativo (`SetupRequest`) valida e higieniza o nome de usuário fornecido.
- [x] As telas de login e signup preservam a disciplina de não utilizar `innerHTML` com dados de entrada.
- [x] Testes automatizados de rejeição de payload malicioso no registro passam com sucesso.
