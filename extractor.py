"""
extractor.py — Automação DrissionPage para Neoenergia Brasília
=============================================================

Extrai dados de consumo e faz download de faturas em PDF.
Versão 0.5: Migração para DrissionPage para máxima estabilidade no Windows.
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Dependências
# ---------------------------------------------------------------------------
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("[ERRO] DrissionPage não instalado. Execute: pip install DrissionPage")
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
CURRENT_PROFILE = "PADRAO"
BASE_URL = "https://agenciavirtual.neoenergiabrasilia.com.br"
DATA_INICIO_FILTRO = "2025-10"

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
            if tmp.exists():
                if p.exists(): p.unlink()
                tmp.rename(p)
        except Exception as e:
            logger.error(f"Erro ao salvar dados: {e}")
            if tmp.exists(): tmp.unlink()

# ---------------------------------------------------------------------------
# Simulação Humana
# ---------------------------------------------------------------------------
def _simular_humano(page: ChromiumPage):
    try:
        for _ in range(random.randint(1, 2)):
            page.actions.move_to((random.randint(100, 700), random.randint(100, 500)))
            time.sleep(random.uniform(0.1, 0.3))
    except: pass

def _clicar_humanizado(page: ChromiumPage, selector_or_ele):
    try:
        ele = page.ele(selector_or_ele) if isinstance(selector_or_ele, str) else selector_or_ele
        if not ele: return False
        
        # Scroll para o elemento
        ele.scroll.to_see()
        time.sleep(0.2)
        
        # Move o mouse até o elemento (se não estiver em modo headless escondido)
        try:
            page.actions.move_to(ele)
        except: pass
        
        time.sleep(random.uniform(0.1, 0.3))
        ele.click()
        return True
    except Exception as e:
        logger.debug(f"Falha ao clicar: {e}")
        return False

def _digitar_humano(ele, texto: str):
    if not ele: return
    ele.clear()
    time.sleep(0.3)
    for char in texto:
        ele.input(char)
        time.sleep(random.uniform(0.05, 0.15))
    time.sleep(0.3)

# ---------------------------------------------------------------------------
# CAPTCHA
# ---------------------------------------------------------------------------
def resolver_captcha(page: ChromiumPage) -> bool:
    """Detecta se há CAPTCHA e orienta o usuário."""
    try:
        iframe = page.get_frame('title:reCAPTCHA')
        if iframe:
            checkbox = iframe.ele('.recaptcha-checkbox-border')
            if checkbox:
                logger.info("CAPTCHA detectado. Tentando clique inicial...")
                checkbox.click()
                time.sleep(2)
    except: pass
    
    # Verifica se já passou
    if any(x in page.url for x in ["Servicos", "Historico", "UnidadeConsumidora"]):
        return True
        
    logger.info("Aguardando resolução do CAPTCHA manualmente no navegador...")
    return False

# ---------------------------------------------------------------------------
# Navegação e Extração
# ---------------------------------------------------------------------------
def autenticar(page: ChromiumPage, cpf: str, senha: str) -> bool:
    page.get(BASE_URL)
    time.sleep(2)
    
    if "Servicos" in page.url: return True

    btn_login = page.ele('button.login-button') or page.ele('.btn-primary@@text():Entrar')
    if btn_login:
        _clicar_humanizado(page, btn_login)
        time.sleep(2)

    input_cpf = page.ele('#cpfCnpjModal')
    if input_cpf:
        _digitar_humano(input_cpf, cpf)
        _digitar_humano(page.ele('#senhaModal'), senha)
        
        resolver_captcha(page)
        
        print("\n" + "!"*50 + "\nRESOLVA O CAPTCHA NO NAVEGADOR SE NECESSÁRIO\n" + "!"*50 + "\n")
        
        # Aguarda autorização (até 5 min)
        for _ in range(300):
            if any(x in page.url for x in ["Servicos", "Historico", "UnidadeConsumidora"]):
                logger.info("Acesso autorizado.")
                return True
            time.sleep(1)
    return False

def descobrir_ucs_ativas(page: ChromiumPage) -> List[str]:
    if "/Servicos" not in page.url or "/Servicos/Menu" in page.url:
        page.get(f"{BASE_URL}/Servicos")
    
    time.sleep(4)
    rows = page.eles('css:table#unidades tbody tr, .unit-card, tr[role="row"]')
    
    ucs_encontradas = []
    for row in rows:
        txt = row.text.lower()
        is_ativa = any(s in txt for s in ["ligado", "ativa", "ativo", "conectada"])
        if is_ativa:
            match = re.search(r"(\d{1,3}\.?\d{3}\.?\d{3}-[A-Z0-9])", txt, re.I)
            if match:
                ucs_encontradas.append(match.group(1))
    
    logger.info("UCs ativas descobertas: %s", ucs_encontradas)
    return ucs_encontradas

def processar_uc(page: ChromiumPage, uc_info: dict, dados: dict, mes_filtro: str = None) -> bool:
    uc_alvo = uc_info.get("uc")
    logger.info("Iniciando UC: %s", uc_alvo if uc_alvo else "Automatizada")

    if "/Servicos" not in page.url or "/Servicos/Menu" in page.url:
        page.get(f"{BASE_URL}/Servicos")
    
    time.sleep(3)
    
    rows = page.eles('css:table#unidades tbody tr, .unit-card, tr[role="row"]')
    idx_final = -1
    
    for i, row in enumerate(rows):
        txt = row.text.lower()
        is_ativa = any(s in txt for s in ["ligado", "ativa", "ativo", "conectada"])
        if not is_ativa: continue
        
        if not uc_alvo: # Pega a primeira ativa se não houver alvo
            idx_final = i
            break
            
        clean_alvo = "".join(re.findall(r'\d', uc_alvo))
        if clean_alvo in "".join(re.findall(r'\d', txt)):
            idx_final = i
            break
            
    if idx_final == -1:
        logger.error("Nenhuma UC ativa encontrada.")
        return False

    row = rows[idx_final]
    match_uc = re.search(r"(\d{1,3}\.?\d{3}\.?\d{3}-[A-Z0-9])", row.text)
    if match_uc: uc_info["uc"] = match_uc.group(1)
    
    logger.info("Acessando UC: %s", uc_info["uc"])
    btn = row.ele('tag:a@@href*payload')
    if btn:
        _clicar_humanizado(page, btn)
        time.sleep(4)
    else:
        logger.error("Botão de serviços não encontrado para esta UC.")
        return False

    # Histórico de Consumo
    try:
        hist_btn = page.ele('text:Histórico') or page.ele('css:a[href*="HistoricoConsumo"]')
        if hist_btn:
            _clicar_humanizado(page, hist_btn)
        else:
            page.get(f"{BASE_URL}/HistoricoConsumo")
    except:
        page.get(f"{BASE_URL}/HistoricoConsumo")

    time.sleep(6)
    
    faturas = extrair_tabela_historico(page, mes_filtro)
    if not faturas:
        logger.warning("Nenhuma fatura encontrada no histórico para %s.", uc_info["uc"])
        return False

    if uc_info["uc"] not in dados["unidades"]:
        dados["unidades"][uc_info["uc"]] = {"faturas": []}
    
    uc_db = dados["unidades"][uc_info["uc"]]
    for f in faturas:
        v_existente = next((x for x in uc_db["faturas"] if x["referencia"] == f["referencia"]), None)
        
        pdf_path = None
        if f.get("pdf_url"):
            pdf_path = baixar_pdf(page, uc_info["uc"], f["referencia"], f["pdf_url"])
        
        if v_existente:
            v_existente.update(f)
            if pdf_path: v_existente["pdf_path"] = pdf_path
        else:
            if pdf_path: f["pdf_path"] = pdf_path
            uc_db["faturas"].append(f)
            
    uc_db["faturas"].sort(key=lambda x: x["referencia"], reverse=True)
    return True

def extrair_tabela_historico(page: ChromiumPage, mes_filtro: str = None) -> List[dict]:
    lista = []
    
    for _ in range(5): # Tenta paginar algumas vezes
        rows = page.eles('css:table tbody tr')
        if not rows: break
        
        achou_antigo = False
        for row in rows:
            cells = row.eles('tag:td')
            if len(cells) < 7: continue
            
            texto_ref = cells[0].text.strip()
            referencia = _normalizar_ref(texto_ref)
            if not referencia: continue
            
            if referencia < DATA_INICIO_FILTRO:
                achou_antigo = True
                continue

            if any(f["referencia"] == referencia for f in lista):
                continue
                
            if mes_filtro and mes_filtro != referencia: continue
            
            pdf_url = ""
            link = row.ele('css:a[href*="SegundaVia"]')
            if link:
                pdf_url = urljoin(BASE_URL, link.attr('href'))
                
            fatura = {
                "mes": texto_ref,
                "referencia": referencia,
                "kwh_faturado": _limpar_valor(cells[5].text),
                "valor_pago": _limpar_valor(cells[6].text),
                "vencimento": cells[7].text.strip() if len(cells) > 7 else "",
                "pdf_url": pdf_url
            }
            lista.append(fatura)
            logger.info("   Fatura detectada: %s", referencia)
        
        if achou_antigo: break
            
        btn_prox = page.ele('text:Próximo') or page.ele('css:.paginate_button.next')
        if btn_prox and btn_prox.is_enabled():
            _clicar_humanizado(page, btn_prox)
            time.sleep(4)
        else:
            break
            
    return lista

def baixar_pdf(page: ChromiumPage, uc: str, ref: str, url: str) -> Optional[str]:
    diretorio = PROFILES_ROOT / CURRENT_PROFILE / "faturas" / uc
    diretorio.mkdir(parents=True, exist_ok=True)
    fpath = diretorio / f"{ref}.pdf"
    
    if fpath.exists():
        return str(fpath)
    
    logger.info("   Baixando PDF %s...", ref)
    try:
        # Configura o destino do download no DrissionPage
        page.set.download_path(str(diretorio))
        
        # Tenta disparar o download clicando no link ou navegando até a URL
        # DrissionPage captura downloads automaticamente se configurado
        page.download(url, rename=f"{ref}.pdf")
        
        if fpath.exists():
            logger.info("   ✅ PDF salvo: %s", fpath)
            return str(fpath)
    except Exception as e:
        logger.error("   ❌ Erro ao baixar PDF %s: %s", ref, e)
    
    return None

def _normalizar_ref(raw: str) -> str:
    m = re.search(r"(\d{2})/(\d{4})", raw)
    if not m: return ""
    return f"{m.group(2)}-{m.group(1)}"

def _limpar_valor(txt: str) -> float:
    v = re.sub(r"[^\d,]", "", txt).replace(",", ".")
    try: return float(v)
    except: return 0.0

def verificar_atualizacao_mensal(dados: dict, ucs_config: List[dict], mes_target: str = None) -> bool:
    if not mes_target:
        mes_target = datetime.now().strftime("%Y-%m")
    
    if not ucs_config: return False

    ucs_faltas = []
    for uc_item in ucs_config:
        uc_cod = uc_item.get("uc")
        if not uc_cod: continue
        
        faturas = dados.get("unidades", {}).get(uc_cod, {}).get("faturas", [])
        if not any(f.get("referencia") == mes_target for f in faturas):
            ucs_faltas.append(uc_cod)
            
    if not ucs_faltas: return True
        
    logger.info("Checkup: Faturas de %s ausentes para UCs: %s", mes_target, ucs_faltas)
    return False

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mes")
    parser.add_argument("--todos", action="store_true")
    parser.add_argument("--uc")
    parser.add_argument("--profile", default="PADRAO")
    args = parser.parse_args()

    global CURRENT_PROFILE
    CURRENT_PROFILE = args.profile
    
    config = carregar_config()
    if not config:
        logger.error("Perfil %s não encontrado.", CURRENT_PROFILE)
        return

    dados = carregar_dados()
    ucs = config.get("unidades", []) or [{"uc": ""}]
    
    # Checkup previo
    if not args.mes:
        mes_atual = datetime.now().strftime("%Y-%m")
        if verificar_atualizacao_mensal(dados, ucs, mes_atual):
            print("\n" + "="*70)
            logger.info("CHECKUP: Todas as UCs já possuem a fatura de %s.", mes_atual)
            print("="*70 + "\n")
            return

    # Browser Setup
    co = ChromiumOptions()
    
    # Previne conflitos com outras instâncias do Chrome abertas pelo usuário
    import random
    porta_aleatoria = random.randint(9223, 9350)
    co.set_paths(local_port=porta_aleatoria)
    
    # Opções de estabilidade para Windows
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    
    # Tenta iniciar o navegador com retentativas
    page = None
    for tentativa in range(3):
        try:
            page = ChromiumPage(co)
            if page: break
        except Exception as e:
            logger.warning(f"Tentativa {tentativa+1} de abrir o navegador falhou: {e}")
            time.sleep(2)
    
    if not page:
        logger.error("Não foi possível inicializar o navegador DrissionPage.")
        return

    try:
        if autenticar(page, config["cpf"], config["senha"]):
            if args.todos:
                ucs_descobertas = descobrir_ucs_ativas(page)
                for code in ucs_descobertas:
                    if not any(u.get("uc") == code for u in ucs):
                        ucs.append({"uc": code})
                ucs = [u for u in ucs if u.get("uc")]

            for uc in ucs:
                if not uc.get("uc") and not args.todos: continue
                    
                sucesso = processar_uc(page, uc, dados, args.mes)
                if sucesso and uc.get("uc"):
                    if not any(u.get("uc") == uc["uc"] for u in config.get("unidades", [])):
                        config.setdefault("unidades", []).append({"uc": uc["uc"]})
                        with get_config_path().open("w", encoding="utf-8") as f:
                            json.dump(config, f, indent=2)
        
        salvar_dados(dados)
        try:
            from sync_json_with_pdfs import sync
            sync(profile=CURRENT_PROFILE)
        except: pass
        logger.info("Fim do processamento para o perfil: %s", CURRENT_PROFILE)
        
    finally:
        page.quit()

if __name__ == "__main__":
    main()
