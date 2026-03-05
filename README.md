# Solar ROI - Automação de Extração e Análise de Break-even

Solução de RPA em Python para extração, consolidação e análise financeira de faturas de energia do portal Neoenergia Brasília. Projetada para investidores solares e gestores de múltiplas UCs, substitui conferência manual de PDFs por fluxo estruturado e auditável, com foco no cálculo preciso do break-even.

## 🚀 Objetivo do Projeto
- **Automação de Fluxo**: Extração robusta de faturas, superando desafios de reCAPTCHA.
- **Consolidação de Dados**: Agregamento de consumo e créditos solares em `dados_faturas.json`.
- **Análise Financeira**: Visualização do ROI e projeção do ponto de equilíbrio (*break-even*) via dashboard.
- **Auditoria**: Organização automática de PDFs em `faturas/`.

## 🛠️ Instalação e Configuração

### 1. Pré-requisitos
- Python 3.9+ e Node.js.
- FFmpeg (para áudio-captcha).
- Playwright:
  ```bash
  pip install -r requirements.txt
  playwright install chromium
  ```

### 2. Configuração Inicial (Setup)
Para garantir sua segurança e privacidade, o projeto utiliza um assistente de configuração. Execute o comando abaixo para informar suas credenciais e UCs de forma segura:
```bash
python setup.py
```
Este script criará os arquivos `.env` e `config.json` localmente. No passo de investimento, use o formato nacional (ex: `R$ 25.000,00`). **Nunca envie estes arquivos para o GitHub.**

## 📖 Como Usar
1. Após rodar o `setup.py`, inicie a extração:
   ```bash
   python extractor.py --todos --auto
   ```
2. **Nota sobre reCAPTCHA**: O robô possui algoritmos para superar o reCAPTCHA automaticamente (clique analógico e áudio-captcha). No entanto, em casos raros de detecção agressiva, o navegador abrirá para que você realize o desafio manualmente e o robô possa prosseguir.

3. Após a conclusão, os dados estarão em `dados_faturas.json`.
4. Para ver o Dashboard, abra o `index.html` (certifique-se de que um servidor local como `python -m http.server 8888` esteja rodando na raiz do projeto).

## 🔒 Segurança e Privacidade
- O arquivo `.gitignore` já está configurado para ignorar dados sensíveis.
- O script `setup.py` facilita a configuração sem que você precise editar arquivos JSON manualmente.
- Seus PDFs e dados de fatura são salvos apenas na sua máquina local.

---
*Transformando faturas de energia em inteligência financeira.*
