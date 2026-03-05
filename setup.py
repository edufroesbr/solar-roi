import os
import json
import re

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    print("="*60)
    print("      Solar ROI - Assistente de Configuracao Inicial")
    print("="*60)
    print("\nEste script ira configurar o seu ambiente para o extrator.")
    print("Seus dados serao salvos localmente no arquivo .env e config.json.\n")

def get_input(prompt, pattern=None, error_msg="Entrada invalida."):
    while True:
        value = input(f"{prompt}: ").strip()
        if not value:
            print("Campo obrigatorio.")
            continue
        if pattern and not re.match(pattern, value):
            print(error_msg)
            continue
        return value

def setup():
    print_banner()

    # 1. Credenciais do Portal
    print("--- 1. Credenciais Neoenergia ---")
    cpf = get_input("Digite seu CPF (apenas numeros)", r"^\d{11}$", "Digite exatamente 11 digitos.")
    # Formata CPF: XXX.XXX.XXX-XX
    cpf_fmt = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    senha = input("Digite sua Senha do Portal Neoenergia: ").strip()

    # 2. Unidades Consumidoras
    print("\n--- 2. Unidades Consumidoras (UCs) ---")
    ucs = []
    while True:
        uc_raw = get_input("Numero da UC (ex: 03178785-X ou 03178785X)", r"^[a-zA-Z0-9\-]+$", "Use apenas números, letras e hífens.")
        
        # Normaliza: Remove hífens existentes e adiciona no local correto (penúltima posição)
        uc_clean = uc_raw.replace("-", "").upper()
        if len(uc_clean) > 1:
            uc_num = f"{uc_clean[:-1]}-{uc_clean[-1]}"
        else:
            uc_num = uc_clean
            
        uc_nome = get_input(f"Nome Apelido para a UC {uc_num} (ex: Casa, Oficina)")
        
        ucs.append({
            "uc": uc_num,
            "responsavel": uc_nome,
            "proporcao": 0.0,
            "payload": ""
        })
        
        cont = input("\nDeseja adicionar outra UC? (s/n): ").lower()
        if cont != 's':
            break

    # 3. Parametros de ROI
    print("\n--- 3. Analise de Investimento (Para o Dashboard) ---")
    data_inicio = get_input("Data de inicio do projeto (ex: 2026-01)", 
                            pattern=r"^\d{4}-\d{2}$", 
                            error_msg="Use o formato AAAA-MM (ex: 2026-01).")
    
    invest_raw = get_input("Valor Total do Investimento (ex: R$ 25.000,00)", 
                           pattern=r"^(R\$\s?)?(\d{1,3}(\.\d{3})*|\d+)(,\d{2})?$", 
                           error_msg="Use o formato R$ 00,00 ou apenas números.")
    
    # Limpa o valor para converter em float: remove "R$", remove "." de milhar, troca "," por "."
    invest_clean = invest_raw.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    investimento = float(invest_clean)
    
    # 4. Grava .env
    print("\nSalvando arquivos de configuracao...")
    env_content = f"""# Neoenergia Portal Credentials
NEO_CPF={cpf_fmt}
NEO_SENHA={senha}

# reCAPTCHA Automation (Opceional)
API_KEY_2CAPTCHA=

# SMTP Email Notifications (Opcional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
"""
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)
    
    # 5. Grava config.json
    config_data = {
        "_comment": "Solar ROI System - Configuration",
        "investimento_total": float(investimento),
        "data_inicio": data_inicio,
        "reajuste_anual_percent": 6.0,
        "unidades": ucs,
        "portal": {
            "base_url": "https://agenciavirtual.neoenergiabrasilia.com.br",
            "historico_url": "https://agenciavirtual.neoenergiabrasilia.com.br/HistoricoConsumo",
            "rate_limit_seconds": 4,
            "headless": False
        },
        "output": {
            "json_path": "dados_faturas.json",
            "pdf_base_dir": "faturas"
        },
        "filtro": {
            "data_inicio_referencia": data_inicio
        }
    }
    
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)

    print("\n" + "="*60)
    print("CONFIGURACAO CONCLUIDA COM SUCESSO!")
    print("="*60)
    print("\nArquivos gerados: .env e config.json")
    print("Agora voce pode rodar a extracao:")
    print("  python extractor.py --todos --auto")
    print("\nLembre-se: NUNCA compartilhe o arquivo .env ou config.json.")

if __name__ == "__main__":
    try:
        setup()
    except KeyboardInterrupt:
        print("\nConfiguracao cancelada pelo usuario.")
