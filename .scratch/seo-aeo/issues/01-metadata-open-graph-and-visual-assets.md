# 01: Metadados Estratégicos, Tags Sociais e Assets Visuais (Open Graph & Favicon)

**What to build:**
Transformar a camada de cabeçalho (`<head>`) da Landing Page pública em uma interface de alta fidelidade para mecanismos de busca, assistentes de IA e aplicativos de mensageria (WhatsApp, LinkedIn, Slack, Discord, X). Atualmente, a página possui um título misto em inglês e português, nenhuma meta-descrição e zero metadados Open Graph ou Twitter Card, resultando em snippets gerados aleatoriamente pelo Google e compartilhamentos sociais opacos sem imagem de pré-visualização.

Este ticket deve entregar:
1. **Reestruturação Estratégica do Título (`<title>`):**
   - Substituir o título atual por uma fórmula precisa, orientada a palavras-chave de intenção de busca em Português do Brasil:
     `TokenPulse — Monitore custos e uso de APIs de IA (OpenAI, Claude, Gemini)`.
   - Limite de caracteres: entre 55 e 65 caracteres, evitando truncamento na visualização de resultados de busca móvel e desktop do Google.
2. **Meta Description Otimizada:**
   - Adicionar tag `<meta name="description">` com copy persuasiva de alto índice de clique (CTR), sintetizando proposta de valor, ausência de terminal e provedores suportados em exatamente 150-155 caracteres:
     `"Monitore gastos, limites e projeções de faturas para APIs de OpenAI, Claude e Gemini em tempo real diretamente pelo navegador. Sem terminal e sem Docker."`
3. **URL Canônica Declarativa:**
   - Inserir `<link rel="canonical" href="https://tokenpulse.netlify.app/">` consolidando autoridade de indexação e prevenindo canibalização de ranking provocada por parâmetros de URL ou variações de protocolo.
4. **Implementação Completa do Protocolo Open Graph:**
   - Inserir `og:type` (`website`), `og:locale` (`pt_BR`), `og:site_name` (`TokenPulse`).
   - Declarar `og:title`, `og:description` e `og:url`.
   - Declarar `og:image` apontando para a imagem oficial de compartilhamento (com especificações explícitas de largura 1200px, altura 630px e texto alternativo `og:image:alt`).
5. **Configuração de Twitter Cards:**
   - Declarar `twitter:card` com valor `summary_large_image`, além de `twitter:title`, `twitter:description` e `twitter:image`.
6. **Design e Criação de Assets Visuais:**
   - Criar `frontend/favicon.svg`: vetor SVG responsivo com o símbolo oficial de atividade (`activity`) do TokenPulse sobre gradiente da marca (`#4D8DFF` a `#8B7CFF`), renderizável de forma nítida em qualquer densidade de pixels.
   - Vincular `favicon.svg` via `<link rel="icon" type="image/svg+xml" href="/favicon.svg">` e `<link rel="apple-touch-icon" href="/favicon.svg">`.
   - Criar asset visual para Open Graph em `frontend/assets/og-image.png` (ou SVG/PNG otimizado) em resolução padrão 1200×630px com identidade visual escura do produto, logotipo, badge de telemetria e chamada de valor.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] `<title>` da Landing Page reescrito para padrão PT-BR com termos de busca (TokenPulse — Monitore custos e uso de APIs de IA (OpenAI, Claude, Gemini)).
- [x] `<meta name="description">` adicionada com copy persuasiva e limite de 155 caracteres.
- [x] Tag canônica absoluta `<link rel="canonical" href="https://tokenpulse.netlify.app/">` implementada no `<head>`.
- [x] Metadados Open Graph (`og:title`, `og:description`, `og:image`, `og:image:width`, `og:image:height`, `og:image:alt`, `og:url`, `og:site_name`, `og:locale`) integrados.
- [x] Tags de Twitter Card (`twitter:card`, `twitter:title`, `twitter:description`, `twitter:image`) declaradas como `summary_large_image`.
- [x] Favicon vetorial em SVG (`frontend/favicon.svg`) criado e devidamente vinculado com suporte a navegadores modernos e touch devices.
- [x] Imagem de compartilhamento social (`frontend/assets/og-image.png` ou equivalente em resolução 1200×630) gerada e acessível publicamente na pasta de assets.
