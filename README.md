# 🤖 Bot de Resumo de Reels do Instagram no Telegram

Este projeto permite que você compartilhe qualquer **Reel do Instagram** diretamente para o seu bot no **Telegram** e receba em instantes um resumo inteligente gerado com IA (Google Gemini), contendo:
- 🎬 Título e tema principal
- 💡 Pontos-chave e insights práticos
- 🛠 Passo a passo ou receitas/dicas em tópicos
- 📌 Conclusão / takeaway central
- 🔗 Link do Reel original

O Gemini analisa **multimodalmente** tanto o áudio do vídeo quanto os textos e códigos exibidos na tela.

---

## 📋 Pré-requisitos e Configuração

### 1. Criar o Bot no Telegram
1. No seu Telegram, busque por `@BotFather` e inicie uma conversa (`/start`).
2. Digite `/newbot`.
3. Escolha um nome para o seu bot (ex: `Meu Resumidor de Reels`) e um username único terminado em `bot` (ex: `meu_reels_summary_bot`).
4. O `@BotFather` fornecerá um **Token de Acesso HTTP API** (ex: `7123456789:AAH...`). Guarde este token.

### 2. Obter a Chave da API do Google Gemini
1. Acesse o [Google AI Studio](https://aistudio.google.com/).
2. Faça login com sua conta Google.
3. Clique em **Get API key** e em seguida **Create API key**.
4. Copie a chave gerada.

### 3. Configurar as Variáveis de Ambiente
1. Copie o arquivo `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```
2. Abra o arquivo `.env` e preencha:
   ```env
   TELEGRAM_BOT_TOKEN=seu_token_aqui
   GEMINI_API_KEY=sua_chave_gemini_aqui
   GEMINI_MODEL=gemini-4-hydrogen
   ```
   *(Opcional: preencha `ALLOWED_USER_IDS` com seu ID numérico do Telegram se quiser restringir o uso do bot apenas para você).*

---

## 🚀 Como Executar

### No Windows:
Basta dar dois cliques no arquivo **`run.bat`**, ou executar via PowerShell/CMD:
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

### No Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
```

---

## 📱 Como Usar no Dia a Dia (Pelo Celular)

1. No aplicativo do Instagram, quando encontrar um Reel que deseja salvar/resumir:
   - Toque no ícone de **Compartilhar (aviãozinho ✈️)**.
   - Selecione **Telegram** na lista de aplicativos.
   - Escolha o seu Bot e envie.
2. O bot responderá avisando que está baixando e processando o vídeo.
3. Em poucos segundos, você recebe o resumo estruturado!
