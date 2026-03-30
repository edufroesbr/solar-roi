# ☀️ Solar ROI: Automação e Análise de Break-even (Neoenergia)

Este repositório contém uma solução de RPA (Robotic Process Automation) desenvolvida em Python para extração, consolidação e análise financeira de faturas de energia do portal Neoenergia Brasília.

O sistema foi projetado para investidores de energia solar e gestores de múltiplas Unidades Consumidoras (UCs) que necessitam substituir a conferência manual de PDFs por um fluxo de dados estruturado, auditável e focado no cálculo preciso do *break-even* do investimento.

## 🚀 Capacidades do Sistema

* **Extração Resiliente (Web Scraping):** Navegação automatizada via Playwright com contramedidas nativas contra detecção de bots e resolução assistida de reCAPTCHA (via processamento de áudio-captcha).
* **Consolidação em Lote:** Agregação de histórico de consumo, injeção de energia e créditos solares acumulados em um banco de dados local (`dados_faturas.json`).
* **Inteligência Financeira:** Motor de cálculo que processa o custo evitado (economia) e projeta o Retorno sobre o Investimento (ROI) em um *dashboard* interativo local.
* **Auditoria Documental:** Download sistemático e arquivamento espelhado dos PDFs originais na pasta `faturas/` para *compliance* e conferência manual.

## 🌟 Novidades da Versão 0.2 (Premium Dashboard)
- **Novo Design System:** Interface completamente repaginada utilizando React, Recharts e TailwindCSS com paleta de cores Premium (Stitch Design).
- **Consolidação Tolerante a Falhas:** Nova injeção de lacunas modulares que garante a exibição de unidades ativas mesmo em meses em que faturas ainda não foram emitidas ou falharam no download ("Sem Fatura").
- **Métricas Individuais (% ROI):** Acompanhamento minucioso de rentabilidade com o novo atributo "ROI U.C." apontando a representatividade exata de recuo de investimento de cada microgerador individualmente.
- **Formatações Localizadas (pt-BR):** Correção da formatação de decimais padrão americano, forçando pontuação brasileira (`2,240%`) e leitura correta de numerais longos no front-end.
- **Apelido de Unidades (Aliases):** Suporte total a exibição do nome reduzido ou customizado da Unidade Consumidora (`03178785-1 - Ana Maria`), eliminando a confusão entre múltiplos contratos.

## 🛠️ Arquitetura e Pré-requisitos

Esta ferramenta é executada localmente, garantindo que credenciais e dados financeiros nunca deixem a máquina do usuário.

**Dependências do Sistema:**

* Python 3.9+
* Node.js (Motor de renderização do Dashboard)
* FFmpeg (Obrigatório para o módulo de resolução de áudio-captcha)

**Instalação do Ambiente:**

```bash
# Clone o repositório
git clone https://github.com/edufroesbr/solar-roi.git
cd solar-roi

# Instale as dependências Python
pip install -r requirements.txt

# Instale os binários de navegação do Playwright
playwright install chromium

```

## ⚙️ Configuração Segura (Setup)

O projeto não utiliza arquivos de configuração expostos no controle de versão. Para inicializar suas credenciais e definir o valor do capital investido na usina:

```bash
python setup.py

```

*O assistente interativo guiará a criação dos arquivos `.env` e `config.json` locais. As credenciais são criptografadas em tempo de execução.*

## 📊 Fluxo de Execução

1. **Inicie a Rotina de Extração:**
```bash
python extractor.py --todos --auto

```


> **Aviso de Intervenção (reCAPTCHA):** O robô tenta a resolução automática via áudio. Caso a Neoenergia ative defesas agressivas, o script pausará e abrirá a janela do navegador para resolução manual do desafio humano, retomando a automação em seguida.


2. **Visualização de Resultados (Dashboard Premium):**
Com os dados consolidados no `dados_faturas.json`, compile e levante o servidor local para a nova interface React/Vite:
```bash
cd dashboard
npm install
npm run build
npx serve -s dist -p 3000
```

Acesse `http://localhost:3000` no seu navegador.
(Alternativamente, você pode usar `python -m http.server 3000 -d dist` dentro da pasta `dashboard`).

## 🔒 Privacidade e Compliance

* **Zero Telemetria:** O código não possui chamadas de rede externas além da comunicação direta com os servidores da Neoenergia.
* **Local-First:** Todo o processamento analítico e armazenamento de PDFs ocorre na infraestrutura do usuário.
* O `.gitignore` é rigorosamente configurado para prevenir vazamentos acidentais de credenciais (`.env`) ou dados financeiros (`*.json`, `*.pdf`).

---

*Transformando dados brutos de faturas de energia em previsibilidade financeira.*

---
