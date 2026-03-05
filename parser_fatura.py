"""
parser_fatura.py — Módulo de parse de faturas PDF (Neoenergia Brasília)
=============================================================
Versão 4.0: Foco total na precisão do rodapé (COMPENSADO individual).
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    PDFPLUMBER_DISPONIVEL = True
except ImportError:
    PDFPLUMBER_DISPONIVEL = False
    logger.warning("pdfplumber não encontrado.")

# ---------------------------------------------------------------------------
# Padrões regex
# ---------------------------------------------------------------------------

REGEX_VALOR_TOTAL = re.compile(
    r"(?:valor\s+(?:total|a\s+pagar|da\s+fatura|cobrado)|total\s+a\s+pagar)[^\d]*"
    r"([\d]{1,6}[.,][\d]{2})",
    re.IGNORECASE,
)

# REGEX DO RODAPÉ (Ouro do dado: o que foi REALMENTE descontado da conta)
# Ex: "COMPENSADO....: 500"
REGEX_COMPENSADO_PONTOS = re.compile(r"COMPENSADO\.+:?\s*([\d]+)", re.IGNORECASE)
REGEX_INJETADO_PONTOS = re.compile(r"INJETADO\.+:?\s*([\d]+)", re.IGNORECASE)

# Crédito kWh no corpo da fatura (itens de GD)
REGEX_CREDITO_GD_KWH = re.compile(
    r"(?:energia\s+(?:compensada|injetada)\s+gd|itens\s+financeiros\s+gd)[^\d\n]*?"
    r"([\d]{1,4})\s*(?:kwh)?",
    re.IGNORECASE,
)

# REGEX para valores negativos (créditos) em texto embaralhado
REGEX_NEGATIVO_SCRAMBLED = re.compile(r"-\s*([\d\s]+[.,][\s\d]{2})")

REGEX_SALDO_CREDITO = re.compile(
    r"(?:saldo\s+(?:de\s+)?cr[eé]dito|cr[eé]dito\s+acumulado|saldo\s+atual\.+:?)"
    r"[^\d]*([\d]{1,6}[.,][\d]{2}|[\d]{1,6})",
    re.IGNORECASE,
)

REGEX_CONSUMO = re.compile(
    r"consumo\s+kwh\s+([\d]+)\s+([\d]{1}[.,][\d]{2,8})",
    re.IGNORECASE,
)

def _converter_valor_br(texto: str) -> Optional[float]:
    if not texto: return None
    texto = texto.replace(" ", "")
    # Scrambled text cleanup
    if texto.count(",") > 1:
        texto = texto.replace(",", "")
        texto = texto[:-2] + "." + texto[-2:]
    
    texto = texto.strip()
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None

def _extrair_texto_pdf(caminho_pdf: str) -> str:
    if not PDFPLUMBER_DISPONIVEL: return ""
    texto_total = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            t = pagina.extract_text()
            if t: texto_total.append(t)
    return "\n".join(texto_total)

def _parsear_via_tabelas(caminho_pdf: str) -> dict:
    resultado = {}
    if not PDFPLUMBER_DISPONIVEL: return resultado
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            pagina = pdf.pages[0]
            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                for linha in tabela:
                    if not linha: continue
                    celulas = [str(c).strip() if c else "" for c in linha]
                    linha_str = " | ".join(celulas).lower()

                    # Valor Total Pago
                    if "valor" in linha_str and ("total" in linha_str or "pagar" in linha_str) and "valor_pago" not in resultado:
                        for c in reversed(celulas):
                            v = _converter_valor_br(re.sub(r"[^0-9,.]", "", c))
                            if v and v > 0:
                                resultado["valor_pago"] = v
                                break

                    # Consumo faturado (kWh)
                    if "consumo kwh" in linha_str and "kwh_faturado" not in resultado:
                        for c in celulas:
                            if c.isdigit() and 0 < int(c) < 5000:
                                resultado["kwh_faturado"] = int(c)
                                break
    except Exception as exc:
        logger.warning("Fallo parsing tabelas: %s", exc)
    return resultado

def _parsear_via_regex(texto: str) -> dict:
    resultado = {}
    
    m = REGEX_VALOR_TOTAL.search(texto)
    if m: resultado["valor_pago"] = _converter_valor_br(m.group(1))
    
    m = REGEX_CONSUMO.search(texto)
    if m:
        resultado["kwh_faturado"] = int(m.group(1))
        resultado["tarifa"] = _converter_valor_br(m.group(2))

    # PRIORIDADE 1: COMPENSADO DO RODAPÉ (Valor real descontado)
    m_foot = REGEX_COMPENSADO_PONTOS.search(texto)
    if m_foot:
        resultado["credito_kwh"] = int(m_foot.group(1))
        logger.debug("Crédito kWh (Footer): %s", resultado["credito_kwh"])

    # PRIORIDADE 2: Itens de GD (Corpo) - use apenas se não achou no rodapé
    if not resultado.get("credito_kwh"):
        m = REGEX_CREDITO_GD_KWH.search(texto)
        if m: resultado["credito_kwh"] = int(m.group(1))

    # Busca específica por negativos (R$) em texto embaralhado
    m_neg = REGEX_NEGATIVO_SCRAMBLED.search(texto)
    if m_neg:
        v = _converter_valor_br(m_neg.group(1))
        if v and 1.0 < v < 1500.0:
            resultado["credito_reais"] = v

    return resultado

def parsear_fatura(caminho_pdf: str) -> dict:
    p = Path(caminho_pdf)
    if not p.exists(): raise FileNotFoundError(caminho_pdf)
    
    texto = _extrair_texto_pdf(str(p))
    dados = _parsear_via_tabelas(str(p))
    dados_regex = _parsear_via_regex(texto)
    
    # Merge com prioridade para tabela em campos financeiros, regex em créditos
    for k, v in dados_regex.items():
        if k not in dados or dados[k] is None:
            dados[k] = v

    # Fallback de Saldo (Individual)
    if not dados.get("saldo_credito"):
        m = REGEX_SALDO_CREDITO.search(texto)
        if m: dados["saldo_credito"] = _converter_valor_br(m.group(1))

    # Inferência de Valores
    tarifa = dados.get("tarifa") or 0.95
    kwh = dados.get("credito_kwh")
    reais = dados.get("credito_reais")

    # Se temos kWh (do rodapé) mas não reais, calculamos
    if kwh is not None and not reais:
        dados["credito_reais"] = round(kwh * tarifa, 2)
    elif reais and kwh is None:
        dados["credito_kwh"] = int(reais / tarifa)

    # Valor Sem Solar
    if dados.get("valor_pago") is not None and dados.get("credito_reais") is not None:
        dados["valor_sem_solar"] = round(dados.get("valor_pago") + dados.get("credito_reais"), 2)

    # Garante campos nulos se não encontrados
    for c in ["valor_pago", "credito_kwh", "credito_reais", "valor_sem_solar", "saldo_credito", "kwh_faturado"]:
        dados.setdefault(c, None)
    
    logger.info("✅ %s: %s", p.name, dados)
    return dados

if __name__ == "__main__":
    import sys, json
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1:
        print(json.dumps(parsear_fatura(sys.argv[1]), indent=2))
