# 02: SECRET_KEY Obrigatória em Produção

**What to build:** Backend recusa iniciar sem `SECRET_KEY` persistente quando `ENVIRONMENT != development`. Em dev, gera chave efêmera com warning explícito. Variável `ENVIRONMENT` adicionada ao `.env.example`.

**Blocked by:** None (pode começar imediatamente)

**Status:** completed

- [x] `ENVIRONMENT=production` sem `SECRET_KEY` → falha imediata com mensagem clara
- [x] `ENVIRONMENT=development` sem `SECRET_KEY` → gera efêmera com warning
- [x] `.env.example` atualizado com `ENVIRONMENT=development`
- [x] Dados criptografados sobrevivem a reinício com mesma `SECRET_KEY`
- [x] Teste automatizado validando falha em produção
