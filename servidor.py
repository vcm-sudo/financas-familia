#!/usr/bin/env python3
"""Servidor local do Finanças Família.

Faz duas coisas:
  1) serve os arquivos estáticos (index.html) como o `python3 -m http.server`;
  2) expõe POST /extrair-pdf, que recebe um PDF (base64, vindo do navegador),
     salva num arquivo temporário e chama o Claude Code CLI (`claude`) pela
     ASSINATURA — sem usar a API por token — para extrair as transações do
     extrato/fatura.

Mesmo padrão do Dashboard Hemato (servidor.py) e do lab_transcribe.py: a
ANTHROPIC_API_KEY é removida do ambiente de propósito, forçando o login da
assinatura (Max/Pro) e evitando cobrança por token.

Import de PDF só funciona com este servidor rodando no Mac (onde o `claude`
está instalado e logado). No site hospedado (GitHub Pages) e no celular, use
OFX/CSV — esses são 100% locais no navegador e continuam funcionando em todo lugar.

Requisitos: `claude` (Claude Code CLI) instalado e logado. Rode `claude` uma vez e autentique.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PORT = 8742
CLI_MODEL = "claude-opus-4-8"   # extração de extrato/fatura pede precisão
TIMEOUT = 240  # segundos por PDF

# Serve a partir da pasta onde este script está.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

PROMPT_TMPL = """Leia o PDF em {caminho}. Você é um assistente financeiro especializado em ler \
extratos bancários e faturas de cartão de crédito brasileiros.

Este PDF pode ser:
- **Extrato bancário** (conta corrente): tem entradas (créditos) e saídas (débitos)
- **Fatura de cartão de crédito**: TODAS as compras são despesas (saídas), mesmo que apareçam como valores positivos. Estornos/créditos viram receitas.

Extraia TODAS as transações que encontrar. Retorne SOMENTE um JSON válido, sem texto antes ou depois:

[
  {{
    "descricao": "estabelecimento ou descrição completa",
    "valor": 99.90,
    "data": "2025-06-10",
    "tipo": "despesa",
    "categoria": "uma de: Alimentação, Moradia, Saúde, Educação, Transporte, Lazer, Vestuário, Assinaturas, Salário, Investimento, Outros"
  }}
]

REGRAS CRÍTICAS:
1. Em FATURAS DE CARTÃO: tipo = "despesa" para todas as compras (mesmo as positivas). Estornos viram "receita".
2. Em FATURAS DE CARTÃO: IGNORE completamente entradas de "Pagamento recebido", "Pagamento de fatura", "Pagto fatura", "Crédito de fatura" e similares — são pagamentos da fatura anterior, não transações reais.
3. Em EXTRATOS BANCÁRIOS: "receita" para entradas/créditos, "despesa" para saídas/débitos.
4. Datas no formato YYYY-MM-DD. Se a fatura tiver só DD/MM, use o ano da fatura (procure no cabeçalho).
5. Valor sempre POSITIVO (sem sinal de menos).
6. Para parcelamentos (ex: "3/12"), inclua a parcela na descrição.
7. Para compras em moeda estrangeira, converta para o valor em reais que aparece.
8. IGNORE: totais, subtotais, saldos, IOF, taxas de conversão isoladas (já estão embutidas), juros, encargos.
9. Categorias mais comuns para faturas: Alimentação (mercados, restaurantes, ifood), Transporte (uber, postos, estacionamento), Lazer (cinema, bar, viagem), Saúde (farmácia, médico), Assinaturas (Netflix, Spotify), Vestuário (lojas de roupa).
10. Use a descrição mais completa que aparecer (ex: "PADARIA SAO JOAO" e não só "PADARIA").

Seja EXAUSTIVO — extraia toda transação, mesmo as pequenas (R$ 2,00, R$ 5,00). Retorne só o JSON, nada mais."""


def call_claude(caminho_pdf: str) -> list:
    """Chama o CLI `claude` (assinatura) para extrair as transações do PDF."""
    if shutil.which("claude") is None:
        raise RuntimeError(
            "CLI 'claude' (Claude Code) não encontrado no PATH. "
            "Instale e faça login uma vez: rode `claude` e autentique."
        )

    # Remove a key da API: força o login da assinatura (evita cobrança por token).
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE")}

    cmd = ["claude", "-p", PROMPT_TMPL.format(caminho=caminho_pdf),
           "--allowedTools", "Read",
           "--model", CLI_MODEL]

    proc = subprocess.run(
        cmd, env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=TIMEOUT,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        raise RuntimeError(
            "O CLI 'claude' falhou (exit %d). %s "
            "Verifique se o `claude` está logado (rode `claude` e autentique)."
            % (proc.returncode, (err[-1][:300] if err else ""))
        )

    texto = (proc.stdout or "").strip()
    texto = re.sub(r"```json|```", "", texto).strip()
    if not texto.startswith("["):
        m = re.search(r"\[.*\]", texto, re.DOTALL)
        if m:
            texto = m.group(0)
    dados = json.loads(texto)
    if not isinstance(dados, list):
        raise ValueError("A resposta não é um array JSON.")
    return dados


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "extrair-pdf" in (self.path or ""):
            super().log_message(fmt, *args)

    def do_POST(self):
        if self.path != "/extrair-pdf":
            self.send_error(404, "Not found")
            return

        tmp_path = None
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            payload = json.loads(body)
            b64 = payload.get("b64") or payload.get("data")
            if not b64:
                raise ValueError("payload sem 'b64'")

            fd, tmp_path = tempfile.mkstemp(suffix=".pdf", prefix="extrato_")
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64decode(b64))

            txs = call_claude(tmp_path)
            self._send_json(200, {"transacoes": txs})
        except subprocess.TimeoutExpired:
            self._send_json(504, {"error": "Timeout (%ds) ao ler o PDF com o Claude." % TIMEOUT})
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": str(e)})
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _send_json(self, code: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    if shutil.which("claude") is None:
        print("⚠️  Aviso: CLI 'claude' não encontrado no PATH — a extração de PDF vai falhar.")
        print("   Instale o Claude Code e faça login (rode `claude` e autentique).\n")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Finanças Família rodando em http://localhost:{PORT}/index.html")
    print("Extração de PDF: Claude Code CLI (assinatura). Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando…")
        server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
