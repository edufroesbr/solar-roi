# 🌐 Guia de Produção e Acesso Online 24h

Para manter o sistema rodando 100% online e acessível de qualquer lugar, siga este roteiro de implantação em uma **VPS** (Servidor Virtual Privado).

## 1. Escolha da Hospedagem (VPS)
Recomendo opções de baixo custo ou gratuitas:
- **Oracle Cloud (Sempre Gratuito)**: Instância Ampere ou x86 (ideal).
- **DigitalOcean / Linode**: Planos de $4-6/mês.
- **AWS (Nivel Gratuito)**: Instância t3.micro.

## 2. Configuração do Servidor (Linux/Ubuntu)
Após acessar sua VPS via SSH:

```bash
# Atualize o sistema
sudo apt update && sudo apt upgrade -y

# Instale Python e dependências de Navegador
sudo apt install python3-pip -y
pip install -r requirements.txt
playwright install-deps
playwright install chromium
```

## 3. Automação 24h (Cron)
Para rodar a coleta automaticamente nos dias desejados, use o **Crontab**:

```bash
crontab -e
```

Adicione a linha abaixo para rodar todo dia às 08:00 (ajuste conforme preferência):
```cron
0 8 * * * cd /caminho/para/projeto && python3 extractor.py --todos --auto >> extractor.log 2>&1
```
*Nota: O sistema utiliza simulação humana (jitter de mouse e digitação cadenciada) para evitar bloqueios. A `API_KEY_2CAPTCHA` é essencial para automação 100% sem intervenção em servidores remotos.*

## 4. Acesso Online ao Dashboard
Para acessar o dashboard via navegador (ex: `http://sua-vps-ip:8080`):

### Opção A: Servidor Simples (Modo Fácil)
```bash
python3 -m http.server 8888
```
*Dica: Use `nohup` ou `screen` para manter o comando rodando após fechar o terminal.*

### Opção B: Nginx + Segurança (Recomendado)
Para proteger com senha (já que seus dados são sensíveis):
1. Instale o Nginx: `sudo apt install nginx`
2. Configure um `basic_auth` para pedir usuário e senha ao acessar o IP da VPS.

## 5. VPN e Segurança
Se você quiser acessar **apenas via VPN**:
- Instale o **Tailscale** ou **WireGuard** na sua VPS e no seu celular/PC.
- Configure o servidor HTTP para ouvir apenas no IP da interface da VPN.
- Assim, o dashboard não ficará exposto na internet pública.

---
**Status Final**: O sistema está pronto. Dados de Fevereiro processados com sucesso e robô configurado para automação total.
