# 04: Mitigação de Truncamento Bcrypt (72 Bytes) e Validação Estrita de Senhas

**What to build:**
Eliminar a discrepância criptográfica causada pela limitação nativa do algoritmo bcrypt, que trunca senhas silenciosamente no 72º byte. Atualmente, os schemas Pydantic de cadastro, setup e alteração de senha (`RegisterRequest`, `SetupRequest`, `ChangePasswordRequest`) definem `max_length=128`. Como resultado, um usuário pode cadastrar uma senha de 100 caracteres, mas apenas os primeiros 72 bytes são efetivamente verificados na autenticação, gerando uma falsa sensação de segurança e inconsistências com o padrão do algoritmo.

Este ticket deve entregar:
1. **Ajuste Cirúrgico nos Schemas Pydantic:**
   - Em `backend/routers/auth.py`, atualizar o campo de senha nos seguintes schemas para `max_length=72`:
     - `RegisterRequest.password`: `Field(..., min_length=8, max_length=72)`
     - `SetupRequest.password`: `Field(..., min_length=8, max_length=72)`
     - `ChangePasswordRequest.new_password`: `Field(..., min_length=8, max_length=72)`
2. **Mensagens de Erro Transparentes:**
   - Garantir que qualquer submissão contendo senha superior a 72 caracteres retorne erro de validação HTTP 422 Unprocessable Entity, orientando o usuário sobre o limite estrito suportado pelo padrão criptográfico.
3. **Cobertura de Testes de Limite de Senha:**
   - Criar teste automatizado tentando cadastrar usuário com senha de 73 caracteres e validar retorno HTTP 422 com mensagem de validação de comprimento.
   - Validar que uma senha de exatamente 72 caracteres é aceita com sucesso (HTTP 201).
   - Validar que o fluxo de alteração de senha (`PUT /api/auth/password`) também rejeita senhas novas com mais de 72 caracteres com HTTP 422.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Campo `password` em `RegisterRequest`, `SetupRequest` e `ChangePasswordRequest` limitado a `max_length=72`.
- [x] Submissões com mais de 72 caracteres são rejeitadas com status HTTP 422.
- [x] Senhas de até 72 caracteres continuam sendo aceitas normalmente.
- [x] Testes automatizados cobrindo os limites de fronteira de senha aprovados.
