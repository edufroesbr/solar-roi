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

def get_input(prompt, pattern=None, error_msg="Entrada inválida.", default=None):
    while True:
        p = f"{prompt} [{default}]" if default else prompt
        value = input(f"{p}: ").strip()
        if not value:
            if default is not None:
                return default
            print("Campo obrigatório.")
            continue
        if pattern and not re.match(pattern, value):
            print(error_msg)
            continue
        return value

def find_profile_by_cpf(cpf_buscado):
    """Procura um perfil existente pelo CPF."""
    cpf_limpo = re.sub(r'[^0-9]', '', cpf_buscado)
    profiles_dir = "profiles"
    if not os.path.exists(profiles_dir):
        return None
    
    for item in os.listdir(profiles_dir):
        config_path = os.path.join(profiles_dir, item, "config.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    cpf_perfil = re.sub(r'[^0-9]', '', cfg.get("cpf", ""))
                    if cpf_perfil == cpf_limpo:
                        return item
            except:
                continue
    return None

def update_perfis_json(profile_id, profile_nome):
    """Garante que o perfil esteja no perfis.json do Dashboard."""
    path = os.path.join("profiles", "perfis.json")
    perfis = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                perfis = json.load(f)
        except:
            perfis = []
    
    # Verifica se já existe
    if not any(p.get("id") == profile_id for p in perfis):
        perfis.append({"id": profile_id, "nome": profile_nome})
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(perfis, f, indent=2, ensure_ascii=False)

def run_extractor(profile_id):
    """Dispara o extrator para o perfil selecionado."""
    print(f"\n🚀 Iniciando extrator para o perfil: {profile_id}...")
    import subprocess
    import sys
    
    python_exe = sys.executable
    cmd = [python_exe, "extractor.py", "--todos", "--profile", profile_id]
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Erro ao executar o extrator: {e}")
    except KeyboardInterrupt:
        print("\n⏹️ Execução interrompida pelo usuário.")

def setup():
    print_banner()

    # 1. Identificação
    print("--- 1. Identificação ---")
    cpf_raw = get_input("Digite seu CPF (apenas números)", r"^\d{11}$", "Digite exatamente 11 dígitos.")
    
    # Busca perfil existente
    profile_id = find_profile_by_cpf(cpf_raw)
    
    if profile_id:
        print(f"\n✅ Perfil encontrado: '{profile_id}'")
        confirm = input(f"Este CPF já possui uma configuração. Deseja rodar a extração agora? (S/n): ").lower()
        if confirm != 'n':
            run_extractor(profile_id)
            return
        
        reconfig = input("Deseja reconfigurar os dados deste perfil? (s/N): ").lower()
        if reconfig != 's':
            print("Operação cancelada.")
            return
    else:
        # Novo Perfil
        nome_sugerido = f"Usina_{cpf_raw[-4:]}"
        profile_id = get_input(f"Crie um Identificador para este perfil (ex: Usina_Dona_Ana)", 
                               pattern=r"^[a-zA-Z0-9_]+$", 
                               error_msg="Use apenas letras, números e underline.",
                               default=nome_sugerido)

    # 2. Credenciais do Portal
    print(f"\n--- 2. Dados de Acesso para {profile_id} ---")
    cpf_fmt = f"{cpf_raw[:3]}.{cpf_raw[3:6]}.{cpf_raw[6:9]}-{cpf_raw[9:]}"
    senha = input("Digite sua Senha do Portal Neoenergia: ").strip()

    # 3. Parametros de ROI
    print("\n--- 3. Parâmetros do Dashboard ---")
    data_inicio = get_input("Mês de início (ex: 2026-01)", 
                            pattern=r"^\d{4}-\d{2}$", 
                            error_msg="Use o formato AAAA-MM.")
    
    invest_raw = get_input("Investimento Total (ex: 22000)", 
                           pattern=r"^\d+$", 
                           error_msg="Digite apenas números inteiros.")
    
    # 4. Cria estrutura de pastas
    profile_dir = os.path.join("profiles", profile_id)
    os.makedirs(profile_dir, exist_ok=True)

    # 5. Salva config.json
    config_data = {
        "cpf": cpf_raw,
        "senha": senha,
        "investimento_total": float(invest_raw),
        "data_inicio": data_inicio,
        "unidades": [] # Será preenchido ou deixado para extração automática
    }
    
    config_path = os.path.join(profile_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

    # Atualiza lista do dashboard
    update_perfis_json(profile_id, profile_id.replace("_", " "))

    print(f"\n✅ Configuração salva em: {config_path}")
    
    runnow = input("\nDeseja rodar a extração agora? (S/n): ").lower()
    if runnow != 'n':
        run_extractor(profile_id)

if __name__ == "__main__":
    try:
        setup()
    except KeyboardInterrupt:
        print("\n\nConfiguração cancelada pelo usuário.")
