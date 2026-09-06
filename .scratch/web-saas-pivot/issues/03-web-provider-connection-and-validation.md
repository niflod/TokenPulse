# 03: Conexão Web de Provedores com Validação Instantânea

**What to build:**
Disponibilizar uma interface visual no navegador onde o usuário autenticado pode cadastrar suas chaves de API/Admin para os provedores suportados (OpenAI, Anthropic, Gemini, Groq, OpenRouter). Ao inserir uma chave, o sistema realiza uma verificação em tempo real contra a API oficial do provedor e exibe feedback imediato ("Conectado com sucesso" ou detalhes do erro de autenticação/permissão), gravando a credencial criptografada por usuário no banco.

**Blocked by:** 01: Cadastro Multi-Usuário e Isolamento de Tenants

**Status:** completed

- [x] Formulário web intuitivo na seção de Provedores do dashboard para inserir credenciais de OpenAI, Anthropic, Gemini, Groq e OpenRouter.
- [x] Endpoint backend `POST /api/providers/validate` que testa a chave contra o provedor sem salvá-la em definitivo caso falhe.
- [x] Criptografia segura da chave associada ao `user_id` e armazenamento mascarado na resposta da API (`sk-...****`).
- [x] Listagem das conexões ativas com badge de status visual (Conectado / Erro / Não configurado).
- [x] Testes automatizados cobrindo fluxos de validação de chaves válidas e rejeição de chaves inválidas ou expiradas com mensagens claras.
