"""
extractor.py — Automação Playwright para Neoenergia Brasília
=============================================================

Extrai dados de consumo e faz download de faturas em PDF.
Versão Restaurada: Foca na estabilidade original e suporte multi-perfil.
"""

import argparse
import asyncio
import json
import logging
import os
import random
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Dependências
# ---------------------------------------------------------------------------
try:
    from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PwTimeout
    try:
        from playwright_stealth import stealth_async
    except ImportError:
        from playwright_stealth import Stealth
        stealth_async = Stealth().apply_stealth_async
except ImportError:
    print("[ERRO] Playwright não instalado.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("extractor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("extractor")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
PROFILES_ROOT = Path("profiles")
CURRENT_PROFILE = "BIMBATO"
BASE_URL = "https://agenciavirtual.neoenergiabrasilia.com.br"
RATE_LIMIT_SECONDS = 4
DATA_INICIO_FILTRO = "2026-01"

def get_config_path() -> Path: return PROFILES_ROOT / CURRENT_PROFILE / "config.json"
def get_dados_path() -> Path: return PROFILES_ROOT / CURRENT_PROFILE / "dados_faturas.json"

def carregar_config() -> dict:
    cpath = get_config_path()
    if not cpath.exists(): return {}
    with cpath.open(encoding="utf-8") as f: return json.load(f)

def carregar_dados() -> dict:
    dpath = get_dados_path()
    if dpath.exists():
        with dpath.open(encoding="utf-8") as f: return json.load(f)
    return {"investimento_total": 0, "data_inicio": DATA_INICIO_FILTRO, "unidades": {}}

def salvar_dados(dados: dict) -> None:
    dpath = get_dados_path()
    # Salva no perfil e no dashboard public
    for p in [dpath, Path("dashboard/public/dados_faturas.json")]:
        if not p.parent.exists(): p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
            tmp.replace(p)
        except:
            if tmp.exists(): tmp.unlink()

# ---------------------------------------------------------------------------
# Simulação Humana
# ---------------------------------------------------------------------------
async def _simular_humano(page: Page):
    try:
        for _ in range(random.randint(1, 3)):
            await page.mouse.move(random.randint(100, 700), random.randint(100, 500), steps=10)
            await asyncio.sleep(random.uniform(0.1, 0.4))
    except: pass

async def _clicar_humanizado(page: Page, selector_or_loc):
    try:
        loc = page.locator(selector_or_loc).first if isinstance(selector_or_loc, str) else selector_or_loc
        await loc.scroll_into_view_if_needed()
        box = await loc.bounding_box()
        if box:
            await page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2, steps=15)
            await asyncio.sleep(0.2)
        await loc.click(delay=random.randint(50, 150))
        return True
    except: return False

async def _digitar_humano(element, texto: str):
    await asyncio.sleep(0.5)
    for char in texto:
        await element.type(char, delay=random.randint(100, 250))
    await asyncio.sleep(0.5)

# ---------------------------------------------------------------------------
# CAPTCHA
# ---------------------------------------------------------------------------
async def resolver_captcha(page: Page) -> bool:
    """Tenta resolver ou aguarda manual."""
    try:
        iframe = page.frame_locator('iframe[title*="reCAPTCHA"]').first
        checkbox = iframe.locator(".recaptcha-checkbox-border").first
        if await checkbox.is_visible():
            logger.info("Tentando resolver CAPTCHA...")
            await _clicar_humanizado(page, checkbox)
            await asyncio.sleep(4)
            checked = await iframe.locator("#recaptcha-anchor").get_attribute("aria-checked")
            if checked != "false": return True
    except: pass
    logger.info("Captcha pendente. Aguardando resolução manual/áudio...")
    return False

# ---------------------------------------------------------------------------
# Navegação e Extração
# ---------------------------------------------------------------------------
async def autenticar(page: Page, cpf: str, senha: str) -> bool:
    await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
    if "Servicos" in page.url: return True

    if not await page.locator("input#cpfCnpjModal").is_visible():
        await _clicar_humanizado(page, "button.login-button, .btn-primary:has-text('Entrar')")
        await asyncio.sleep(2)

    await _digitar_humano(page.locator("input#cpfCnpjModal"), cpf)
    await _digitar_humano(page.locator("input#senhaModal"), senha)
    
    await resolver_captcha(page)
    
    print("\n" + "!"*50 + "\nRESOLVA O CAPTCHA SE NECESSÁRIO NO NAVEGADOR\n" + "!"*50 + "\n")
    
    for _ in range(300): # 5 min
        if any(x in page.url for x in ["Servicos", "Historico", "UnidadeConsumidora"]):
            logger.info("Acesso autorizado.")
            return True
        await asyncio.sleep(1)
    return False

async def descobrir_ucs_ativas(page: Page) -> List[str]:
    """Retorna uma lista de códigos de UC que estão com status 'ligado' ou 'ativa'."""
    if "/Servicos" not in page.url or "/Servicos/Menu" in page.url:
        await page.goto(f"{BASE_URL}/Servicos", wait_until="networkidle")
    
    await asyncio.sleep(4)
    rows = page.locator("table#unidades tbody tr, .unit-card, tr[role='row']")
    count = await rows.count()
    
    ucs_encontradas = []
    for i in range(count):
        txt = (await rows.nth(i).inner_text()).lower()
        is_ativa = any(s in txt for s in ["ligado", "ativa", "ativo", "conectada"])
        if is_ativa:
            match = re.search(r"(\d{1,3}\.?\d{3}\.?\d{3}-[A-Z0-9])", txt, re.I)
            if match:
                ucs_encontradas.append(match.group(1))
    
    logger.info("UCs ativas descobertas: %s", ucs_encontradas)
    return ucs_encontradas

async def processar_uc(page: Page, uc_info: dict, dados: dict, mes_filtro: str = None) -> bool:
    uc_alvo = uc_info.get("uc")
    logger.info("Iniciando UC: %s", uc_alvo if uc_alvo else "Automatizada")

    # 1. Lista de Unidades
    if "/Servicos" not in page.url or "/Servicos/Menu" in page.url:
        await page.goto(f"{BASE_URL}/Servicos", wait_until="networkidle")
    
    await asyncio.sleep(3)
    await page.screenshot(path="debug_lista_unidades.png")
    logger.info("Screenshot da lista de unidades salvo em debug_lista_unidades.png")
    
    # Seletores estáveis baseados no HTML real
    rows = page.locator("table#unidades tbody tr, .unit-card, tr[role='row']")
    count = await rows.count()
    logger.info("Total de linhas detectadas na lista: %d", count)
    
    idx_ativa = -1
    idx_alvo = -1
    
    for i in range(count):
        txt = (await rows.nth(i).inner_text()).lower()
        logger.info("Linha %d texto: %s", i, txt.replace('\n', ' '))
        
        is_ativa = any(s in txt for s in ["ligado", "ativa", "ativo", "conectada"])
        if not is_ativa: continue
        
        if idx_ativa == -1: idx_ativa = i
        
        if uc_alvo:
            clean_alvo = "".join(re.findall(r'\d', uc_alvo))
            if clean_alvo in "".join(re.findall(r'\d', txt)):
                idx_alvo = i
                break
                
    # Define qual índice usar
    final_idx = idx_alvo if idx_alvo != -1 else idx_ativa
    
    if final_idx == -1:
        logger.error("Nenhuma UC ativa encontrada.")
        return False

    if idx_alvo == -1 and uc_alvo:
        logger.warning("UC alvo '%s' não encontrada ou inativa. Usando alternativa ativa.", uc_alvo)

    row = rows.nth(final_idx)
    # Captura o código real para atualizar config/dados
    match_uc = re.search(r"(\d{1,3}\.?\d{3}\.?\d{3}-[A-Z0-9])", await row.inner_text())
    if match_uc: uc_info["uc"] = match_uc.group(1)
    
    logger.info("Acessando UC: %s", uc_info["uc"])
    # Clique no botão que contém o link de serviços (payload)
    btn = row.locator("a[href*='payload']").first
    href_payload = await btn.get_attribute("href")
    
    await _clicar_humanizado(page, btn)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(4)
    await page.screenshot(path="debug_pos_clique_uc.png")
    logger.info("Screenshot pós-clique UC salvo.")

    # 2. Histórico de Consumo
    # Tenta encontrar o botão ou redirecionar
    try:
        hist_btn = page.locator("a[href*='HistoricoConsumo'], .card:has-text('Histórico'), :text('Histórico')").first
        if await hist_btn.is_visible():
            logger.info("Botão de histórico encontrado. Clicando...")
            await _clicar_humanizado(page, hist_btn)
        else:
            raise Exception("Botão não visível")
    except:
        logger.warning("Falha ao clicar no Histórico. Tentando redirecionamento forçado...")
        await page.goto(f"{BASE_URL}/HistoricoConsumo", wait_until="networkidle")

    await asyncio.sleep(8) # Aumentado para buffering lento
    await page.screenshot(path="debug_pagina_historico.png")
    logger.info("Screenshot da página de histórico salvo.")
    
    # 3. Extração da Tabela
    faturas = await extrair_tabela_historico(page, mes_filtro)
    if not faturas:
        logger.warning("A tabela de histórico não carregou para a UC %s.", uc_info["uc"])
        return False

    # 4. Salvamento e Download
    if uc_info["uc"] not in dados["unidades"]:
        dados["unidades"][uc_info["uc"]] = {"faturas": []}
    
    uc_db = dados["unidades"][uc_info["uc"]]
    for f in faturas:
        # Verifica duplicata
        v_existente = next((x for x in uc_db["faturas"] if x["referencia"] == f["referencia"]), None)
        
        pdf_path = None
        if f.get("pdf_url"):
            pdf_path = await baixar_pdf(page, uc_info["uc"], f["referencia"], f["pdf_url"])
        
        if v_existente:
            v_existente.update(f)
            if pdf_path: v_existente["pdf_path"] = pdf_path
        else:
            if pdf_path: f["pdf_path"] = pdf_path
            uc_db["faturas"].append(f)
            
    uc_db["faturas"].sort(key=lambda x: x["referencia"], reverse=True)
    return True

async def extrair_tabela_historico(page: Page, mes_filtro: str = None) -> List[dict]:
    # Espera por qualquer um dos IDs de tabela conhecidos ou tags genéricas
    try:
        await page.wait_for_selector("#protocolos, table.table, .dataTables_wrapper", timeout=20000)
    except: return []

    rows = page.locator("table tbody tr")
    count = await rows.count()
    lista = []
    
    for i in range(count):
        cells = rows.nth(i).locator("td")
        if await cells.count() < 7: continue
        
        texto_ref = (await cells.nth(0).inner_text()).strip()
        referencia = _normalizar_ref(texto_ref)
        if not referencia: continue
        if mes_filtro and mes_filtro != referencia: continue
        
        # Busca link do PDF (ícone de Olho Verde)
        pdf_url = ""
        link = cells.locator("a[href*='SegundaVia']").first
        if await link.count() > 0:
            pdf_url = urljoin(BASE_URL, await link.get_attribute("href"))
            
        fatura = {
            "mes": texto_ref,
            "referencia": referencia,
            "kwh_faturado": _limpar_valor(await cells.nth(5).inner_text()),
            "valor_pago": _limpar_valor(await cells.nth(6).inner_text()),
            "vencimento": (await cells.nth(7).inner_text()).strip(),
            "pdf_url": pdf_url
        }
        lista.append(fatura)
        logger.info("   Fatura detectada: %s", referencia)
    
    return lista

async def baixar_pdf(page: Page, uc: str, ref: str, url: str) -> Optional[str]:
    diretorio = PROFILES_ROOT / CURRENT_PROFILE / "faturas" / uc
    diretorio.mkdir(parents=True, exist_ok=True)
    fpath = diretorio / f"{ref}.pdf"
    
    if fpath.exists():
        logger.info("   PDF já existe: %s", ref)
        return str(fpath)
    
    logger.info("   Baixando PDF %s...", ref)
    try:
        # Tenta capturar o download disparado por navegação ou clique
        try:
            async with page.expect_download(timeout=20000) as dinfo:
                await page.goto(url)
            download = await dinfo.value
            await download.save_as(str(fpath))
            logger.info("   ✅ PDF salvo: %s", fpath)
            await asyncio.sleep(2)
            return str(fpath)
        except Exception as e1:
            logger.warning("   ⚠️ Falha no download via goto: %s. Tentando via request...", e1)
            
            # Fallback: requisição direta (pode precisar de cookies)
            response = await page.request.get(url)
            if response.ok:
                body = await response.body()
                fpath.write_bytes(body)
                logger.info("   ✅ PDF salvo (fallback request): %s", fpath)
                return str(fpath)
            else:
                logger.error("   ❌ Falha no download (Status: %d)", response.status)

    except Exception as e:
        logger.error("   ❌ Erro crítico ao baixar PDF %s: %s", ref, e)
    
    return None

def _normalizar_ref(raw: str) -> str:
    m = re.search(r"(\d{2})/(\d{4})", raw)
    if not m: return ""
    return f"{m.group(2)}-{m.group(1)}"

def _limpar_valor(txt: str) -> float:
    v = re.sub(r"[^\d,]", "", txt).replace(",", ".")
    try: return float(v)
    except: return 0.0

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(args):
    global CURRENT_PROFILE
    CURRENT_PROFILE = args.profile
    
    config = carregar_config()
    if not config: return logger.error("Perfil %s não encontrado.", CURRENT_PROFILE)

    dados = carregar_dados()
    ucs = config.get("unidades", []) or [{"uc": ""}]
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            accept_downloads=True
        )
        page = await context.new_page()
        await stealth_async(page)
        
        if await autenticar(page, config["cpf"], config["senha"]):
            # Se --todos for passado, tenta descobrir UCs se a lista estiver vazia/genérica
            if args.todos:
                ucs_descobertas = await descobrir_ucs_ativas(page)
                for code in ucs_descobertas:
                    # Adiciona se não estiver na lista
                    if not any(u.get("uc") == code for u in ucs):
                        ucs.append({"uc": code})
                
                # Remove UC vazia se descobrimos algo
                ucs = [u for u in ucs if u.get("uc")]

            for uc in ucs:
                if not uc.get("uc") and not args.todos:
                    # Se não tem UC e não quer todos, pula ou processa default
                    continue
                    
                sucesso = await processar_uc(page, uc, dados, args.mes)
                if sucesso and uc.get("uc"):
                    # Atualiza config se for uma UC nova
                    if not any(u.get("uc") == uc["uc"] for u in config.get("unidades", [])):
                        config.setdefault("unidades", []).append({"uc": uc["uc"]})
                        with get_config_path().open("w", encoding="utf-8") as f:
                            json.dump(config, f, indent=2)
        
        await browser.close()
    
    salvar_dados(dados)
    try:
        from sync_json_with_pdfs import sync
        sync(profile=CURRENT_PROFILE)
    except: pass
    logger.info("Fim do processamento para o perfil: %s", CURRENT_PROFILE)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mes")
    p.add_argument("--todos", action="store_true")
    p.add_argument("--uc")
    p.add_argument("--profile", default="BIMBATO")
    p.add_argument("--auto", action="store_true")
    asyncio.run(main(p.parse_args()))
