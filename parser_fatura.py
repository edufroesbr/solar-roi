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

# Regex para capturar o "Total a Pagar" (Neoenergia agrupa UC + Vencimento + Valor)
REGEX_VALOR_TOTAL = re.compile(
    r"(?:\d{3}\.\d{3}-[A-Z0-9]\s+\d{2}/\d{2}/\d{4}\s+)" # UC + Vencimento
    r"([\d]{1,3}(?:\.\d{3})*[.,][\d]{2})", # Valor (ex: 2.466,53)
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
    # Remove espaços e símbolos monetários
    texto = texto.replace(" ", "").replace("R$", "")
    
    # Caso 1: Formato brasileiro com ponto e virgula: 2.466,53 -> 2466.53
    if "." in texto and "," in texto:
        # Verifica se o ponto está antes da vírgula (milhar)
        if texto.find(".") < texto.find(","):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            # Caso raro: 2,466.53 (formato US)
            texto = texto.replace(",", "").replace(".", ".")
    # Caso 2: Apenas vírgula: 2466,53 -> 2466.53
    elif "," in texto:
        texto = texto.replace(",", ".")
    # Caso 3: Apenas pontos (ex: texto extraído falho ou milhar): 2.466.53 ou 2.466
    elif "." in texto:
        if texto.count(".") == 1:
            # Se tiver apenas um ponto, tratamos como decimal por segurança (padrão Neoenergia)
            # A menos que pareça um milhar sem decimal (ex: 2.466)
            pass 
        else:
            # Múltiplos pontos: 1.000.000 -> 1000000
            texto = texto.replace(".", "")
            
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
    dados_tabela = _parsear_via_tabelas(str(p))
    dados_regex = _parsear_via_regex(texto)
    
    # PRIORIADE TOTAL: REGEX (Captura melhor o campo "Total a Pagar" grande)
    dados = dados_regex.copy()
    
    # Preenche com dados da tabela se o regex falhou ou para campos complementares
    for k, v in dados_tabela.items():
        if k not in dados or dados[k] is None:
            dados[k] = v

    # Fallback de Saldo (Individual)
    if not dados.get("saldo_credito"):
        m = REGEX_SALDO_CREDITO.search(texto)
        if m: dados["saldo_credito"] = _converter_valor_br(m.group(1))

    # Inferência de Valores
    tarifa = dados.get("tarifa") or 0.95
    kwh = dados.get("credito_kwh")
    # PRIORIDADE: Se temos kWh (do rodapé), recalculamos os REAIS para evitar capturar DIC
    if kwh is not None and kwh > 0:
        dados["credito_reais"] = round(kwh * tarifa, 2)
        logger.debug("✅ Crédito Reais Priorizado (kWh * Tarifa): %s", dados["credito_reais"])
    # Fallback: Se não temos kWh mas achamos reais (negativo), usamos com cautela
    elif dados.get("credito_reais") and not kwh:
        # Mantém o valor que veio do regex negativo
        pass

    # Valor Sem Solar (Total Bruto que seria pago)
    if dados.get("valor_pago") is not None and dados.get("credito_reais") is not None:
        dados["valor_sem_solar"] = round(float(dados.get("valor_pago")) + float(dados.get("credito_reais")), 2)
    
    # Fallback: se não temos valor pago mas temos crédito e tarifa
    elif dados.get("credito_kwh") and dados.get("tarifa"):
        dados["valor_sem_solar"] = round(dados["credito_kwh"] * dados["tarifa"], 2)

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
