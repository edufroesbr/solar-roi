"""
extractor.py — Automação Playwright para Neoenergia Brasília
=============================================================

Extrai dados de consumo e faz download de faturas em PDF
das 3 Unidades Consumidoras (UCs) configuradas no config.json.

Uso:
    python extractor.py --todos               # Extrai todos os meses >=2026-01
    python extractor.py --mes 2026-01         # Extrai um mês específico
    python extractor.py --mes 2026-02
    python extractor.py --uc 03178785-1 --mes 2026-01
    python extractor.py --auto                # Stub para uso futuro sem CAPTCHA

Dependências:
    pip install -r requirements.txt
    playwright install chromium

Variáveis de ambiente (.env):
    NEO_CPF    — CPF do titular (ex: 000.000.000-00)
    NEO_SENHA  — Senha da Agência Virtual
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

from sync_json_with_pdfs import sync as sync_pdf_data

# ---------------------------------------------------------------------------
# Dependências externas — avisa se ausentes
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[AVISO] python-dotenv não instalado. Use: pip install -r requirements.txt")
    sys.exit(1)

try:
    from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PwTimeout
    try:
        from playwright_stealth import stealth_async
    except ImportError:
        # Fallback para playwright-stealth 2.x
        from playwright_stealth import Stealth
        stealth_async = Stealth().apply_stealth_async
except ImportError:
    print("[ERRO] playwright ou playwright-stealth não instalado. Use: pip install playwright playwright-stealth && playwright install chromium")
    sys.exit(1)

try:
    from parser_fatura import parsear_fatura
    PARSER_DISPONIVEL = True
except ImportError:
    PARSER_DISPONIVEL = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("extractor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("extractor")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
CONFIG_PATH = Path("config.json")
DADOS_PATH = Path("dados_faturas.json")
DADOS_PUBLIC_PATH = Path("dashboard/public/dados_faturas.json")
BASE_URL = "https://agenciavirtual.neoenergiabrasilia.com.br"
HISTORICO_URL = f"{BASE_URL}/HistoricoConsumo"
RATE_LIMIT_SECONDS = 4  # Aumentado para evitar flooding
DATA_INICIO_FILTRO = "2026-01"  # Formato AAAA-MM


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def carregar_config() -> dict:
    """Carrega config.json. Levanta FileNotFoundError se ausente."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def carregar_dados() -> dict:
    """Carrega dados_faturas.json. Retorna estrutura vazia se ausente."""
    if DADOS_PATH.exists():
        with DADOS_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {"investimento_total": 22900.00, "data_inicio": DATA_INICIO_FILTRO, "unidades": {}}


def salvar_dados(dados: dict) -> None:
    """Salva dados_faturas.json de forma atômica em múltiplos locais."""
    paths = [DADOS_PATH]
    if DADOS_PUBLIC_PATH.parent.exists():
        paths.append(DADOS_PUBLIC_PATH)

    for p in paths:
        tmp = p.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        tmp.replace(p)
    logger.info("Dados salvos em: %s", [str(p) for p in paths])


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def _referencia_valida(referencia: str, filtro_mes: Optional[str] = None) -> bool:
    """Retorna True se a referência MM/YYYY ou AAAA-MM >= DATA_INICIO_FILTRO."""
    try:
        # Aceita 'Jan/2026' ou '2026-01'
        if "/" in referencia and len(referencia) <= 8:
            # Formato MM/YYYY como 'Jan/2026' ou '01/2026'
            partes = referencia.split("/")
            ano = int(partes[1])
            # Tenta mês numérico
            try:
                mes = int(partes[0])
            except ValueError:
                # Mês abreviado em português
                meses_ptbr = {
                    "jan": 1, "fev": 2, "mar": 3, "abr": 4,
                    "mai": 5, "jun": 6, "jul": 7, "ago": 8,
                    "set": 9, "out": 10, "nov": 11, "dez": 12,
                }
                mes = meses_ptbr.get(partes[0].lower()[:3], 0)
            ref_dt = datetime(ano, mes, 1)
        else:
            ref_dt = datetime.strptime(referencia, "%Y-%m")

        inicio_dt = datetime.strptime(DATA_INICIO_FILTRO, "%Y-%m")
        if filtro_mes:
            filtro_dt = datetime.strptime(filtro_mes, "%Y-%m")
            return ref_dt == filtro_dt
        return ref_dt >= inicio_dt
    except Exception:
        logger.debug("Referência inválida: %r", referencia)
        return False


def _gerar_browser_mask() -> Dict:
    """Gera uma máscara de identidade aleatória para o navegador."""
    import random
    profiles = [
        {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
            "device_scale_factor": 1
        },
        {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "viewport": {"width": 1440, "height": 900},
            "device_scale_factor": 2
        },
        {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
            "viewport": {"width": 1366, "height": 768},
            "device_scale_factor": 1
        }
    ]
    return random.choice(profiles)

async def _simular_humano(page: Page):
    """Realiza pequenas oscilações de mouse e esperas variáveis."""
    import random
    import math
    try:
        # Move o mouse em uma pequena curva senoidal
        start_x, start_y = random.randint(100, 800), random.randint(100, 600)
        await page.mouse.move(start_x, start_y)
        
        for i in range(10):
            offset = 5 * math.sin(i * 0.5)
            await page.mouse.move(start_x + i * 5, start_y + offset)
            await asyncio.sleep(0.05)
            
        await asyncio.sleep(random.uniform(0.5, 1.5))
    except:
        pass

async def _clicar_analogico(page: Page, element_or_selector):
    """Clica em um elemento simulando movimento humano com jitter (oscilação)."""
    import random
    import math
    try:
        if isinstance(element_or_selector, str):
            element = page.locator(element_or_selector).first
        else:
            element = element_or_selector
            
        if not await element.is_visible():
            return False
            
        box = await element.bounding_box()
        if not box:
            return False
            
        target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        
        # Posição inicial do mouse
        await page.mouse.move(random.randint(0, 100), random.randint(0, 100))
        
        # Caminho com "jitter"
        steps = random.randint(15, 25)
        for i in range(steps):
            t = (i + 1) / steps
            # Interpolação simples + jitter
            curr_x = target_x * t + (random.uniform(-3, 3))
            curr_y = target_y * t + (random.uniform(-3, 3))
            await page.mouse.move(curr_x, curr_y)
            if i % 5 == 0: await asyncio.sleep(0.01)

        await asyncio.sleep(random.uniform(0.2, 0.4))
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15)) # Tempo de clique real
        await page.mouse.up()
        return True
    except Exception as e:
        logger.warning("Falha ao clicar analógico: %s", e)
        return False

async def _clicar_humanizado(page: Page, element_or_selector):
    """Fallback para clique simplificado se o analógico falhar."""
    return await _clicar_analogico(page, element_or_selector)

async def _digitar_humano(element, texto: str):
    """Digita texto com intervalos longos entre teclas e pausas deliberadas."""
    import random
    # Pequena pausa antes de começar a digitar (pensamento humano)
    await asyncio.sleep(random.uniform(0.6, 1.2))
    for i, char in enumerate(texto):
        await element.type(char, delay=random.randint(120, 350)) # Mais lento
        # Simula erro ocasional ou hesitação
        if i > 0 and i % 5 == 0:
            await asyncio.sleep(random.uniform(0.4, 0.8))
    await asyncio.sleep(random.uniform(0.8, 1.5))

def _normalizar_referencia(ref: str) -> Optional[str]:
    """Converte 'Jan/2026' -> '2026-01'."""
    meses_ptbr = {
        "jan": "01", "fev": "02", "mar": "03", "abr": "04",
        "mai": "05", "jun": "06", "jul": "07", "ago": "08",
        "set": "09", "out": "10", "nov": "11", "dez": "12",
    }
    try:
        if "/" in ref:
            partes = ref.split("/")
            if len(partes) != 2:
                return ref
            
            mes_str = partes[0].strip().lower()[:3]
            ano = partes[1].strip()
            
            # Tenta meses abreviados
            mes_num = meses_ptbr.get(mes_str)
            if mes_num:
                return f"{ano}-{mes_num}"
            
            # Tenta meses numéricos (ex: 01/2026)
            p0 = partes[0].strip()
            if p0.isdigit():
                mes_num = p0.zfill(2)
                return f"{ano}-{mes_num}"
            
            # Já está no formato YYYY-MM?
            if re.match(r"^\d{4}-\d{2}$", ref):
                return ref
                
        return ref
    except Exception:
        return None


def _limpar_valor(texto: str) -> Optional[float]:
    """Extrai valor numérico de strings como 'R$ 100,68'."""
    if not texto:
        return None
    texto = re.sub(r"[^\d,.]", "", texto.strip())
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
async def autenticar(page: Page, cpf: str, senha: str, modo_auto: bool = False) -> bool:
    """Realiza login na Agência Virtual da Neoenergia Brasília.
    
    Combina simulação humana, coordenadas de clique e espera inteligente.
    """
    logger.info("Navegando para o portal...")
    try:
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60_000)
        
        # Se já estiver em uma URL interna, pula login
        if any(x in page.url for x in ["Servicos", "Historico", "UnidadeConsumidora"]):
            logger.info("Sessao ja ativa detectada (%s). Pulando login.", page.url)
            return True
            
        # 1. Abre modal de login se necessário
        if not await page.locator("input#cpfCnpjModal").is_visible():
            logger.info("Abrindo modal de login...")
            trigger = page.locator(".full-width-button.mat-accent, .login-button:has-text('Login')").first
            await trigger.click()
            await asyncio.sleep(2)

        # 2. Preenche campos
        campo_cpf = page.locator("input#cpfCnpjModal").first
        campo_senha = page.locator("input#senhaModal").first
        
        await campo_cpf.wait_for(state="visible", timeout=20_000)
        
        # Digitação humanizada
        await _clicar_humanizado(page, campo_cpf)
        await _digitar_humano(campo_cpf, cpf)
        
        if senha:
            await _clicar_humanizado(page, campo_senha)
            await _digitar_humano(campo_senha, senha)
        else:
            logger.warning("🔑 Senha não encontrada no .env. Preencha manualmente se necessário.")

        # 3. Resolução de CAPTCHA
        if modo_auto:
            logger.info("Tentando resolver CAPTCHA automaticamente...")
            sucesso_captcha = await resolver_captcha(page)
            if not sucesso_captcha:
                logger.warning("⚠️ Falha na automacao do CAPTCHA. Verifique a tela - Screenshot salva.")
                await page.screenshot(path="debug_captcha_fail.png")

        # 4. Finalização do login
        btn_entrar = page.locator("button.login-submit-button").first
        
        if modo_auto:
            # Em modo auto, tentamos clicar no botão se ele habilitar (espera pelo Angular)
            try:
                # O reCAPTCHA leva uns segundos para soltar o botão
                for _ in range(10): 
                    if await btn_entrar.is_enabled():
                        logger.info("Botao ENTRAR habilitado! Clicando...")
                        await _clicar_humanizado(page, btn_entrar)
                        break
                    await asyncio.sleep(1)
            except:
                pass

        # 5. Espera redirecionamento ou Intervenção Manual
        logger.info("Aguardando acesso à área logada...")
        max_wait_manual = 300 # 5 min
        
        for i in range(max_wait_manual):
            # Se a URL mudou para área interna, sucesso!
            if any(x in page.url for x in ["Servicos", "Historico", "UnidadeConsumidora"]):
                logger.info("Login confirmado! Area logada atingida: %s", page.url)
                return True
            
            # Avisa o usuário no modo interativo (não-auto)
            if not modo_auto and i == 0:
                print("\n" + "!" * 50)
                print("ACAO NECESSARIA: Resolva o CAPTCHA no navegador.")
                print("Aguardando redirecionamento automaticamente...")
                print("!" * 50 + "\n")

            # Verifica erros visíveis na tela
            erro_loc = page.locator(".alert-danger, .error-message, .mat-error").first
            if await erro_loc.is_visible():
                txt_erro = await erro_loc.inner_text()
                logger.error("❌ Erro detectado no portal: %s", txt_erro)
                if modo_auto: return False

            await asyncio.sleep(1)
            
        logger.error("❌ Timeout aguardando redirecionamento após login.")
        return False

    except Exception as e:
        logger.error("❌ Falha crítica no fluxo de autenticação: %s", e)
        try: await page.screenshot(path="error_auth_critical.png")
        except: pass
        return False


# ---------------------------------------------------------------------------
# Extração da tabela de histórico
# ---------------------------------------------------------------------------
async def processar_uc(
    page: Page,
    uc_config: dict,
    dados: dict,
    config: dict,
    filtro_mes: Optional[str] = None,
) -> None:
    """Extrai, baixa e parseia todas as faturas de uma UC e atualiza dados."""
    uc = uc_config["uc"]
    logger.info("--- Processando UC: %s ---", uc)

    # --- VERIFICAÇÃO DE DADOS JÁ COLETADOS ---
    # COMENTADO PARA FORÇAR RE-EXTRAÇÃO COMPLETA CONFORME SOLICITADO
    # if filtro_mes and filtro_mes != "todos":
    #     uc_data = dados.get("unidades", {}).get(uc, {})
    #     faturas = uc_data.get("faturas", [])
    #     ja_existe = any(f.get("referencia") == filtro_mes for f in faturas)
    #     if ja_existe:
    #         logger.info("⏩ UC %s para o mês %s já consta no banco. Pulando...", uc, filtro_mes)
    #         return

    # 1. Navegação Dinâmica: Home -> UC -> Menu -> Histórico
    try:
        # Garantir que estamos na lista de unidades
        if "/Servicos" not in page.url or "/Servicos/Menu" in page.url:
             logger.info("Retornando para a lista de unidades...")
             await page.goto(f"{BASE_URL}/Servicos", wait_until="networkidle", timeout=30_000)
        
        # Aguarda a lista carregar (pode ser tabela ou cards)
        # O seletor 'table' é mais genérico para a lista vista no screenshot
        await page.wait_for_selector("table, .mat-mdc-card, .unit-card", timeout=20_000)
        await asyncio.sleep(2) 
        
        await page.screenshot(path="debug_lista_uc.png")

        # Localiza a UC específica na lista
        logger.info("Buscando UC %s na lista...", uc)
        
        encontrou = False
        
        # Estratégia A: Busca em Tabelas (conforme visto no screenshot)
        rows = page.locator("table tbody tr")
        count = await rows.count()
        
        for i in range(count):
            row = rows.nth(i)
            texto_row = await row.inner_text()
            
            # LOG BRUTO PARA DEBUG DE UC NAO ENCONTRADA
            logger.debug("   [DEBUG UC LIST] Linha %d: %s", i, texto_row.replace("\n", " | ").strip())

            # Normaliza para comparação (remove hífens, pontos e espaços)
            uc_clean = re.sub(r'[^0-9]', '', uc)
            row_clean = re.sub(r'[^0-9]', '', texto_row)
            
            if uc_clean and uc_clean in row_clean:
                # 1.1 Verificação de STATUS (Ativa/Ligada)
                status_texto = texto_row.lower()
                is_ativa = any(s in status_texto for s in ["ligada", "ligado", "ativa", "ativo", "conectada"])
                
                logger.debug("UC %s detectada na linha. Texto completo: %s", uc, texto_row.strip())
                
                if not is_ativa:
                    logger.warning("UC %s ignorada: Status nao esta LIGADA/ATIVA. (Texto: %s)", uc, texto_row.strip())
                    return
                
                logger.info("UC %s encontrada e ativa. Clicando...", uc)
                
                # Scroll para garantir visibilidade
                await row.scroll_into_view_if_needed()
                
                # Tenta clicar no botão verde visto no screenshot
                btn = row.locator("button, a").filter(has_text=uc_clean).first
                if not await btn.is_visible():
                    btn = row.locator("button, a, td").first
                
                await _clicar_humanizado(page, btn)
                
                # Aguarda confirmação de que saímos da lista e entramos no menu
                try:
                    await page.wait_for_selector("mat-card, .menu-servicos, a[href*='HistoricoConsumo'], a[href*='SegundaVia']", timeout=15_000)
                    encontrou = True
                    break
                except:
                    logger.warning("Aguardando carregamento do menu da UC %s...", uc)
                    await page.wait_for_load_state("networkidle")
                    if "Servicos/Menu" in page.url or "UnidadeConsumidora" in page.url:
                        encontrou = True
                        break
        
        # Estratégia B: Fallback para Cards se Estratégia A falhar
        if not encontrou:
            cards = page.locator("mat-card, .card-unidade, .mdc-card, .unit-card")
            count_cards = await cards.count()
            for i in range(count_cards):
                card = cards.nth(i)
                card_text = await card.inner_text()
                if uc in card_text or uc.replace("-", "") in card_text:
                    await _clicar_humanizado(page, card.locator("button, a").first)
                    encontrou = True
                    break

        if not encontrou:
            logger.error("UC %s nao encontrada na lista ou inacessivel.", uc)
            return
            
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        await page.screenshot(path="debug_menu_uc.png")

        # 2. No Menu, clica em "Histórico de Consumo"
        # O HTML mostra cards dentro de .row.novoCard
        seletores_historico = [
            ".novoCard a[href*='HistoricoConsumo']",
            "a:has(h4:has-text('Histórico'))",
            "text='Histórico de Consumo'",
            "a[href*='HistoricoConsumo']"
        ]
        
        href_completo = None
        card_historico = None
        for sel in seletores_historico:
            loc = page.locator(sel).first
            if await loc.is_visible():
                card_historico = loc
                # Captura o href real do link <a>
                href = await loc.get_attribute("href")
                if not href:
                    href = await loc.evaluate("el => el.closest('a')?.getAttribute('href')")
                
                if href:
                    href_completo = urljoin(BASE_URL, href)
                    if "HistoricoConsumo" not in href_completo:
                        continue
                break
        
        if not card_historico:
            logger.error("Opcao 'Historico' nao encontrada para UC %s.", uc)
            return
            
        logger.info("Clicando em Historico de Consumo...")
        # Simula aproximação humana e clica analógico no BOX (não apenas no texto)
        await _simular_humano(page)
        await _clicar_analogico(page, card_historico)
        
        # Buffering humano: espera o site carregar a próxima etapa
        await asyncio.sleep(random.uniform(4, 7))
        await page.wait_for_load_state("networkidle")
        
        # Verifica se realmente entrou na URL de histórico
        if "HistoricoConsumo" not in page.url:
            # Tenta um goto direto USANDO O PAYLOAD EXTRAÍDO
            if href_completo:
                logger.warning("Clique no menu nao mudou a URL. Tentando acesso direto com payload...")
                await page.goto(href_completo, wait_until="networkidle", timeout=30_000)
            else:
                logger.warning("Clique no menu nao mudou a URL. Tentando acesso direto simples (sem payload)...")
                await page.goto(f"{BASE_URL}/HistoricoConsumo", wait_until="networkidle", timeout=30_000)

        logger.info("Pagina de historico acessada para UC %s.", uc)

    except Exception as e:
        logger.error("Falha na navegao para UC %s: %s", uc, e)
        await page.screenshot(path=f"error_nav_{uc}.png")
        return

    # 2. Extração do histórico
    historico = await extrair_historico(page, uc, filtro_mes)
    if not historico:
        logger.warning("Nenhuma fatura encontrada para UC %s.", uc)
        return

    # Atualiza ou cria entrada da UC nos dados
    if uc not in dados["unidades"]:
        dados["unidades"][uc] = {"faturas": []}
    
    uc_dados = dados["unidades"][uc]
    uc_dados["responsavel"] = uc_config.get("responsavel", "Titular")
    uc_dados["proporcao"] = uc_config.get("proporcao", 0.0)

    # Garante que dados globais de investimento estao sincronizados
    dados["investimento_total"] = config.get("investimento_total", dados.get("investimento_total", 0.0))
    dados["data_inicio"] = config.get("data_inicio", dados.get("data_inicio", DATA_INICIO_FILTRO))

    # Índice de faturas existentes para evitar duplicatas (normalizando a referência)
    # Refatoração: usamos a "referencia" (Ex: 2026-01) como chave primária
    faturas_map = {f["referencia"]: f for f in uc_dados.get("faturas", [])}

    for item in historico:
        ref = item.get("referencia")
        if not ref:
            continue

        # Download do PDF se disponível e se ainda não tivermos o PDF ou o valor solar
        # (Prioriza baixar novos ou atualizar vazios)
        fatura_existente = faturas_map.get(ref)
        ja_tem_pdf = fatura_existente and fatura_existente.get("pdf_path")
        
        pdf_path = None
        dados_pdf = None

        if item.get("pdf_url"):
            pdf_path = await baixar_pdf(page, uc, ref, item["pdf_url"])
            await asyncio.sleep(RATE_LIMIT_SECONDS)
        else:
            logger.debug("   [AVISO] Link de PDF nao encontrado para fatura %s.", ref)

            # Parse do PDF (Sempre re-faz o parse para garantir que novos campos sejam capturados)
            if pdf_path and PARSER_DISPONIVEL:
                try:
                    dados_pdf = parsear_fatura(pdf_path)
                except Exception as exc:
                    logger.warning("Erro no parse do PDF %s: %s", pdf_path, exc)
        
        # Cria ou atualiza a fatura
        nova_fatura = _mesclar_fatura(item, fatura_existente, pdf_path, dados_pdf)
        
        if ref in faturas_map:
            # Atualiza no lugar
            for idx, f in enumerate(uc_dados["faturas"]):
                if f["referencia"] == ref:
                    uc_dados["faturas"][idx] = nova_fatura
                    break
        else:
            uc_dados["faturas"].append(nova_fatura)
            faturas_map[ref] = nova_fatura

    # Ordena faturas por data
    uc_dados["faturas"].sort(key=lambda x: x["referencia"], reverse=True)

async def extrair_historico(page: Page, uc: str, mes_filtro: str = None) -> List[Dict]:
    """
    Extrai as linhas da tabela de histórico de consumo (12 colunas) com buffering resiliente.
    """
    try:
        # Buffering: espera a tabela ou qualquer indicador de dados carregar
        # Adicionados seletores de Angular Material e tabelas genéricas
        seletores_tabela = [
            "#protocolos tbody tr",
            "table.table tbody tr",
            "mat-table mat-row",
            ".mdc-data-table__row",
            "table tr:has(td)"
        ]
        
        logger.info("   Aguardando carregamento dos dados (buffering)...")
        tabela_detectada = False
        for _ in range(40): # 40 segundos total
            # Check se fomos redirecionados de volta ao menu por erro de session/payload
            if "/Servicos/Menu" in page.url or "/Servicos/Unidades" in page.url:
                logger.error("❌ Redirecionado para o menu! A sessao ou o payload da UC %s expirou.", uc)
                return []

            for sel in seletores_tabela:
                loc = page.locator(sel).first
                if await loc.is_visible():
                    tabela_detectada = True
                    break
            if tabela_detectada: break
            await asyncio.sleep(1)
            
        if not tabela_detectada:
            logger.error("❌ Timeout: Dados nao carregados para UC %s. Screenshot de erro salvo.", uc)
            await page.screenshot(path=f"debug_timeout_table_{uc}.png")
            return []

        # Tenta pegar as linhas da tabela usando o seletor que funcionou
        linhas_loc = None
        for sel in seletores_tabela:
             if await page.locator(sel).first.is_visible():
                 linhas_loc = page.locator(sel)
                 break
        
        count = await linhas_loc.count()
        logger.info("   Encontradas %d linhas na tabela.", count)

        if count > 0:
            html_debug = await linhas_loc.nth(0).inner_html()
            logger.debug("   [DEBUG HTML] Estrutura da primeira linha: %s", html_debug[:500])

        faturas_extraidas = []
        for i in range(count):
            linha = linhas_loc.nth(i)
            # Busca todas as células possíveis na linha
            celulas_loc = linha.locator("td, mat-cell, .mat-cell, .mdc-data-table__cell, [role='cell'], > div")
            num_celulas = await celulas_loc.count()
            
            logger.debug("   [LINHA %d] Celulas encontradas: %d", i, num_celulas)
            
            if num_celulas < 2:
                content = await linha.inner_text()
                logger.debug("   [LINHA %d] Ignorada (texto: %s)", i, content.strip()[:100])
                continue

            # Loga o texto de cada célula para diagnóstico
            textos_celulas = []
            for j in range(num_celulas):
                textos_celulas.append((await celulas_loc.nth(j).inner_text()).strip())
            
            logger.debug("   [LINHA %d] CONTEUDO: %s", i, " | ".join(textos_celulas))

            ref_texto = textos_celulas[0] if num_celulas > 0 else ""
            if not ref_texto or "/" not in ref_texto or len(ref_texto) > 10:
                logger.debug("   [LINHA %d] Descartada: '%s' nao parece uma referencia (MM/AAAA)", i, ref_texto)
                continue

            referencia = _normalizar_referencia(ref_texto)
            if not referencia: 
                logger.debug("   [LINHA %d] Falha ao normalizar referencia: %s", i, ref_texto)
                continue
            
            # Filtro por mês se solicitado
            if mes_filtro and mes_filtro != referencia:
                continue

            # Captura o link do PDF (Prioridade: Olho Verde com HREF)
            pdf_url = ""
            # O seletor abaixo busca especificamente links <a> que tenham o ícone e um href
            link_pdf_loc = celulas_loc.locator("a[href*='SegundaVia']:has(i.glyphicon-eye-open)").first
            if await link_pdf_loc.count() == 0:
                # Fallback: qualquer link com href na última célula (Segunda Via)
                link_pdf_loc = celulas_loc.last.locator("a[href]").first
            
            if await link_pdf_loc.count() > 0:
                href = await link_pdf_loc.get_attribute("href")
                if href and href != "#":
                    pdf_url = urljoin(BASE_URL, href)
                    logger.debug("   [PDF] URL detectada: %s", pdf_url[:100] + "...")
                else:
                    logger.debug("   [PDF] Link ignorado (sem href valido)")

            fatura = {
                "mes": ref_texto,
                "referencia": referencia,
                "leitura": textos_celulas[3] if num_celulas > 3 else "",
                "kwh_faturado": _limpar_valor(textos_celulas[5]) if num_celulas > 5 else 0,
                "valor_pago": _limpar_valor(textos_celulas[6]) if num_celulas > 6 else 0,
                "vencimento": textos_celulas[7] if num_celulas > 7 else "",
                "data_pagamento": textos_celulas[8] if num_celulas > 8 else "",
                "pdf_url": pdf_url,
                "extra": {
                    "tp_fatura": textos_celulas[1] if num_celulas > 1 else "",
                    "data_leitura": textos_celulas[2] if num_celulas > 2 else ""
                }
            }
            logger.info("   [CAPTURA] Fatura %s: %d kWh, R$ %.2f", referencia, fatura["kwh_faturado"], fatura["valor_pago"])
            faturas_extraidas.append(fatura)

        return faturas_extraidas

    except Exception as exc:
        logger.error("Falha ao extrair historico da UC %s: %s", uc, exc)
        try: await page.screenshot(path=f"error_extract_{uc}.png")
        except: pass
        return []


# ---------------------------------------------------------------------------
# Download de PDFs
# ---------------------------------------------------------------------------
async def baixar_pdf(page: Page, uc: str, referencia: str, pdf_href: str) -> Optional[str]:
    """Baixa o PDF da fatura e salva em faturas/{uc}/{referencia}.pdf.

    Retorna o caminho salvo ou None se falhar.
    """
    if not pdf_href:
        return None

    pasta = Path("faturas") / uc
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{referencia}.pdf"

    if caminho.exists():
        logger.info("PDF ja existe: %s", caminho)
        return str(caminho)

    logger.info("Baixando PDF: %s", pdf_href)
    try:
        async with page.expect_download(timeout=30_000) as download_info:
            await page.goto(pdf_href)
        download = await download_info.value
        await download.save_as(str(caminho))
        await asyncio.sleep(RATE_LIMIT_SECONDS)
        logger.info("PDF salvo: %s", caminho)
        return str(caminho)
    except PwTimeout:
        logger.warning("   Timeout ao baixar PDF %s — tentando via response...", pdf_href)
    except Exception as exc:
        logger.error("   ❌ Erro ao baixar PDF: %s", exc)

    # Fallback: tenta via response direto
    try:
        response = await page.request.get(pdf_href)
        if response.ok:
            body = await response.body()
            caminho.write_bytes(body)
            logger.info("PDF salvo (fallback): %s", caminho)
            return str(caminho)
    except Exception as exc2:
        logger.error("   ❌ Fallback também falhou: %s", exc2)

    return None


# ---------------------------------------------------------------------------
# Montagem de objeto fatura
# ---------------------------------------------------------------------------
def _mesclar_fatura(item_extraido: dict, fatura_existente: Optional[dict], pdf_path: Optional[str], dados_pdf: Optional[dict]) -> dict:
    """
    Mescla dados extraídos da tabela, do PDF e de faturas já existentes.
    Preserva dados calculados (valor_sem_solar, etc) se já existirem.
    """
    ref = item_extraido["referencia"]
    
    # Base: dados da tabela
    fatura = {
        "mes": item_extraido.get("mes", ""),
        "referencia": ref,
        "kwh_faturado": item_extraido["kwh_faturado"],
        "valor_pago": item_extraido["valor_pago"],
        "vencimento": item_extraido["vencimento"],
        "data_pagamento": item_extraido["data_pagamento"],
        "pdf_path": pdf_path or (fatura_existente.get("pdf_path") if fatura_existente else None),
        "fonte": "extraido",
        "valor_sem_solar": fatura_existente.get("valor_sem_solar") if fatura_existente else None,
        "credito_kwh": fatura_existente.get("credito_kwh") if fatura_existente else None,
        "credito_reais": fatura_existente.get("credito_reais") if fatura_existente else None,
        "saldo_credito": fatura_existente.get("saldo_credito") if fatura_existente else None,
    }

    # Se houve parse do PDF, atualiza campos (sobrescreve se o PDF for mais confiável)
    if dados_pdf:
        for campo in ["valor_pago", "credito_kwh", "credito_reais", "valor_sem_solar", "saldo_credito", "kwh_faturado"]:
            if dados_pdf.get(campo) is not None:
                fatura[campo] = dados_pdf[campo]
        fatura["fonte"] = "extraido+pdf"

    # Se a fatura existente tinha fonte 'seed', preservamos os campos que não conseguimos extrair
    if fatura_existente:
        if fatura_existente.get("fonte") == "seed":
            fatura["fonte"] = "seed+extraido"
        
        # Mantém campos que podem ter sido inseridos manualmente e não estão no novo fluxo
        for k, v in fatura_existente.items():
            if k not in fatura or fatura[k] is None:
                fatura[k] = v

    return fatura


# ---------------------------------------------------------------------------
# Processamento de uma UC
# ---------------------------------------------------------------------------
# LEGACY processar_uc removido - Unified dynamic navigation version is above
# Fim dos helpers de faturas


# ---------------------------------------------------------------------------
# Ponto de entrada principal
# ---------------------------------------------------------------------------
def enviar_email(assunto: str, corpo: str) -> None:
    """
    Envia notificação para os destinatários configurados usando SMTP.
    """
    destinatarios = [
        "edufroes@gmail.com", 
        "analima.lima50@gmail.com", 
        "marina.limavale@gmail.com"
    ]
    
    # Credenciais SMTP do .env (Sugestão: usar Gmail ou SendGrid)
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        logger.warning("Credenciais SMTP nao configuradas. E-mail nao enviado.")
        return

    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import smtplib

    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = ", ".join(destinatarios)
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        logger.info("E-mail enviado com sucesso para %s!", ", ".join(destinatarios))
    except Exception as e:
        logger.error("❌ Falha ao enviar e-mail: %s", e)


async def resolver_captcha_audio(page) -> bool:
    """
    Resolve o reCAPTCHA v2 usando o desafio de áudio e Speech Recognition.
    Inspirado em scripts open-source para Playwright.
    """
    import random
    import urllib.request
    try:
        from speech_recognition import Recognizer, AudioFile
    except ImportError:
        logger.error("❌ Módulo 'speech_recognition' não encontrado. Instale com: pip install SpeechRecognition")
        return False
        
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.error("❌ Módulo 'pydub' não encontrado. Instale com: pip install pydub")
        return False
    
    logger.info("Tentando resolver via desafio de áudio (Speech Recognition)...")
    
    try:
        # 1. Localiza o iframe do reCAPTCHA
        iframe_element = page.locator("iframe[title='reCAPTCHA']").first
        if not await iframe_element.is_visible():
            logger.warning("Iframe do reCAPTCHA não encontrado.")
            return False
            
        # Screenshot inicial do estado do Captcha
        await page.screenshot(path="debug_recaptcha_check_pre.png")

        # Pega o frame
        name = await iframe_element.get_attribute("name")
        recaptcha_frame = page.frame(name=name)
        
        # Clica no checkbox usando coordenadas para simular humano
        checkbox = recaptcha_frame.locator(".recaptcha-checkbox-border")
        await _clicar_humanizado(page, checkbox) 
        await asyncio.sleep(2)
        
        # Screenshot para debug visual solicitado pelo usuário
        await page.screenshot(path="debug_recaptcha_click.png")
        
        # Verifica se já resolveu (às vezes resolve só no clique pelo histórico)
        # Atenção: em SPAs Angular, o atributo pode demorar a atualizar
        await asyncio.sleep(2)
        checked = await recaptcha_frame.locator("#recaptcha-anchor").get_attribute("aria-checked")
        if checked != "false":
            logger.info("reCAPTCHA resolvido automaticamente pelo clique (cookies/histórico).")
            return True
            
        # Detecta se abriu o puzzle de imagens (bframe)
        logger.info("Detectando se puzzle de imagens foi aberto...")
        bframe_element = page.locator("iframe[src*='api2/bframe']").first
        
        # Aguarda um tempo para o puzzle carregar se existir
        puzzle_visible = False
        for _ in range(5):
            if await bframe_element.is_visible():
                puzzle_visible = True
                break
            await asyncio.sleep(1)
            
        if not puzzle_visible:
            logger.warning("Puzzle de imagens não apareceu. Tentando verificar se ja logou...")
            checked = await recaptcha_frame.locator("#recaptcha-anchor").get_attribute("aria-checked")
            return checked != "false"

        # Tira foto do puzzle para confirmação
        await page.screenshot(path="debug_recaptcha_puzzle_detected.png")
        logger.info("🧩 Puzzle detectado. Tentando via áudio...")

        bname = await bframe_element.get_attribute("name")
        challenge_frame = page.frame(name=bname)
        
        # Clica no botão de áudio (humanizado)
        btn_audio = challenge_frame.locator("#recaptcha-audio-button")
        await _clicar_humanizado(page, btn_audio)
        await asyncio.sleep(3)
        
        # 3. Pega o link do áudio
        audio_link = await challenge_frame.locator(".rc-audiochallenge-tdownload-link").get_attribute("href")
        if not audio_link:
            logger.warning("Link do áudio não encontrado.")
            return False
            
        # 4. Processa o áudio
        audio_path = "recaptcha_audio.mp3"
        wav_path = "recaptcha_audio.wav"
        
        await asyncio.to_thread(urllib.request.urlretrieve, audio_link, audio_path)
        
        # Converte para WAV (SpeechRecognition prefere WAV)
        # Atenção: requer FFmpeg instalado no sistema!
        try:
            audio_seg = await asyncio.to_thread(AudioSegment.from_mp3, audio_path)
            await asyncio.to_thread(audio_seg.export, wav_path, format="wav")
        except Exception as pydub_err:
            logger.error("Falha ao converter audio mp3 -> wav. O FFmpeg esta instalado no PATH?")
            logger.debug("Erro pydub: %s", pydub_err)
            return False
        
        # Reconhecimento de fala
        recognizer = Recognizer()
        with AudioFile(wav_path) as source:
            audio_data = await asyncio.to_thread(recognizer.record, source)
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language="pt-BR")
            
        logger.info("Texto extraído do áudio: '%s'", text)
        
        # 5. Preenche e confirma (humanizado)
        await challenge_frame.fill("#audio-response", text)
        btn_verify = challenge_frame.locator("#recaptcha-verify-button")
        await _clicar_humanizado(page, btn_verify)
        await asyncio.sleep(3)
        
        # Print final do estado
        await page.screenshot(path="debug_recaptcha_solved.png")
        
        # Limpa arquivos temporários
        for f in [audio_path, wav_path]:
            if os.path.exists(f): os.remove(f)
            
        # Verifica se resolveu
        checked = await recaptcha_frame.locator("#recaptcha-anchor").get_attribute("aria-checked")
        return checked != "false"
        
    except Exception as e:
        logger.error("❌ Falha na resolução por áudio: %s", e)
        return False


async def resolver_captcha(page) -> bool:
    """
    Resolve o reCAPTCHA v2 usando a biblioteca 2captcha-python ou Interação Humana Analógica.
    """
    # 0. Interação Humana na Checkbox (Prevenir reconhecimento imediato de bot)
    try:
        # Procura o iframe do reCAPTCHA
        logger.info("Simulando clique humano analogico na checkbox do reCAPTCHA...")
        iframe_loc = page.frame_locator('iframe[title*="reCAPTCHA"]').first
        checkbox = iframe_loc.locator(".recaptcha-checkbox-border").first
        
        if await checkbox.is_visible():
            # Move o mouse para perto do iframe primeiro (simula aproximação)
            await _simular_humano(page)
            # Clique analógico real (coordenadas + jitter)
            await _clicar_analogico(page, checkbox)
            await asyncio.sleep(random.uniform(2, 4))
    except Exception as e:
        logger.debug("Clique analogico na checkbox falhou (iframe nao encontrado?): %s", e)

    api_key = os.getenv("API_KEY_2CAPTCHA")
    if not api_key or api_key == "SUA_CHAVE_AQUI":
        logger.info("API Key do 2Captcha nao configurada. Tentando audio fallback...")
        return await resolver_captcha_audio(page)
    
    # Tenta usar stealth se disponível (reduz a incidência de CAPTCHA)
    await stealth_async(page)
    
    from twocaptcha import TwoCaptcha
    
    try:
        logger.info("Iniciando resolucao automatica do reCAPTCHA...")
        
        # 1. Localiza o sitekey no iframe do reCAPTCHA ou no elemento Angular
        captcha_element = page.locator(".g-recaptcha, ngx-recaptcha2").first
        site_key = await captcha_element.get_attribute("data-sitekey")
        
        if not site_key:
            # Fallback 1: tenta buscar na URL de qualquer iframe do Google Recaptcha
            logger.info("Sitekey nao encontrado em atributos. Buscando em iframes...")
            iframes = page.frames
            for frame in iframes:
                if "google.com/recaptcha" in frame.url:
                    match = re.search(r"k=([A-Za-z0-9_-]+)", frame.url)
                    if match:
                        site_key = match.group(1)
                        logger.info("Sitekey extraído do iframe: %s", site_key)
                        break
        
        if not site_key:
            # Fallback 2: tenta buscar no script ou em outros elementos comuns
            site_key = await page.evaluate("() => document.querySelector('.g-recaptcha')?.getAttribute('data-sitekey') || document.querySelector('ngx-recaptcha2')?.getAttribute('data-sitekey') || window.recaptcha_sitekey")
            
        if not site_key:
            logger.warning("Sitekey nao encontrado. Tentando audio fallback...")
            return await resolver_captcha_audio(page)

        solver = TwoCaptcha(api_key)
        
        # 2. Solicita resolução
        result = await asyncio.to_thread(
            solver.recaptcha,
            sitekey=site_key,
            url=page.url
        )
        
        if result and "code" in result:
            code = result["code"]
            logger.info("reCAPTCHA resolvido com sucesso! Injetando token...")
            
            # 3. Injeta a solução no campo oculto e dispara eventos para Angular/React
            # Rastreia o campo exato e injeta o valor
            await page.evaluate(f"""
                const token = "{code}";
                const textareas = [
                    document.getElementById("g-recaptcha-response"),
                    ...document.getElementsByName("g-recaptcha-response")
                ];
                textareas.forEach(el => {{
                    if (el) {{
                        el.value = token;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }});
            """)
            
            # 4. Tenta disparar o callback se existir
            logger.info("Tentando disparar callbacks de submissao (Angular/Standard)...")
            # Usando uma string de função pura para evitar problemas de CSP com injeção de argumentos
            await page.evaluate(f"""
                (function() {{
                    const el = document.querySelector('.g-recaptcha, ngx-recaptcha2');
                    if (!el) return;
                    const callback = el.getAttribute('data-callback');
                    const token = "{code}";
                    if (callback && window[callback]) {{
                        window[callback](token);
                    }} else if (typeof onSubmit === 'function') {{
                        onSubmit(token);
                    }}
                }})();
            """)
            
            # Pequeno aguardo para "buffering" de processamento do site
            await asyncio.sleep(2)
            return True
        
        return False
        
    except Exception as e:
        logger.error("❌ Erro ao resolver CAPTCHA automaticamente: %s", e)
        return False


async def main(args: argparse.Namespace) -> None:
    """Orquestra a extração completa."""
    # Verificação de FFmpeg (essencial para áudio CAPTCHA)
    import subprocess
    ffmpeg_ok = False
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ffmpeg_ok = True
    except:
        logger.warning("\n" + "!" * 60 + "\n[AVISO CRÍTICO] FFmpeg não encontrado no PATH.\n"
                       "A resolução automática de CAPTCHA via Áudio irá falhar.\n"
                       "Instale o FFmpeg e adicione ao PATH do Windows.\n" + "!" * 60 + "\n")

    # Credenciais
    cpf = os.getenv("NEO_CPF")
    senha = os.getenv("NEO_SENHA")

    if not cpf:
        logger.error(
            "❌ CPF não encontrado!\n"
            "   Crie um arquivo .env com:\n"
            "     NEO_CPF=seu.cpf"
        )
        sys.exit(1)

    if not senha:
        logger.warning("🔑 Senha não encontrada no .env. Será necessário digitar manualmente.")

    # Configuração
    config = carregar_config()
    dados = carregar_dados()

    # Define UCs alvo
    ucs_config = config.get("unidades", [])
    if args.uc:
        ucs_config = [u for u in ucs_config if u["uc"] == args.uc]
        if not ucs_config:
            logger.error("❌ UC '%s' não encontrada no config.json.", args.uc)
            sys.exit(1)

    # Define filtro de mês
    filtro_mes = None if args.todos else args.mes

    logger.info(
        "\nSolar ROI - Extrator Neoenergia Brasilia"
        "\n   UCs: %s"
        "\n   Filtro: %s"
        "\n   Modo auto: %s\n",
        [u["uc"] for u in ucs_config],
        filtro_mes or "todos >= " + DATA_INICIO_FILTRO,
        args.auto,
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=config.get("portal", {}).get("headless", False), 
            slow_mo=100,
            args=["--start-maximized"],
        )
        # Browser Identity Rotation
        mask = _gerar_browser_mask()
        logger.info("Mascara de identidade aplicada: %s (%dx%d)", 
                    mask["user_agent"][:50] + "...", 
                    mask["viewport"]["width"], 
                    mask["viewport"]["height"])

        context: BrowserContext = await browser.new_context(
            no_viewport=True, # Necessário para --start-maximized funcionar de fato
            viewport=None,    # Deve ser None se no_viewport=True
            accept_downloads=True,
            user_agent=mask["user_agent"],
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        page = await context.new_page()
        
        # Ativa o mascaramento (stealth) na página
        await stealth_async(page)

        # Autenticação
        autenticado = await autenticar(page, cpf, senha, args.auto)
        if not autenticado:
            logger.error("Falha na autenticacao. Encerrando.")
            try:
                await browser.close()
            except:
                pass
            sys.exit(1)

        # Processa cada UC
        for uc_info in ucs_config:
            try:
                await processar_uc(page, uc_info, dados, config, filtro_mes)
            except Exception as exc:
                logger.error("❌ Erro ao processar UC %s: %s", uc_info.get("uc"), exc)

        await browser.close()

    # Salva dados do portal antes da sincronização fina com PDFs
    salvar_dados(dados)

    # Sincroniza dados extraídos com o conteúdo dos PDFs
    logger.info("⚡ Iniciando sincronização inteligente com PDFs baixados...")
    try:
        sync_pdf_data()
    except Exception as e:
        logger.error("Erro na sincronização de PDFs: %s", e)

    logger.info("\nExtracao concluida! Resultado em: %s", DADOS_PATH)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrator de faturas Neoenergia Brasília (Playwright)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python extractor.py --mes 2026-01\n"
            "  python extractor.py --mes 2026-02\n"
            "  python extractor.py --todos\n"
            "  python extractor.py --uc 03178785-1 --mes 2026-01\n"
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--mes",
        metavar="AAAA-MM",
        help="Extrai apenas o mês especificado (ex: 2026-01)",
    )
    group.add_argument(
        "--todos",
        action="store_true",
        help="Extrai todos os meses a partir de Jan/2026",
    )
    parser.add_argument(
        "--uc",
        metavar="CODIGO_UC",
        help="Processa apenas a UC especificada (ex: 03178785-1)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="(Futuro) Modo sem interação humana — reCAPTCHA automático",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args_cli = cli()
    asyncio.run(main(args_cli))
