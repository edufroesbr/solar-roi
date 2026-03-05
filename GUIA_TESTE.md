# 🧪 Guia de Teste - Solar ROI

Este guia orienta o teste do fluxo completo de extração e análise, simulando a experiência de um novo usuário.

## 1. Configuração do Ambiente
Certifique-se de ter as dependências instaladas:
```bash
pip install -r requirements.txt
playwright install chromium
```

## 2. Assistente de Setup
Execute o assistente para configurar suas UCs e credenciais de forma anônima e segura.
> [!NOTE]
> O assistente agora suporta UCs terminadas em **X** (ex: `03212774-X`).

```bash
python setup.py
```
**Instruções no prompt:**
- Informe seu CPF e Senha (ficarão salvos apenas no seu `.env` local).
- Adicione suas Unidades Consumidoras (o script formata o hífen automaticamente).
- Informe o valor total do seu investimento solar (formato: `R$ 25.000,00`).

## 3. Rodando o Extrator
Inicie o processo de coleta automática:
```bash
python extractor.py --todos --auto
```
> [!IMPORTANT]
> **reCAPTCHA**: O bot costuma ter sucesso em superar o reCAPTCHA automaticamente. Entretanto, se o portal solicitar um desafio visual complexo, você verá a janela do navegador e poderá resolver manualmente para que a extração continue.

- O robô abrirá o navegador, fará login e baixará os PDFs na pasta `faturas/`.
- Os dados serão consolidados em `dados_faturas.json`.

## 4. Visualizando o Dashboard
Para ver seu ROI e Break-even:
1. Inicie o servidor: `python -m http.server 8888`
2. Acesse: `http://localhost:8888`

---
*Dúvidas? Verifique o README.md principal para detalhes técnicos.*
