#!/bin/bash
cd "$(dirname "$0")"

# Mata qualquer servidor anterior na porta 8742
lsof -ti:8742 | xargs kill -9 2>/dev/null

# Inicia o servidor local (arquivos + /extrair-pdf via Claude CLI/assinatura)
python3 servidor.py &
SERVER_PID=$!

# Aguarda o servidor subir
sleep 1

# Abre no navegador padrão (localhost é necessário para o import de PDF e o login Firebase)
open "http://localhost:8742/index.html"

echo "Finanças rodando (PID $SERVER_PID) em http://localhost:8742/index.html"
echo "Import de PDF: Claude Code CLI (assinatura). Feche esta janela para encerrar."
wait $SERVER_PID
