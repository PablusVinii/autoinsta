# 🤖 AutoInsta — Assistente Universal de Vídeos, Voz & Segundo Cérebro no Telegram

Bot do **Telegram** que transforma links de vídeos (**Instagram, YouTube, TikTok e Twitter/X**) e **notas de voz** em resumos estruturados por lentes especializadas, transcrições diarizadas, estudo interativo de inglês, auditoria crítica com IA, base de conhecimento no **Notion** e **Obsidian**, além de geração e publicação automática de conteúdo para **LinkedIn** e **Blog (GitHub Pages)**.

---

## ✨ Funcionalidades Principais

### 1. Entrada Multimodal (Vídeos & Áudio)
- **Instagram** (`reel`, `reels`, `p`, `share/reel`) — download via `yt-dlp` e análise multimodal (áudio + conteúdo visual da tela).
- **YouTube** (`watch?v=`, `shorts/`, `youtu.be/`) — análise direta da URL via Google Gemini, obtenção de legendas com `youtube-transcript-api` e fallback via `yt-dlp`.
- **TikTok** (`tiktok.com`, `vm.tiktok.com`, `vt.tiktok.com`) — download prioritário pela API TikWM (evitando bloqueios de datacenter) com fallback via `yt-dlp`.
- **Twitter / X** (`twitter.com/.../status/...`, `x.com/.../status/...`) — download via `yt-dlp`.
- **Notas de Voz e Áudios no Telegram** — transcrição direta com **Deepgram Nova-3** e diarização automática de locutores (`🗣️ Locutor 1`, `Locutor 2`, etc.).

### 2. Lentes Especializadas de Extração
Ao enviar qualquer link suportado, você escolhe a lente mais adequada para extrair o conteúdo (sempre traduzido e estruturado em **Português do Brasil**):

| Lente | Código | Foco da Extração |
| :--- | :--- | :--- |
| 💼 **Negócios & Vendas** | `biz` | Tese comercial, frameworks, métricas, plano de execução e alertas |
| 💻 **Tecnologia & IA** | `tech` | Ferramentas, stack, arquitetura demonstrada, passo a passo e prompts |
| 🧠 **Sabedoria & Filosofia** | `wis` | Modelos mentais, reflexões, quebra de paradigma e citações |
| 🙏 **Fé & Espiritualidade** | `fth` | Mensagem central, princípios e referências bíblicas |
| ⚡ **Síntese Geral** | `gen` | Resumo direto e universal com pontos-chave e takeaway |

### 3. Ações Interativas por Vídeo / Áudio
Cada resumo gerado inclui botões interativos no Telegram:

- **📝 Transcrição**: exibe a transcrição completa em português.
- **🇺🇸 Estudar Inglês & ✍️ Praticar Tradução**: modo bilíngue para aprender vocabulário com áudio de pronúncia nativa (**Deepgram Aura-2** / fallback `edge-tts`) e correção automática da sua tradução.
- **🎙️ Dublagem pt-BR**: gera dublagem multi-voz traduzida para o português.
- **🎧 Resumo Áudio**: gera locução neural do resumo com `edge-tts` (`pt-BR-AntonioNeural`).
- **💡 Ideias de Post & 💭 Gerar Comentário**: sugere ganchos, ideias de conteúdo e comentários engajadores.
- **⚖️ Auditoria Crítica**: análise cética ("Advogado do Diabo") via **NVIDIA NIM** apontando omissões, riscos práticos e nota de praticidade.
- **💬 Tirar Dúvida (Q&A)**: basta responder (*Reply*) à mensagem do resumo para conversar com a IA sobre o conteúdo.
- **💾 Notion**: cria automaticamente uma página na sua database do Notion (criando as colunas `Pontos-Chave`, `Passo a Passo` e `Takeaway` se ainda não existirem).
- **📓 Obsidian**: formata a nota em Markdown com frontmatter YAML, `[[Wikilinks]]`, callouts e transcrição retrátil, enviando direto para o seu cofre no GitHub (ou enviando o `.md` no chat caso o token não esteja configurado).
- **💼 Post LinkedIn**: gera rascunho autoral em 3 ângulos rotativos (`executivo`, `tecnico`, `provocativo`), cria capa visual com Gemini Image (`gemini-2.5-flash-image` / `gemini-3.1-flash-image`) e publica via API oficial do LinkedIn.
- **🌐 Post Blog**: gera artigo completo em Markdown (`executivo`, `tecnico`, `didatico`) com imagem de capa opcional e publica no repositório do **GitHub Pages** (`posts/<slug>.md`, `posts/images/<slug>.png` e atualização automática de `posts/index.json`).

### 4. Roteamento Inteligente de IA & Persistência
- **LLM Router (`services/nvidia.py`)**: usa o **Google Gemini** (`GEMINI_MODEL`) como provedor principal e alterna automaticamente para a **NVIDIA NIM** (`nvidia/nemotron-3.5-bolt-e4b` e `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`) quando o Gemini atinge limite de cota ou quando `LLM_PROVIDER=nvidia`.
- **Banco de Dados (`services/database.py`)**: utiliza **PostgreSQL** quando `DATABASE_URL` está configurada (persistindo vídeos salvos e cache de cards entre reinícios) com fallback automático para **SQLite** local (`saved_videos.db`).
- **Health Check HTTP**: expõe um servidor simples na porta `PORT` (padrão `8080`) para monitoramento em serviços como Render ou Koyeb.

---

## 💬 Comandos Disponíveis no Telegram

| Comando | Aliases | Descrição |
| :--- | :--- | :--- |
| `/start` | — | Exibe instruções iniciais, plataformas suportadas e lentes |
| `/salvos` | `/biblioteca` | Lista os últimos vídeos e áudios salvos na biblioteca |
| `/obsidian` | `/notas` | Mostra notas recentes e conexões `[[Wikilinks]]` |
| `/buscar <termo>` | `/pesquisar` | Busca textual + pesquisa semântica vetorial (NVIDIA Embeddings) |
| `/consultar <pergunta>` | `/cerebro`, `/perguntar` | Síntese cruzada (RAG) respondendo com base no seu Segundo Cérebro |

---

## 🗂️ Estrutura do Projeto

```text
autoinsta/
├── bot.py                 # Aplicação principal do bot Telegram, comandos, callbacks e health check
├── config.py              # Carregamento e validação das variáveis de ambiente
├── requirements.txt       # Dependências Python
├── Dockerfile             # Imagem Docker (Python 3.12-slim + ffmpeg + curl)
├── docker-compose.yml     # Orquestração com restart automático e .env
├── run.bat                # Script de inicialização rápida no Windows
├── .env.example           # Modelo de variáveis de ambiente
├── github_io_site/        # Front-end estático do blog para GitHub Pages (index.html, post.html, posts/)
└── services/
    ├── downloader.py      # Extração de URLs, legendas YouTube, TikWM API e yt-dlp
    ├── summarizer.py      # Prompts das lentes, análise multimodal, Q&A e estudo de inglês
    ├── transcriber.py     # Transcrição/diarização Deepgram Nova-3, tradução e síntese de voz
    ├── nvidia.py          # Roteador Gemini -> NVIDIA NIM, embeddings, auditoria crítica e edge-tts
    ├── database.py        # Persistência em PostgreSQL ou SQLite (saved_videos e video_cache)
    ├── notion.py          # Integração com a API do Notion
    ├── obsidian.py        # Formatação com [[Wikilinks]] e sincronização via GitHub Contents API
    ├── linkedin.py        # Geração e publicação de posts (texto + imagem) no LinkedIn
    ├── blog.py            # Geração e publicação de artigos no blog GitHub Pages
    └── visuals.py         # Geração de imagens de capa 16:9 com Gemini Image
```

---

## ⚙️ Pré-requisitos e Variáveis de Ambiente

1. **Bot no Telegram**: crie um bot com o [`@BotFather`](https://t.me/BotFather) (`/newbot`) e copie o token HTTP API.
2. **Chave do Google Gemini**: gere uma API key no [Google AI Studio](https://aistudio.google.com/).
3. **FFmpeg** *(necessário para manipulação de mídia/áudio; já incluído no `Dockerfile`)*.

Copie o arquivo de exemplo e preencha as variáveis desejadas:

```bash
cp .env.example .env
```

### Variáveis Principais (Obrigatórias)

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Token do bot obtido no `@BotFather` | — |
| `GEMINI_API_KEY` | Chave da API do Google Gemini | — |
| `GEMINI_MODEL` | Modelo Gemini usado nas análises | `gemini-4-hydrogen` |

### Variáveis Opcionais (Integrações, IA e Infraestrutura)

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `ALLOWED_USER_IDS` | IDs numéricos do Telegram autorizados (separados por vírgula) | Todos permitidos |
| `DATABASE_URL` | String de conexão PostgreSQL (se vazia, usa `saved_videos.db` em SQLite) | `""` (SQLite) |
| `PORT` | Porta do servidor HTTP de health check | `8080` |
| `NVIDIA_API_KEY` | Chave da NVIDIA NIM (auditoria crítica, embeddings RAG e fallback de LLM) | `""` |
| `LLM_PROVIDER` | Defina como `nvidia` para forçar o uso da NVIDIA NIM em vez do Gemini | `""` |
| `DEEPGRAM_KEYS` / `DEEPGRAM_API_KEY` | Chave(s) da API Deepgram (separadas por vírgula em `DEEPGRAM_KEYS`) | — |
| `NOTION_API_KEY` | Token da integração do Notion | `""` |
| `NOTION_DATABASE_ID` | ID ou URL do banco de dados no Notion | `""` |
| `OBSIDIAN_GITHUB_TOKEN` | Token do GitHub (PAT com permissão `repo`) para o cofre do Obsidian | `""` |
| `OBSIDIAN_GITHUB_REPO` | Repositório do cofre Obsidian (`usuario/repo`) | `PablusVinii/meu-obsidian` |
| `OBSIDIAN_VAULT_FOLDER` | Pasta de destino das notas no repositório Obsidian | `Inbox` |
| `LINKEDIN_ACCESS_TOKEN` | Token OAuth da API do LinkedIn (`openid`/`profile`/`w_member_social`) | `""` |
| `LINKEDIN_PERSON_URN` | URN do autor no LinkedIn (opcional; resolvido via `/v2/userinfo` se omitido) | `""` |
| `BLOG_GITHUB_TOKEN` | Token do GitHub para publicar no blog (fallback: `GITHUB_TOKEN` / `OBSIDIAN_GITHUB_TOKEN`) | `""` |
| `BLOG_GITHUB_REPO` | Repositório do blog GitHub Pages (`usuario/usuario.github.io`) | `PablusVinii/PablusVinii.github.io` |
| `BLOG_BASE_URL` | URL pública base do blog | `https://pablusvinii.github.io` |

---

## 🚀 Como Executar

### 1. Windows (Execução Rápida)
Dê dois cliques em **`run.bat`** (ele cria o `.env` se não existir, configura o ambiente virtual `venv`, instala as dependências e inicia o bot) ou rode manualmente no PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

### 2. Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
```

### 3. Docker / Docker Compose

```bash
docker compose up -d --build
```

Para acompanhar os logs:

```bash
docker compose logs -f
```

---

## 📱 Fluxo de Uso Rápido

1. No **Instagram**, **YouTube**, **TikTok** ou **Twitter/X**, toque em **Compartilhar** → selecione **Telegram** → envie o link para o seu bot *(ou grave/encaminhe um áudio diretamente no chat)*.
2. Escolha uma das **5 lentes de análise**.
3. Receba o resumo estruturado e use os botões abaixo da mensagem para ouvir em áudio, estudar inglês, auditar criticamente, salvar no **Notion** / **Obsidian** ou publicar no **LinkedIn** e no **Blog**.
4. Dê **Responder (Reply)** em qualquer resumo para fazer perguntas específicas sobre o vídeo.
