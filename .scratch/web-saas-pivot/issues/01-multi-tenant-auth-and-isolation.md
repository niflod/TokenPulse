# 01: Cadastro Multi-Usuário e Isolamento de Tenants

**What to build:**
Permitir que qualquer novo usuário acerte na interface web, crie uma conta própria através de uma página de cadastro (`/signup.html`), realize login com email e senha, e receba um token JWT isolado. Toda a persistência e consulta a dados do TokenPulse (provedores, logs de uso, chaves virtuais, alertas) passa a ser estritamente particionada pelo identificador do usuário autenticado (`user_id`), garantindo isolamento total entre diferentes contas no SaaS.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Tela de cadastro `/signup.html` com formulário de email, nome e senha, com validação de campos e feedback visual de sucesso/erro.
- [x] Endpoint de registro `POST /api/auth/register` aberto publicamente que cria um novo usuário com senha hasheada com bcrypt.
- [x] Adicionar chave estrangeira `user_id` às entidades de dados de provedores, histórico de uso, chaves de cliente e configurações de alerta com migração automática retrocompatível.
- [x] Garantir que endpoints protegidos de leitura e escrita filtrem e salvem registros exclusivamente associados ao `user_id` do token JWT autenticado.
- [x] Testes automatizados comprovando que o Usuário A não consegue ler nem modificar dados pertencentes ao Usuário B (HTTP 401/403/404).
