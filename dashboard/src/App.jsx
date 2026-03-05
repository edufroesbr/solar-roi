import { useState, useMemo, useEffect, useCallback } from "react";
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
    Tooltip, Legend, ResponsiveContainer, ReferenceLine, Area, AreaChart, ComposedChart
} from "recharts";

// ─── CONSTANTES ───────────────────────────────────────────────────────────────

// ─── CONSTANTES ───────────────────────────────────────────────────────────────
const COLOR_PALETTE = ["#00A36C", "#0077B6", "#F4A261", "#9B5DE5", "#E63946", "#F15BB5"];
const LS_KEY = "solar_roi_faturas_manuais";

// ─── PROJEÇÃO ─────────────────────────────────────────────────────────────────
function gerarProjecao(unidadesInfo, meses = 18, reajuste = 0.06) {
    const resultado = [];
    const mesInicio = new Date(2026, 2);
    const ucs = Object.keys(unidadesInfo);

    // Base de cálculo para projeção baseada em médias ou valores padrão se vazio
    const basePorUC = {};
    ucs.forEach(uc => {
        basePorUC[uc] = 137.5 / ucs.length; // Valor base genérico total distribuído
    });

    for (let i = 0; i < meses; i++) {
        const d = new Date(mesInicio);
        d.setMonth(d.getMonth() + i);
        const label = d.toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(". ", "/");
        const fator = Math.pow(1 + reajuste, i / 12);

        const ponto = { mes: label, total: 0, projecao: true };
        ucs.forEach((uc, idx) => {
            const val = basePorUC[uc] * fator;
            ponto[`cred_${uc}`] = val;
            ponto.total += val;
        });

        resultado.push(ponto);
    }
    return resultado;
}

// ─── CONVERSÕES ───────────────────────────────────────────────────────────────
function faturasJsonParaLista(dados) {
    const lista = [];
    if (!dados || !dados.unidades) return lista;
    Object.entries(dados.unidades).forEach(([uc, info]) => {
        (info.faturas || []).forEach(f => {
            lista.push({
                uc,
                mes: f.mes,
                kwh: f.kwh_faturado,
                pago: f.valor_pago,
                semSolar: f.valor_sem_solar,
                credito: f.credito_reais,
                vencimento: f.vencimento,
                data_pagamento: f.data_pagamento,
                dias_atraso: f.dias_atraso,
                pdf_path: f.pdf_path,
                fonte: f.fonte || "extraido",
            });
        });
    });
    return lista;
}

function consolidarMeses(faturas, ucs) {
    const mapa = {};
    faturas.forEach(f => {
        if (!mapa[f.mes]) {
            mapa[f.mes] = { mes: f.mes, total: 0 };
            ucs.forEach(uc => mapa[f.mes][`cred_${uc}`] = 0);
        }
        mapa[f.mes][`cred_${f.uc}`] = (mapa[f.mes][`cred_${f.uc}`] || 0) + (f.credito || 0);
        mapa[f.mes].total += (f.credito || 0);
    });
    return Object.values(mapa);
}

function calcularSaldoDevedor(historico, projecao, investimento) {
    let saldo = investimento;
    return [...historico, ...projecao].map(m => {
        saldo = Math.max(0, saldo - m.total);
        return { ...m, saldo: +saldo.toFixed(2), investido: +(investimento - saldo).toFixed(2) };
    });
}

// ─── FORMATAÇÃO ───────────────────────────────────────────────────────────────
const fmt = v => `R$ ${(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// ─── COMPONENTES ─────────────────────────────────────────────────────────────

function Card({ label, value, sub, color = "#00A36C" }) {
    return (
        <div style={{
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 16, padding: "20px 24px", flex: 1, minWidth: 160,
            borderTop: `3px solid ${color}`, backdropFilter: "blur(10px)"
        }}>
            <div style={{ fontSize: 11, color: "#888", textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 6 }}>{label}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#fff", lineHeight: 1.1 }}>{value}</div>
            {sub && <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>{sub}</div>}
        </div>
    );
}

const TooltipCustom = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={{ background: "#111", border: "1px solid #333", borderRadius: 10, padding: "12px 16px", fontSize: 13 }}>
            <div style={{ color: "#aaa", marginBottom: 6, fontWeight: 700 }}>{label}</div>
            {payload.map((p, i) => (
                <div key={i} style={{ color: p.color, marginBottom: 2 }}>
                    {p.name}: <b>{fmt(p.value)}</b>
                </div>
            ))}
        </div>
    );
};

// Indicador de fonte da fatura
function FonteBadge({ fonte }) {
    const isManual = fonte === "manual";
    return (
        <span style={{
            fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
            background: isManual ? "#F4A26122" : "#00A36C22",
            color: isManual ? "#F4A261" : "#00A36C",
            border: `1px solid ${isManual ? "#F4A26144" : "#00A36C44"}`,
            letterSpacing: 0.5,
        }}>
            {isManual ? "MANUAL" : "AUTO"}
        </span>
    );
}

// ─── APP PRINCIPAL ────────────────────────────────────────────────────────────
export default function App() {
    // Estado de dados
    const [dadosJson, setDadosJson] = useState(null);
    const [carregando, setCarregando] = useState(true);
    const [erroCarregamento, setErroCarregamento] = useState(null);
    const [faturasExtradas, setFaturasExtradas] = useState([]);
    const [faturasManuals, setFaturasManuals] = useState([]);

    // Parâmetros
    const [investimento, setInvestimento] = useState(22900);
    const [reajuste, setReajuste] = useState(6);
    const [proporcoes, setProporcoes] = useState({});
    const [aba, setAba] = useState("visao");
    const [novaFatura, setNovaFatura] = useState({ uc: "", mes: "", kwh: "", pago: "", semSolar: "" });

    // ── Calcula dinamicamente as informações das unidades ──────────────────────
    const unidadesInfo = useMemo(() => {
        if (!dadosJson || !dadosJson.unidades) return {};
        const info = {};
        Object.keys(dadosJson.unidades).forEach((uc, index) => {
            info[uc] = {
                nome: dadosJson.unidades[uc].responsavel || uc,
                cor: COLOR_PALETTE[index % COLOR_PALETTE.length],
                proporcao: dadosJson.unidades[uc].proporcao || 0
            };
        });
        return info;
    }, [dadosJson]);

    // ── Carregamento dinâmico do JSON ──────────────────────────────────────────
    useEffect(() => {
        fetch("dados_faturas.json")
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(dados => {
                setDadosJson(dados);
                setInvestimento(dados.investimento_total || 22900);
                setFaturasExtradas(faturasJsonParaLista(dados));

                const initialProps = {};
                Object.entries(dados.unidades || {}).forEach(([uc, info]) => {
                    initialProps[uc] = info.proporcao * 100 || 0;
                });
                setProporcoes(initialProps);
                if (Object.keys(dados.unidades || {}).length > 0) {
                    setNovaFatura(prev => ({ ...prev, uc: Object.keys(dados.unidades)[0] }));
                }

                setCarregando(false);
            })
            .catch(err => {
                setErroCarregamento(err.message);
                setCarregando(false);
            });
    }, []);

    // ── Restaura faturas manuais do localStorage ──────────────────────────────
    useEffect(() => {
        try {
            const salvas = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
            setFaturasManuals(salvas);
        } catch {
            setFaturasManuals([]);
        }
    }, []);

    // ── Faturas consolidadas (extraídas + manuais) ────────────────────────────
    const faturas = useMemo(() => [...faturasExtradas, ...faturasManuals], [faturasExtradas, faturasManuals]);
    const ucs = useMemo(() => Object.keys(unidadesInfo), [unidadesInfo]);

    const historico = useMemo(() => consolidarMeses(faturas, ucs), [faturas, ucs]);
    const projecao = useMemo(() => gerarProjecao(unidadesInfo, 18, reajuste / 100), [unidadesInfo, reajuste]);
    const serieSaldo = useMemo(() => calcularSaldoDevedor(historico, projecao, investimento), [historico, projecao, investimento]);

    const totalEconomizado = historico.reduce((a, m) => a + m.total, 0);
    const saldoAtual = investimento - totalEconomizado;
    const idxBreakeven = serieSaldo.findIndex(m => m.saldo === 0);
    const mesBreakeven = idxBreakeven >= 0 ? serieSaldo[idxBreakeven].mes : "Em cálculo...";
    const mediaEconomia = historico.length > 0 ? totalEconomizado / historico.length : 0;
    const mesesRestantes = mediaEconomia > 0 ? Math.ceil(saldoAtual / mediaEconomia) : "—";

    const tabelaDetalhada = useMemo(() => {
        const meses = [...new Set(faturas.map(f => f.mes))].sort((a, b) => {
            const [mA, aA] = a.split('/');
            const [mB, aB] = b.split('/');
            return new Date(aB, mB - 1) - new Date(aA, mA - 1);
        });
        return meses.map(mes => {
            const row = { mes };
            ucs.forEach(uc => {
                const f = faturas.find(x => x.uc === uc && x.mes === mes);
                row[uc] = f ? { pago: f.pago, credito: f.credito, kwh: f.kwh, fonte: f.fonte } : null;
            });
            row.totalCredito = ucs.reduce((a, uc) => a + (row[uc]?.credito || 0), 0);
            return row;
        });
    }, [faturas, ucs]);

    // ── Adicionar fatura manual ───────────────────────────────────────────────
    const adicionarFatura = useCallback(() => {
        if (!novaFatura.mes || !novaFatura.kwh || !novaFatura.pago) return;
        const credito = parseFloat(novaFatura.semSolar) - parseFloat(novaFatura.pago);
        const nova = {
            uc: novaFatura.uc,
            mes: novaFatura.mes,
            kwh: parseFloat(novaFatura.kwh),
            pago: parseFloat(novaFatura.pago),
            semSolar: parseFloat(novaFatura.semSolar),
            credito: parseFloat(credito.toFixed(2)),
            fonte: "manual",
        };
        const atualizadas = [...faturasManuals, nova];
        setFaturasManuals(atualizadas);
        try {
            localStorage.setItem(LS_KEY, JSON.stringify(atualizadas));
        } catch {/* quota atingida */ }
        setNovaFatura({ uc: ucs[0] || "", mes: "", kwh: "", pago: "", semSolar: "" });
    }, [novaFatura, faturasManuals, ucs]);

    // ── Exportações ───────────────────────────────────────────────────────────
    const exportarCSV = useCallback(() => {
        const linhas = [["Mês", "UC", "Responsável", "kWh", "Pago (R$)", "Sem Solar (R$)", "Crédito (R$)", "Fonte"]];
        faturas.forEach(f => {
            linhas.push([
                f.mes, f.uc, unidadesInfo[f.uc]?.nome || f.uc,
                f.kwh, f.pago, f.semSolar, f.credito, f.fonte,
            ]);
        });
        const csv = "\uFEFF" + linhas.map(l => l.join(";")).join("\n");
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "roi_solar_neoenergia.csv"; a.click();
        URL.revokeObjectURL(url);
    }, [faturas, unidadesInfo]);

    const exportarJSON = useCallback(() => {
        if (!dadosJson) return;
        const blob = new Blob([JSON.stringify(dadosJson, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "dados_faturas.json"; a.click();
        URL.revokeObjectURL(url);
    }, [dadosJson]);

    const imprimirRelatorio = useCallback(() => {
        window.print();
    }, []);

    // ── Loading & Erro ────────────────────────────────────────────────────────
    if (carregando) {
        return (
            <div style={{ background: "#0a0a0a", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: "#00A36C", fontFamily: "monospace", fontSize: 18 }}>
                <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 48, marginBottom: 16 }}>☀️</div>
                    <div>Carregando dados do sistema solar...</div>
                </div>
            </div>
        );
    }

    if (erroCarregamento) {
        return (
            <div style={{ background: "#0a0a0a", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: "#E63946", fontFamily: "monospace", fontSize: 14, padding: 40 }}>
                <div style={{ textAlign: "center", maxWidth: 500 }}>
                    <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
                    <div style={{ color: "#E63946", fontSize: 18, marginBottom: 12 }}>Erro ao carregar dados</div>
                    <div style={{ color: "#666", marginBottom: 24 }}>{erroCarregamento}</div>
                    <div style={{ color: "#555", fontSize: 12 }}>
                        Verifique se o arquivo <code style={{ color: "#00A36C" }}>dados_faturas.json</code> está no mesmo diretório que o dashboard.
                        <br /><br />
                        Execute o extrator para gerar o arquivo: <br />
                        <code style={{ color: "#0077B6" }}>python extractor.py --todos</code>
                    </div>
                </div>
            </div>
        );
    }

    const abas = [
        { id: "visao", label: "📊 Visão Geral" },
        { id: "evolucao", label: "📈 Evolução" },
        { id: "tabela", label: "🧾 Faturas" },
        { id: "config", label: "⚙️ Configurar" },
    ];

    return (
        <div style={{
            fontFamily: "'DM Mono', 'Courier New', monospace",
            background: "#0a0a0a", minHeight: "100vh", color: "#e0e0e0",
            padding: "0 0 60px"
        }}>

            {/* ── HEADER ─────────────────────────────────────────────────────────── */}
            <div style={{
                background: "linear-gradient(135deg, #001a0e 0%, #003320 50%, #001a0e 100%)",
                borderBottom: "1px solid #00A36C33",
                padding: "28px 40px 24px", position: "relative", overflow: "hidden"
            }}>
                <div style={{
                    position: "absolute", top: 0, left: 0, right: 0, bottom: 0, opacity: 0.04,
                    backgroundImage: "repeating-linear-gradient(0deg, #00A36C 0, #00A36C 1px, transparent 1px, transparent 40px), repeating-linear-gradient(90deg, #00A36C 0, #00A36C 1px, transparent 1px, transparent 40px)"
                }} />
                <div style={{ position: "relative" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 4 }}>
                        <div style={{ fontSize: 28 }}>☀️</div>
                        <div>
                            <div style={{ fontSize: 22, fontWeight: 900, color: "#fff", letterSpacing: -0.5 }}>
                                ROI Solar — Neoenergia Brasília
                            </div>
                            <div style={{ fontSize: 12, color: "#00A36C", letterSpacing: 2 }}>
                                USINA FOTOVOLTAICA · RETORNO DE INVESTIMENTO · 3 UNIDADES
                            </div>
                        </div>
                    </div>
                    <div style={{ display: "flex", gap: 20, marginTop: 8 }}>
                        <span style={{ fontSize: 11, color: "#555" }}>{ucs.join(' · ')}</span>
                        <span style={{ fontSize: 11, color: "#555" }}>•</span>
                        <span style={{ fontSize: 11, color: "#555" }}>Relatório Gerencial Usina Solar</span>
                        {erroCarregamento === null && (
                            <span style={{ fontSize: 11, color: "#00A36C55" }}>• dados_faturas.json ✓</span>
                        )}
                    </div>
                </div>
            </div>

            {/* ── ABAS ───────────────────────────────────────────────────────────── */}
            <div style={{ display: "flex", gap: 2, padding: "0 40px", background: "#0f0f0f", borderBottom: "1px solid #1a1a1a", flexWrap: "wrap" }}>
                {abas.map(a => (
                    <button key={a.id} onClick={() => setAba(a.id)} style={{
                        background: aba === a.id ? "#00A36C" : "transparent",
                        color: aba === a.id ? "#000" : "#666",
                        border: "none", borderRadius: "0 0 8px 8px", padding: "10px 20px",
                        fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
                        letterSpacing: 0.5, transition: "all 0.2s"
                    }}>{a.label}</button>
                ))}
                {/* Botões de exportação */}
                <div style={{ display: "flex", gap: 8, marginLeft: "auto", alignItems: "center", padding: "6px 0" }}>
                    <button onClick={exportarCSV} style={{ background: "transparent", color: "#00A36C", border: "1px solid #00A36C44", borderRadius: 8, padding: "7px 14px", fontFamily: "inherit", fontSize: 11, cursor: "pointer" }}>⬇ CSV</button>
                    <button onClick={exportarJSON} style={{ background: "transparent", color: "#0077B6", border: "1px solid #0077B644", borderRadius: 8, padding: "7px 14px", fontFamily: "inherit", fontSize: 11, cursor: "pointer" }}>⬇ JSON</button>
                    <button onClick={imprimirRelatorio} style={{ background: "transparent", color: "#888", border: "1px solid #33333344", borderRadius: 8, padding: "7px 14px", fontFamily: "inherit", fontSize: 11, cursor: "pointer" }}>🖨 Imprimir</button>
                </div>
            </div>

            <div style={{ padding: "32px 40px" }}>

                {/* ── ABA: VISÃO GERAL ─────────────────────────────────────────────── */}
                {aba === "visao" && (
                    <>
                        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 32 }}>
                            <Card label="Investimento Total" value={fmt(investimento)} color="#00A36C" />
                            <Card label="Total Economizado" value={fmt(totalEconomizado)} sub={`${historico.length} meses registrados`} color="#0077B6" />
                            <Card label="Saldo Devedor" value={fmt(Math.max(0, saldoAtual))} sub={`${((totalEconomizado / investimento) * 100).toFixed(1)}% recuperado`} color="#F4A261" />
                            <Card label="Breakeven Estimado" value={mesBreakeven} sub={`~${mesesRestantes} meses restantes`} color="#E63946" />
                            <Card label="Economia Média/Mês" value={fmt(mediaEconomia)} sub="todas as unidades" color="#9B5DE5" />
                        </div>

                        {/* BARRA DE PROGRESSO */}
                        <div style={{ background: "#111", border: "1px solid #1e1e1e", borderRadius: 16, padding: "24px 28px", marginBottom: 28 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                                <span style={{ fontSize: 12, color: "#888", letterSpacing: 1 }}>PROGRESSO DO RETORNO</span>
                                <span style={{ fontSize: 13, color: "#00A36C", fontWeight: 700 }}>
                                    {((totalEconomizado / investimento) * 100).toFixed(2)}%
                                </span>
                            </div>
                            <div style={{ background: "#1a1a1a", borderRadius: 8, height: 12, overflow: "hidden" }}>
                                <div style={{
                                    width: `${Math.min(100, (totalEconomizado / investimento) * 100)}%`,
                                    background: "linear-gradient(90deg, #00A36C, #00D68F)",
                                    height: "100%", borderRadius: 8, transition: "width 1s ease"
                                }} />
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 11, color: "#555" }}>
                                <span>R$ 0</span><span>Meta: {fmt(investimento)}</span>
                            </div>
                        </div>

                        {/* CONTRIBUIÇÃO POR UNIDADE */}
                        <div style={{ background: "#111", border: "1px solid #1e1e1e", borderRadius: 16, padding: "24px 28px" }}>
                            <div style={{ fontSize: 12, color: "#888", letterSpacing: 1, marginBottom: 20 }}>CONTRIBUIÇÃO POR UNIDADE CONSUMIDORA</div>
                            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                                {Object.entries(unidadesInfo).map(([uc, info]) => {
                                    const total = faturas.filter(f => f.uc === uc).reduce((a, f) => a + (f.credito || 0), 0);
                                    return (
                                        <div key={uc} style={{ flex: 1, minWidth: 200, background: "#0a0a0a", borderRadius: 12, padding: "16px 20px", borderLeft: `3px solid ${info.cor}` }}>
                                            <div style={{ fontSize: 10, color: "#555", marginBottom: 4 }}>{uc}</div>
                                            <div style={{ fontWeight: 700, color: "#ccc", marginBottom: 8 }}>{info.nome}</div>
                                            <div style={{ fontSize: 22, fontWeight: 900, color: info.cor }}>{fmt(total)}</div>
                                            <div style={{ fontSize: 11, color: "#555", marginTop: 4 }}>
                                                {((total / (totalEconomizado || 1)) * 100).toFixed(1)}% do total economizado
                                            </div>
                                            <div style={{ background: "#1a1a1a", borderRadius: 4, height: 4, marginTop: 10 }}>
                                                <div style={{ width: `${info.proporcao * 100}%`, background: info.cor, height: 4, borderRadius: 4 }} />
                                            </div>
                                            <div style={{ fontSize: 10, color: "#444", marginTop: 4 }}>Proporção: {(info.proporcao * 100).toFixed(0)}%</div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </>
                )}

                {/* ── ABA: EVOLUÇÃO ────────────────────────────────────────────────── */}
                {aba === "evolucao" && (
                    <>
                        <div style={{ background: "#111", border: "1px solid #1e1e1e", borderRadius: 16, padding: "24px 28px", marginBottom: 28 }}>
                            <div style={{ fontSize: 12, color: "#888", letterSpacing: 1, marginBottom: 4 }}>EVOLUÇÃO DO SALDO DEVEDOR</div>
                            <div style={{ fontSize: 11, color: "#444", marginBottom: 20 }}>Histórico real + projeção futura</div>
                            <ResponsiveContainer width="100%" height={320}>
                                <ComposedChart data={serieSaldo} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
                                    <CartesianGrid stroke="#1a1a1a" strokeDasharray="3 3" />
                                    <XAxis dataKey="mes" tick={{ fill: "#555", fontSize: 11 }} />
                                    <YAxis tickFormatter={v => `R$${(v / 1000).toFixed(0)}k`} tick={{ fill: "#555", fontSize: 11 }} />
                                    <Tooltip content={<TooltipCustom />} />
                                    <Legend wrapperStyle={{ color: "#666", fontSize: 12 }} />
                                    <ReferenceLine y={0} stroke="#00A36C" strokeDasharray="4 4" label={{ value: "BREAKEVEN", fill: "#00A36C", fontSize: 10 }} />
                                    <Area type="monotone" dataKey="investido" name="Valor Recuperado" fill="#00A36C22" stroke="#00A36C" strokeWidth={2} />
                                    <Line type="monotone" dataKey="saldo" name="Saldo Devedor" stroke="#F4A261" strokeWidth={2.5} dot={false} />
                                </ComposedChart>
                            </ResponsiveContainer>
                        </div>
                        <div style={{ background: "#111", border: "1px solid #1e1e1e", borderRadius: 16, padding: "24px 28px" }}>
                            <div style={{ fontSize: 12, color: "#888", letterSpacing: 1, marginBottom: 20 }}>CRÉDITO MENSAL POR UNIDADE (R$)</div>
                            <ResponsiveContainer width="100%" height={280}>
                                <BarChart data={[...historico, ...projecao.slice(0, 10)]} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
                                    <CartesianGrid stroke="#1a1a1a" strokeDasharray="3 3" />
                                    <XAxis dataKey="mes" tick={{ fill: "#555", fontSize: 11 }} />
                                    <YAxis tickFormatter={v => `R$${v}`} tick={{ fill: "#555", fontSize: 11 }} />
                                    <Tooltip content={<TooltipCustom />} />
                                    <Legend wrapperStyle={{ color: "#666", fontSize: 12 }} />
                                    {ucs.map((uc, i) => (
                                        <Bar key={uc} dataKey={`cred_${uc}`} name={unidadesInfo[uc]?.nome || uc} stackId="a" fill={unidadesInfo[uc]?.cor || COLOR_PALETTE[i % COLOR_PALETTE.length]} radius={i === ucs.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
                                    ))}
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </>
                )}

                {/* ── ABA: FATURAS ─────────────────────────────────────────────────── */}
                {aba === "tabela" && (
                    <>
                        <div style={{ background: "#111", border: "1px solid #1e1e1e", borderRadius: 16, padding: "24px 28px", marginBottom: 24 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                                <div style={{ fontSize: 12, color: "#888", letterSpacing: 1 }}>EXTRATO MENSAL — TODAS AS UNIDADES</div>
                                <div style={{ display: "flex", gap: 12, fontSize: 11, color: "#555" }}>
                                    <span><span style={{ color: "#00A36C" }}>●</span> Auto</span>
                                    <span><span style={{ color: "#F4A261" }}>●</span> Manual</span>
                                </div>
                            </div>
                            <div style={{ overflowX: "auto" }}>
                                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                                    <thead>
                                        <tr style={{ borderBottom: "1px solid #2a2a2a" }}>
                                            <th style={{ padding: "10px 12px", textAlign: "left", color: "#555", fontWeight: 600 }}>Mês</th>
                                            {ucs.map((uc) => (
                                                <th key={uc} colSpan={3} style={{ padding: "10px 12px", textAlign: "center", color: unidadesInfo[uc]?.cor, fontWeight: 700, borderBottom: `2px solid ${unidadesInfo[uc]?.cor}44` }}>
                                                    {unidadesInfo[uc]?.nome}
                                                </th>
                                            ))}
                                            <th style={{ padding: "10px 12px", textAlign: "right", color: "#888" }}>Crédito Total</th>
                                            <th style={{ padding: "10px 12px", textAlign: "right", color: "#888" }}>Saldo Dev.</th>
                                        </tr>
                                        <tr style={{ borderBottom: "1px solid #1a1a1a" }}>
                                            <th style={{ padding: "10px 12px", border: 'none' }}></th>
                                            {ucs.map(uc => (
                                                <React.Fragment key={uc}>
                                                    <th style={{ padding: "6px 8px", textAlign: "center", color: "#444", fontSize: 10 }}>Pago</th>
                                                    <th style={{ padding: "6px 8px", textAlign: "center", color: "#444", fontSize: 10 }}>Crédito</th>
                                                    <th style={{ padding: "6px 8px", textAlign: "center", color: "#444", fontSize: 10 }}>kWh</th>
                                                </React.Fragment>
                                            ))}
                                            <th style={{ padding: "6px 12px", border: 'none' }}></th><th style={{ padding: "6px 12px", border: 'none' }}></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(() => {
                                            let saldoAcc = investimento;
                                            return tabelaDetalhada.map((row, i) => {
                                                saldoAcc -= row.totalCredito;
                                                return (
                                                    <tr key={i} style={{ borderBottom: "1px solid #161616", background: i % 2 === 0 ? "transparent" : "#0d0d0d" }}>
                                                        <td style={{ padding: "10px 12px", color: "#aaa", fontWeight: 700 }}>{row.mes}</td>
                                                        {ucs.map(uc => (
                                                            <React.Fragment key={uc}>
                                                                <td style={{ padding: "10px 8px", textAlign: "center", color: "#777" }}>
                                                                    {row[uc] ? fmt(row[uc].pago) : "—"}
                                                                </td>
                                                                <td style={{ padding: "10px 8px", textAlign: "center", color: "#00A36C", fontWeight: 700 }}>
                                                                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                                                                        {row[uc] ? fmt(row[uc].credito) : "—"}
                                                                        {row[uc] && <FonteBadge fonte={row[uc].fonte} />}
                                                                    </div>
                                                                </td>
                                                                <td style={{ padding: "10px 8px", textAlign: "center", color: "#555" }}>
                                                                    {row[uc] ? `${row[uc].kwh} kWh` : "—"}
                                                                </td>
                                                            </React.Fragment>
                                                        ))}
                                                        <td style={{ padding: "10px 12px", textAlign: "right", color: "#00D68F", fontWeight: 900 }}>
                                                            {fmt(row.totalCredito)}
                                                        </td>
                                                        <td style={{ padding: "10px 12px", textAlign: "right", color: saldoAcc <= 0 ? "#00A36C" : "#F4A261", fontWeight: 700 }}>
                                                            {fmt(Math.max(0, saldoAcc))}
                                                        </td>
                                                    </tr>
                                                );
                                            });
                                        })()}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        {/* ADICIONAR FATURA MANUALMENTE */}
                        <div style={{ background: "#111", border: "1px solid #00A36C33", borderRadius: 16, padding: "24px 28px" }}>
                            <div style={{ fontSize: 12, color: "#00A36C", letterSpacing: 1, marginBottom: 16 }}>+ REGISTRAR NOVA FATURA MANUALMENTE</div>
                            <div style={{ fontSize: 11, color: "#555", marginBottom: 16 }}>
                                Faturas manuais são salvas no navegador (localStorage) como backup até o próximo ciclo de extração.
                            </div>
                            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
                                {[
                                    { label: "Unidade", key: "uc", type: "select", opts: Object.entries(unidadesInfo).map(([k, v]) => ({ value: k, label: v.nome })) },
                                    { label: "Mês (ex: Mar/2026)", key: "mes", type: "text" },
                                    { label: "kWh Faturado", key: "kwh", type: "number" },
                                    { label: "Valor Pago (R$)", key: "pago", type: "number" },
                                    { label: "Valor Sem Solar (R$)", key: "semSolar", type: "number" },
                                ].map(f => (
                                    <div key={f.key} style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 140 }}>
                                        <label style={{ fontSize: 10, color: "#555", letterSpacing: 1 }}>{f.label}</label>
                                        {f.type === "select" ? (
                                            <select value={novaFatura[f.key]} onChange={e => setNovaFatura(p => ({ ...p, [f.key]: e.target.value }))}
                                                style={{ background: "#0a0a0a", border: "1px solid #2a2a2a", color: "#ccc", borderRadius: 8, padding: "8px 10px", fontFamily: "inherit", fontSize: 12 }}>
                                                {f.opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                            </select>
                                        ) : (
                                            <input type={f.type} value={novaFatura[f.key]} placeholder={f.label}
                                                onChange={e => setNovaFatura(p => ({ ...p, [f.key]: e.target.value }))}
                                                style={{ background: "#0a0a0a", border: "1px solid #2a2a2a", color: "#ccc", borderRadius: 8, padding: "8px 10px", fontFamily: "inherit", fontSize: 12 }} />
                                        )}
                                    </div>
                                ))}
                                <button onClick={adicionarFatura} style={{
                                    background: "#00A36C", color: "#000", border: "none", borderRadius: 8,
                                    padding: "9px 20px", fontFamily: "inherit", fontWeight: 900, fontSize: 12, cursor: "pointer"
                                }}>ADICIONAR</button>
                            </div>
                            {faturasManuals.length > 0 && (
                                <div style={{ marginTop: 16, fontSize: 11, color: "#F4A261" }}>
                                    ⚠️ {faturasManuals.length} fatura(s) manual(is) pendente(s) no localStorage.
                                    <button onClick={() => { setFaturasManuals([]); localStorage.removeItem(LS_KEY); }} style={{
                                        marginLeft: 12, background: "transparent", color: "#E63946", border: "1px solid #E6394644", borderRadius: 6, padding: "3px 10px", fontFamily: "inherit", fontSize: 10, cursor: "pointer"
                                    }}>Limpar manuais</button>
                                </div>
                            )}
                        </div>
                    </>
                )}

                {/* ── ABA: CONFIGURAR ──────────────────────────────────────────────── */}
                {aba === "config" && (
                    <div style={{ background: "#111", border: "1px solid #1e1e1e", borderRadius: 16, padding: "32px 36px", maxWidth: 640 }}>
                        <div style={{ fontSize: 12, color: "#888", letterSpacing: 1, marginBottom: 28 }}>PARÂMETROS DO INVESTIMENTO</div>
                        {[
                            { label: "Investimento Total (R$)", val: investimento, set: setInvestimento, min: 1000, max: 200000, step: 100 },
                            { label: "Reajuste Tarifário Anual (%)", val: reajuste, set: setReajuste, min: 0, max: 20, step: 0.5 },
                        ].map(({ label, val, set, min, max, step }) => (
                            <div key={label} style={{ marginBottom: 28 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                                    <span style={{ fontSize: 12, color: "#777" }}>{label}</span>
                                    <span style={{ fontSize: 14, fontWeight: 900, color: "#00A36C" }}>{label.includes("R$") ? fmt(val) : `${val}%`}</span>
                                </div>
                                <input type="range" min={min} max={max} step={step} value={val} onChange={e => set(+e.target.value)}
                                    style={{ width: "100%", accentColor: "#00A36C" }} />
                            </div>
                        ))}
                        <div style={{ marginTop: 8, paddingTop: 24, borderTop: "1px solid #1a1a1a" }}>
                            <div style={{ fontSize: 12, color: "#888", letterSpacing: 1, marginBottom: 20 }}>PROPORÇÃO POR UNIDADE</div>
                            {ucs.map((uc) => (
                                <div key={uc} style={{ marginBottom: 20 }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                                        <span style={{ fontSize: 11, color: "#666" }}>{unidadesInfo[uc]?.nome} ({uc})</span>
                                        <span style={{ fontSize: 14, fontWeight: 900, color: unidadesInfo[uc]?.cor }}>{proporcoes[uc]?.toFixed(0)}%</span>
                                    </div>
                                    <input type="range" min={0} max={100} step={1} value={proporcoes[uc] || 0} onChange={e => setProporcoes(p => ({ ...p, [uc]: +e.target.value }))}
                                        style={{ width: "100%", accentColor: unidadesInfo[uc]?.cor }} />
                                </div>
                            ))}
                            <div style={{ fontSize: 11, color: ucs.reduce((a, uc) => a + (proporcoes[uc] || 0), 0) !== 100 ? "#E63946" : "#00A36C", marginTop: 8 }}>
                                {ucs.reduce((a, uc) => a + (proporcoes[uc] || 0), 0) !== 100
                                    ? `⚠️ Total = ${ucs.reduce((a, uc) => a + (proporcoes[uc] || 0), 0)}% (deve ser 100%)`
                                    : `✓ Total = 100%`}
                            </div>
                        </div>

                        {/* CENÁRIOS */}
                        <div style={{ marginTop: 32, background: "#0a0a0a", borderRadius: 12, padding: "20px 24px", border: "1px solid #1a1a1a" }}>
                            <div style={{ fontSize: 11, color: "#555", marginBottom: 12, letterSpacing: 1 }}>CENÁRIOS DE BREAKEVEN</div>
                            {[
                                { cenario: "Pessimista (-15%)", mult: 0.85, cor: "#E63946" },
                                { cenario: "Realista", mult: 1.0, cor: "#F4A261" },
                                { cenario: "Otimista (+15%)", mult: 1.15, cor: "#00A36C" },
                            ].map(({ cenario, mult, cor }) => {
                                const meses = mediaEconomia > 0 ? Math.ceil(saldoAtual / (mediaEconomia * mult)) : "—";
                                return (
                                    <div key={cenario} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #141414" }}>
                                        <span style={{ fontSize: 12, color: "#666" }}>{cenario}</span>
                                        <span style={{ fontSize: 13, fontWeight: 700, color: cor }}>{typeof meses === "number" ? `~${meses} meses` : "—"}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>

            {/* ── ESTILOS PARA IMPRESSÃO ────────────────────────────────────────── */}
            <style>{`
        @media print {
          body { background: white !important; color: black !important; }
          button { display: none !important; }
          div[style*="background: #0a0a0a"] { background: white !important; }
          div[style*="background: #111"] { background: #f5f5f5 !important; border-color: #ddd !important; }
          input[type="range"] { display: none; }
          * { color: black !important; }
          td, th { border: 1px solid #ddd !important; }
        }
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap');
      `}</style>
        </div>
    );
}
