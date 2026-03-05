
import os
import json
import asyncio
import subprocess
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

# Configuração de Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backend_utils")

class UtilityHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path == '/imprimir-lote':
            logger.info("Solicitação de impressão em lote recebida.")
            try:
                # Executa o script de geração de relatórios
                # Usamos subprocess para não travar o servidor
                process = subprocess.Popen(['python', 'gerar_relatorios.py'], 
                                         stdout=subprocess.PIPE, 
                                         stderr=subprocess.PIPE,
                                         text=True)
                
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "sucesso", "mensagem": "Processo de impressão iniciado em segundo plano."}).encode())
            except Exception as e:
                logger.error(f"Erro ao iniciar impressão: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "erro", "mensagem": str(e)}).encode())

        elif self.path == '/extrair-agora':
            logger.info("Solicitação de extração manual recebida.")
            try:
                process = subprocess.Popen(['python', 'extractor.py', '--todos'], 
                                         stdout=subprocess.PIPE, 
                                         stderr=subprocess.PIPE,
                                         text=True)
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "sucesso", "mensagem": "Extração iniciada."}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "erro", "mensagem": str(e)}).encode())

def run_server(port=8889):
    server_address = ('', port)
    httpd = HTTPServer(server_address, UtilityHandler)
    logger.info(f"Servidor de Utilidades rodando na porta {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
