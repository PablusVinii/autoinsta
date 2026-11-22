FROM python:3.12-slim

# Instala ffmpeg e dependencias essenciais do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala as dependencias do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia os arquivos do projeto
COPY . .

# Executa o bot
CMD ["python", "bot.py"]
