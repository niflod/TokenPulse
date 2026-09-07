# 04: Motor de AEO (AI Engine Optimization), FAQ Estruturado e Autoridade Semântica

**What to build:**
Dotar a Landing Page de conteúdo com formato direto de respostas ("answer-shaped content") e marcação semântica estruturada (JSON-LD), permitindo que motores de busca conversacionais e assistentes de inteligência artificial (como ChatGPT, Perplexity, Claude, Gemini e Google SGE/AI Overviews) identifiquem, interpretem e citem com precisão o TokenPulse. Atualmente, o site não possui seção de dúvidas frequentes, não declara esquemas estruturados e omite referências claras à licença de código aberto e ao repositório oficial no GitHub.

Este ticket deve entregar:
1. **Seção de Perguntas Frequentes (FAQ) na Landing Page:**
   - Adicionar uma nova seção com âncora `#faq` e cabeçalho claro (*"Perguntas Frequentes"*), contendo 5 itens estruturados em acordeões ou blocos semânticos com respostas concisas de 2 a 3 frases em Português do Brasil:
     - **Q1: O TokenPulse é gratuito?**
       *Resposta:* "Sim. O TokenPulse é 100% gratuito e de código aberto sob a licença MIT. Você pode usar a versão hospedada na web ou rodar a aplicação em seu próprio ambiente sem custos de assinatura."
     - **Q2: É seguro inserir minhas chaves de API no TokenPulse?**
       *Resposta:* "Sim. Suas chaves de provedor são criptografadas em repouso com algoritmo simétrico Fernet, utilizando derivação de chaves via HKDF (SHA-256) e salt exclusivo por usuário. As chaves nunca são expostas em texto puro nem retornadas para a interface web."
     - **Q3: Quais provedores de IA posso monitorar?**
       *Resposta:* "O TokenPulse oferece suporte nativo à sincronização direta e telemetria de consumo para OpenAI (modelos GPT-4o, o1, o3-mini), Anthropic (Claude 3.5 Sonnet), Google Gemini (Gemini 2.0 Flash), Groq e OpenRouter."
     - **Q4: Preciso instalar algo no meu computador ou alterar código?**
       *Resposta:* "Não. Diferente de ferramentas legadas de terminal ou proxy local, o TokenPulse opera diretamente no navegador. Basta conectar suas chaves de organização no painel web para sincronizar gastos e limites automaticamente."
     - **Q5: Como funciona a estimativa de fatura e burn rate?**
       *Resposta:* "O sistema calcula sua taxa de consumo horário (burn rate) em tempo real e projeta o valor estimado da fatura de final de mês e o tempo restante até o teto da sua cota de API, emitindo alertas antes que ocorra bloqueio por limite."
2. **Implementação de Dados Estruturados em JSON-LD (`schema.org/FAQPage`):**
   - Inserir no `<head>` da Landing Page um bloco `<script type="application/ld+json">` contendo a especificação formal `schema.org` com `@type: "FAQPage"`, mapeando rigorosamente as 5 perguntas e respostas do corpo HTML.
   - Isso garante que tanto o Google quanto assistentes baseados em RAG capturem as respostas sem ambiguidade sintática.
3. **Declaração de Entidade Semântica (`schema.org/Organization` e `WebApplication`):**
   - Inserir dados estruturados JSON-LD definindo a entidade formal da plataforma:
     - `@type: "WebApplication"` com `name: "TokenPulse"`, `applicationCategory: "DeveloperApplication"`, `operatingSystem: "Web Browser"`.
     - `@type: "Organization"` com nome, URL canônica oficial e `sameAs` apontando para o repositório público no GitHub.
4. **Link Canônico de Autoridade no Rodapé:**
   - Adicionar no rodapé (`footer`) da Landing Page um link explícito e contextual para o repositório no GitHub:
     - Ícone do GitHub + texto *"Código Aberto no GitHub (MIT)"*.
   - Esse vínculo cruzado fecha o ciclo de validação de entidade para LLMs, que usam menções cruzadas entre código-fonte e site para atestar a veracidade e confiabilidade da ferramenta.

**Blocked by:** 01 (Metadados Estratégicos, Tags Sociais e Assets Visuais)

**Status:** completed

- [x] Seção visual semântica de FAQ com 5 perguntas e respostas em PT-BR integrada à Landing Page.
- [x] Bloco de dados estruturados JSON-LD com `schema.org/FAQPage` validado sintaticamente.
- [x] Bloco de dados estruturados JSON-LD com `schema.org/Organization` e `WebApplication` implementado.
- [x] Link oficial do repositório GitHub com indicação de licença MIT adicionado no rodapé da Landing Page.
- [x] Coerência textual validada: nome da plataforma estritamente "TokenPulse" em toda a cópia pública (sem caixas altas desnecessárias no corpo de texto).
