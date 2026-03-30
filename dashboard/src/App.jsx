import React, { useState, useMemo, useEffect, useCallback } from "react";
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
    Tooltip as RechartsTooltip, Legend, ResponsiveContainer, ReferenceLine, Area, AreaChart, ComposedChart, Cell
} from "recharts";

// ─── STITCH DESIGN TOKENS (PREMIUM MODO CLARO) ──────────────────────────────
const COLORS = {
    green: "#4db886",
    blue: "#5da0d6",
    gold: "#b38b4d",
    gray: "#6b7280",
    white: "#ffffff",
    surface: "#f8fafc",
    textSlate: "#334155",
    textDark: "#1e293b",
};

const COLOR_PALETTE = ["#4db886", "#5da0d6", "#b38b4d", "#9334E6", "#12B5CB", "#E8710A"];

// ─── FORMATAÇÃO ───────────────────────────────────────────────────────────────
const fmt = v => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v || 0);
const fmtKwh = v => `${(v || 0).toLocaleString('pt-BR')} kWh`;
const fmtPercentShort = v => new Intl.NumberFormat('pt-BR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(v || 0);
const fmtPercentLong = v => new Intl.NumberFormat('pt-BR', { style: 'percent', minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(v || 0);

// ─── EXPORTAÇÃO CSV ───────────────────────────────────────────────────────────
const exportToCSV = (data, filename) => {
    if (!data.length) return;
    const headers = Object.keys(data[0]);
    const csvContent = [
        headers.join(","),
        ...data.map(row => headers.map(h => `"${(row[h] || "").toString().replace(/"/g, '""')}"`).join(","))
    ].join("\n");

    const blob = new Blob(["\ufeff" + csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
};

// ─── COMPONENTES ─────────────────────────────────────────────────────────────

function KPICard({ label, value, sub, bgColor, borderColor, textColor, trendIcon }) {
    return (
        <div className={`rounded-3xl p-6 flex flex-col justify-between shadow-[0_4px_20px_rgba(0,0,0,0.04)] border-2 ${bgColor} ${borderColor}`}>
            <h3 className="text-[11px] font-bold text-slate-500 mb-2 uppercase tracking-[1px]">{label}</h3>
            <div>
                <div className={`text-3xl font-bold ${textColor} mb-1 tracking-tight text-slate-800`}>{value}</div>
                <div className={`text-[13px] font-medium ${textColor} flex items-center gap-1 opacity-90`}>
                    {trendIcon}
                    {sub}
                </div>
            </div>
        </div>
    );
}

const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="bg-white/95 backdrop-blur-md border border-slate-200 rounded-2xl p-4 shadow-xl text-sm">
            <div className="font-bold text-slate-800 mb-2 border-b pb-1 border-slate-100">{label}</div>
            {payload.map((p, i) => (
                <div key={i} className="flex justify-between gap-6 mb-1.5">
                    <span className="text-slate-500 flex items-center gap-2 font-medium">
                        <span className="w-2 h-2 rounded-full" style={{ background: p.color }}></span>
                        {p.name}:
                    </span>
                    <span className="font-bold" style={{ color: p.color }}>{fmt(p.value)}</span>
                </div>
            ))}
        </div>
    );
};

// ─── APP PRINCIPAL ────────────────────────────────────────────────────────────
export default function App() {
    const [dadosJson, setDadosJson] = useState(null);
    const [carregando, setCarregando] = useState(true);
    const [faturasExtradas, setFaturasExtradas] = useState([]);
    const [investimento, setInvestimento] = useState(22900);
    const [expandidoId, setExpandidoId] = useState(null);

    // Carregamento de dados
    useEffect(() => {
        fetch("dados_faturas.json")
            .then(res => res.json())
            .then(dados => {
                setDadosJson(dados);
                setInvestimento(dados.investimento_total || 22900);
                const lista = [];
                const todosMeses = new Set();
                
                Object.values(dados.unidades || {}).forEach(info => {
                    (info.faturas || []).forEach(f => todosMeses.add(f.mes));
                });

                Object.entries(dados.unidades || {}).forEach(([uc, info]) => {
                    const faturasDaUc = info.faturas || [];
                    const mesesDaUc = faturasDaUc.map(f => f.mes);
                    
                    faturasDaUc.forEach(f => {
                        lista.push({
                            uc,
                            mes: f.mes,
                            referencia: f.referencia,
                            kwh: f.kwh_faturado || 0,
                            pago: f.valor_pago || 0,
                            semSolar: f.valor_sem_solar || 0,
                            credito: f.credito_reais > 0 ? f.credito_reais : (f.valor_sem_solar > f.valor_pago ? f.valor_sem_solar - f.valor_pago : 0),
                            responsavel: info.responsavel || uc
                        });
                    });

                    todosMeses.forEach(mes => {
                        if (!mesesDaUc.includes(mes)) {
                            lista.push({
                                uc,
                                mes: mes,
                                referencia: mes.split('/').reverse().join('-'),
                                kwh: 0,
                                pago: 0,
                                semSolar: 0,
                                credito: 0,
                                responsavel: info.responsavel || uc,
                                missing: true
                            });
                        }
                    });
                });
                setFaturasExtradas(lista);
                setCarregando(false);
            })
            .catch(err => {
                console.error(err);
                setCarregando(false);
            });
    }, []);

    const ucs = useMemo(() => dadosJson ? Object.keys(dadosJson.unidades) : [], [dadosJson]);
    const unidadesInfo = useMemo(() => {
        const info = {};
        ucs.forEach((uc, i) => {
            const label = dadosJson.unidades[uc].apelido || dadosJson.unidades[uc].responsavel;
            info[uc] = {
                nome: label ? `${uc} - ${label}` : uc,
                cor: COLOR_PALETTE[i % COLOR_PALETTE.length]
            };
        });
        return info;
    }, [ucs, dadosJson]);

    const totalEconomizado = useMemo(() => faturasExtradas.reduce((a, f) => a + (f.credito || 0), 0), [faturasExtradas]);
    const mesesAtivos = useMemo(() => [...new Set(faturasExtradas.filter(f => (f.credito || 0) > 0).map(f => f.mes))].length, [faturasExtradas]);
    const numMesesTotal = useMemo(() => [...new Set(faturasExtradas.map(f => f.mes))].length, [faturasExtradas]);
    const mediaMensal = useMemo(() => mesesAtivos > 0 ? totalEconomizado / mesesAtivos : 0, [totalEconomizado, mesesAtivos]);
    
    const mesesRestantes = useMemo(() => {
        const saldo = investimento - totalEconomizado;
        return mediaMensal > 0 ? Math.ceil(saldo / mediaMensal) : 0;
    }, [investimento, totalEconomizado, mediaMensal]);

    const playbackDate = useMemo(() => {
        if (mesesRestantes <= 0) return "Conciliado";
        const d = new Date();
        d.setMonth(d.getMonth() + mesesRestantes);
        return d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
    }, [mesesRestantes]);

    // Histórico mensal acumulado para o gráfico
    const historicoMensal = useMemo(() => {
        const meses = [...new Set(faturasExtradas.map(f => f.mes))].sort((a, b) => {
            const [mA, yA] = a.split('/').map(Number);
            const [mB, yB] = b.split('/').map(Number);
            return (yA * 100 + mA) - (yB * 100 + mB);
        });

        let acumulado = 0;
        return meses.map(mes => {
            const faturasMes = faturasExtradas.filter(f => f.mes === mes);
            const ganhoMes = faturasMes.reduce((a, f) => a + (f.credito || 0), 0);
            acumulado += ganhoMes;
            return { 
                mes, 
                ganho: ganhoMes, 
                acumulado: acumulado, 
                restante: Math.max(0, investimento - acumulado) 
            };
        });
    }, [faturasExtradas, investimento]);

    const handleExportFull = () => {
        const data = faturasExtradas.map(f => ({
            Unidade: unidadesInfo[f.uc].nome,
            Mes: f.mes,
            Consumo: f.kwh,
            Pago: f.pago,
            Recuperado: f.credito,
            '% Investimento': fmtPercentLong(f.credito / investimento)
        }));
        exportToCSV(data, "SolarROI_Historico_Completo.csv");
    };

    if (carregando) return <div className="flex h-screen items-center justify-center text-slate-300 font-bold text-xl uppercase tracking-widest animate-pulse font-sans">☀️ Sincronizando Stitch Database...</div>;

    return (
        <div className="p-10 antialiased bg-[#f8fafc] min-h-screen text-slate-700 font-sans print:bg-white print:p-0">
            
            {/* ── HEADER Premium ─────────────────────────────────────────────── */}
            <header className="flex justify-between items-center mb-6 bg-white/70 p-5 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] backdrop-blur-xl border border-white/60 sticky top-0 z-50">
                <div className="flex items-center gap-5">
                    <div className="w-12 h-12 bg-slate-800 rounded-2xl flex items-center justify-center text-white shadow-lg overflow-hidden">
                        <svg className="w-7 h-7" fill="currentColor" viewBox="0 0 24 24"><path d="M12 3a2.5 2.5 0 0 1 2.5 2.5c0 .28-.05.55-.14.8l2.9 1.45A1.99 1.99 0 0 1 19 9.5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V9.5c0-.85.53-1.58 1.28-1.87l2.86-1.43c-.09-.25-.14-.52-.14-.8A2.5 2.5 0 0 1 12 3zm0 2a.5.5 0 0 0-.5.5c0 .28.22.5.5.5s.5-.22.5-.5a.5.5 0 0 0-.5-.5zm5 5.5h-10v8h10v-8zm-6 2v4H9v-4h2zm4 0v4h-2v-4h2z"></path></svg>
                    </div>
                    <div>
                        <h1 className="text-2xl font-serif-title text-slate-800 tracking-tight leading-none mb-1">
                            ROI SOLAR <span className="text-[#b38b4d] italic">PREMIUM</span>
                        </h1>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest leading-none">Intelligence Engine • Modo Claro</p>
                    </div>
                </div>
                <div className="flex items-center gap-4 no-print">
                    <div className="flex bg-slate-100 p-1 rounded-full border border-slate-200 shadow-inner">
                        <button onClick={handleExportFull} className="px-5 py-2 text-[10px] font-black text-slate-600 hover:bg-white hover:shadow-sm rounded-full transition-all uppercase tracking-widest">CSV</button>
                        <button onClick={() => window.print()} className="px-5 py-2 text-[10px] font-black text-slate-600 hover:bg-white hover:shadow-sm rounded-full transition-all uppercase tracking-widest">PDF</button>
                    </div>
                    <div className="h-12 w-12 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-600 shadow-sm overflow-hidden p-0.5">
                         <div className="w-full h-full rounded-full bg-slate-50 flex items-center justify-center font-bold text-xs">EF</div>
                    </div>
                </div>
            </header>

            {/* Subtítulo Narrativo */}
            <div className="mb-10 px-2">
                <h2 className="text-[13px] font-bold text-slate-500 uppercase tracking-[2px] mb-2 flex items-center gap-3">
                    <span className="w-8 h-[2px] bg-[#b38b4d]"></span>
                    Status de Monitoramento da Usina
                </h2>
                <p className="text-slate-400 text-sm leading-relaxed max-w-3xl">
                    Análise consolidada de <span className="text-slate-800 font-bold">{ucs.length} unidades</span> beneficiárias. 
                    Com base na média de economia de <span className="text-[#4db886] font-bold">{fmt(mediaMensal)}/mês</span>, 
                    projetamos a quitação total do capital investido para <span className="text-slate-800 font-black underline decoration-[#b38b4d] decoration-2">{playbackDate}</span>. 
                    Atualmente, o sistema já recuperou <span className="text-slate-800 font-bold">{fmtPercentShort(totalEconomizado/investimento)}</span> do valor original.
                </p>
            </div>

            {/* ── KPI CARDS ────────────────────────────────────────────────────── */}
            <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 mb-12">
                <KPICard label="CAPITAL INVESTIDO" value={fmt(investimento)} sub="Fundo de Ativos Solar" bgColor="bg-[#FFFDF7]" borderColor="border-[#F5E3C1]" textColor="text-[#B38B4D]" trendIcon={<span className="text-[10px]">⚖️</span>}/>
                <KPICard label="GANHO COMPROVADO" value={fmt(totalEconomizado)} sub={`${fmt(mediaMensal || 0)} / média ativa`} bgColor="bg-[#F0FDF6]" borderColor="border-[#BAF0D4]" textColor="text-[#4DB886]" trendIcon={<span className="text-[10px]">↑</span>}/>
                <KPICard label="PAYBACK ESTIMADO" value={playbackDate} sub={`${mesesRestantes} meses restantes`} bgColor="bg-[#F2F8FC]" borderColor="border-[#D1E5F5]" textColor="text-[#5DA0D6]" trendIcon={<span className="text-[10px]">⏱️</span>}/>
                <KPICard label="ROI ATUAL" value={fmtPercentShort(totalEconomizado/investimento)} sub={`R$ ${(investimento - totalEconomizado).toLocaleString('pt-BR')} de saldo`} bgColor="bg-[#F8FAFC]" borderColor="border-[#E2E8F0]" textColor="text-[#6B7280]" trendIcon={<span className="text-[10px]">📊</span>}/>
            </section>

            {/* ── CHARTS SECTION ───────────────────────────────────────────────── */}
            <section className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-12">
                <div className="lg:col-span-2 bg-white rounded-3xl border border-slate-200 shadow-[0_8px_40px_rgba(0,0,0,0.02)] p-8 relative overflow-hidden group">
                    <div className="absolute -right-20 -top-20 w-64 h-64 bg-[#f8fafc] rounded-full blur-3xl group-hover:bg-[#f0f9ff] transition-colors"></div>
                    <h2 className="text-xs font-black text-slate-800 uppercase tracking-widest mb-8 border-l-4 border-[#4DB886] pl-4">Projeção de Recuperação de Ativos</h2>
                    <div className="absolute top-8 right-8 flex gap-8 text-[10px] font-bold text-slate-400 uppercase tracking-widest no-print">
                        <div className="flex items-center gap-2"><span className="w-3 h-1 rounded-full bg-[#4DB886]"></span> Ganho Acumulado</div>
                        <div className="flex items-center gap-2"><span className="w-3 h-1 rounded-full bg-[#5DA0D6]"></span> Capital em Risco</div>
                    </div>
                    <div className="h-[320px] mt-4">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={historicoMensal}>
                                <defs>
                                    <linearGradient id="gSave" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#4DB886" stopOpacity={0.8}/><stop offset="95%" stopColor="#4DB886" stopOpacity={0.05}/></linearGradient>
                                    <linearGradient id="gRest" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#5DA0D6" stopOpacity={0.6}/><stop offset="95%" stopColor="#5DA0D6" stopOpacity={0}/></linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="mes" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#94a3b8", fontWeight: "800" }} />
                                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#94a3b8" }} tickFormatter={v => `R$${v}`} />
                                <RechartsTooltip content={<CustomTooltip />} />
                                <Area type="monotone" dataKey="acumulado" name="Economias Acumuladas" stroke="#4DB886" fill="url(#gSave)" strokeWidth={4} />
                                <Area type="monotone" dataKey="restante" name="Capital Restante" stroke="#5DA0D6" strokeDasharray="8 8" fill="url(#gRest)" strokeWidth={2} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-white rounded-3xl border border-slate-200 shadow-[0_8px_40px_rgba(0,0,0,0.02)] p-8">
                    <h2 className="text-xs font-black text-slate-800 uppercase tracking-widest mb-10 border-l-4 border-[#B38B4D] pl-4">Mix de Contribuição</h2>
                    <div className="space-y-10">
                        {ucs.map(uc => {
                            const totalUC = faturasExtradas.filter(f => f.uc === uc).reduce((a, f) => a + (f.credito || 0), 0);
                            const perc = (totalUC / totalEconomizado) * 100 || 0;
                            return (
                                <div key={uc} className="group">
                                    <div className="flex justify-between items-end mb-3">
                                        <span className="font-black text-2xl leading-none transition-transform group-hover:scale-110" style={{ color: unidadesInfo[uc].cor }}>{perc.toFixed(0)}%</span>
                                        <span className="text-[11px] font-black text-slate-500 uppercase tracking-widest">{unidadesInfo[uc].nome}</span>
                                    </div>
                                    <div className="bg-slate-50 border border-slate-100 rounded-full h-4 overflow-hidden border p-0.5">
                                        <div className="h-full rounded-full transition-all duration-1000 shadow-[2px_0_10px_rgba(0,0,0,0.1)] relative" style={{ width: `${perc}%`, backgroundColor: unidadesInfo[uc].cor }}>
                                            <div className="absolute inset-0 bg-gradient-to-b from-white/30 to-transparent"></div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>

            {/* ── Performance TABLE ─────────────────────────────────────────── */}
            <section className="bg-white rounded-3xl border border-slate-200 shadow-[0_12px_50px_rgba(0,0,0,0.03)] overflow-hidden">
                <div className="p-8 border-b border-slate-100 flex justify-between items-center bg-slate-50/20">
                    <div>
                        <h2 className="text-sm font-black text-slate-800 uppercase tracking-[2px] border-l-4 border-slate-800 pl-4 mb-1">Extrato Mensal Consolidado</h2>
                        <p className="text-[11px] text-slate-400 font-bold uppercase ml-5">Detalhamento dos Rendimentos por Ativo</p>
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-[13px] text-slate-600">
                        <thead>
                            <tr className="text-[10px] text-slate-400 font-black uppercase bg-slate-50 border-b border-slate-100 tracking-[1.5px]">
                                <th className="px-8 py-5">Período</th>
                                <th className="px-8 py-5 text-right">Valor Pago (Taxas)</th>
                                <th className="px-8 py-5 text-right">Valor Recuperado</th>
                                <th className="px-8 py-5 text-right">% Investimento</th>
                                <th className="px-8 py-5 text-center">Status</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                            {[...new Set(faturasExtradas.map(f => f.mes))].sort((a,b) => {
                                const [mA, yA] = a.split('/').map(Number);
                                const [mB, yB] = b.split('/').map(Number);
                                return (yB * 100 + mB) - (yA * 100 + mA);
                            }).map(mes => {
                                const faturasMes = faturasExtradas.filter(f => f.mes === mes);
                                const totalMes = faturasMes.reduce((a,f) => a + (f.credito || 0), 0);
                                const pagoMes = faturasMes.reduce((a,f) => a + (f.pago || 0), 0);
                                const percMes = (totalMes / investimento) * 100;
                                const isOpen = expandidoId === mes;

                                return (
                                    <React.Fragment key={mes}>
                                        <tr className={`hover:bg-[#F8FBFE] transition-colors cursor-pointer group ${isOpen ? 'bg-[#F2F8FC]/60' : ''}`} onClick={() => setExpandidoId(isOpen ? null : mes)}>
                                            <td className="px-8 py-6 font-black text-slate-800 flex items-center gap-4">
                                                <div className={`w-6 h-6 rounded-lg flex items-center justify-center border border-slate-200 text-slate-400 transition-all ${isOpen ? 'rotate-180 bg-slate-800 border-slate-800 text-white shadow-md' : 'bg-white group-hover:border-slate-800 group-hover:text-slate-800'}`}>
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" strokeWidth="4" stroke-linecap="round" stroke-linejoin="round"></path></svg>
                                                </div>
                                                {mes}
                                            </td>
                                            <td className="px-8 py-6 text-right font-medium text-slate-400">{fmt(pagoMes)}</td>
                                            <td className="px-8 py-6 text-right font-black text-slate-800">{fmt(totalMes)}</td>
                                            <td className="px-8 py-6 text-right">
                                                <span className="font-bold text-slate-500 bg-slate-100 px-3 py-1 rounded-full text-[11px] tabular-nums">{fmtPercentLong(totalMes / investimento)}</span>
                                            </td>
                                            <td className="px-8 py-6 flex justify-center">
                                                <span className="flex items-center gap-2 text-[#4DB886] font-black text-[10px] bg-[#EEFDF5] px-4 py-2 rounded-full border border-[#D1F7E1] shadow-sm">
                                                    CONCILIADO
                                                    <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"></path></svg>
                                                </span>
                                            </td>
                                        </tr>
                                        {isOpen && (
                                            <tr className="bg-white">
                                                <td colSpan="5" className="p-0 border-b border-slate-100">
                                                    <div className="p-10 pl-24 grid grid-cols-1 md:grid-cols-2 gap-12 bg-slate-50/50 relative">
                                                        <div className="absolute top-0 left-0 bottom-0 w-2.5 bg-[#4DB886] rounded-r-full shadow-[2px_0_10px_rgba(77,184,134,0.3)]"></div>
                                                        <div>
                                                            <div className="mb-8">
                                                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[2.5px] mb-1">Composição por Ativo</h4>
                                                                <p className="text-[11px] text-slate-300 font-bold uppercase italic">Detalhamento individual das unidades</p>
                                                            </div>
                                                            <div className="space-y-4">
                                                                {ucs.sort().map(uc => {
                                                                    const f = faturasMes.find(x => x.uc === uc);
                                                                    if (!f) return null;
                                                                    return (
                                                                        <div key={uc} className="flex justify-between items-center bg-white p-5 rounded-2xl border border-slate-100 shadow-[0_4px_15px_rgba(0,0,0,0.015)] hover:scale-[1.02] transition-all hover:bg-slate-50/50">
                                                                            <div className="flex items-center gap-4">
                                                                                <div className="w-4 h-4 rounded-md shadow-sm" style={{ background: unidadesInfo[uc].cor }}></div>
                                                                                <div className="flex flex-col">
                                                                                    <span className="font-black text-slate-800 text-[12px]">{unidadesInfo[uc].nome}</span>
                                                                                    {f.missing ? (
                                                                                        <span className="text-[10px] text-slate-300 font-bold uppercase">Sem Fatura</span>
                                                                                    ) : (
                                                                                        <span className="text-[10px] text-slate-400 font-bold">{f.kwh} kWh</span>
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                            <div className="flex flex-col items-end">
                                                                                <span className="font-black text-slate-900">{f.missing ? '---' : fmt(f.credito)}</span>
                                                                                <span className="text-[10px] font-bold text-[#b38b4d]">
                                                                                    Contrib: {f.missing || totalMes === 0 ? '0%' : ((f.credito / totalMes)*100).toFixed(0) + '%'}
                                                                                </span>
                                                                                <span className="text-[10px] font-bold text-slate-400 mt-0.5">
                                                                                    ROI U.C: {f.missing ? '---' : fmtPercentLong(f.credito / investimento)}
                                                                                </span>
                                                                            </div>
                                                                        </div>
                                                                    );
                                                                })}
                                                            </div>
                                                        </div>
                                                        <div className="bg-white rounded-3xl p-10 border border-slate-100 shadow-sm flex flex-col justify-center">
                                                            <div className="mb-8 text-center">
                                                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[2.5px] mb-1">Participação na Geração</h4>
                                                                <div className="w-10 h-1 bg-slate-100 mx-auto rounded-full"></div>
                                                            </div>
                                                            <div className="w-full h-48">
                                                                <ResponsiveContainer width="100%" height="100%">
                                                                    <BarChart data={faturasMes}>
                                                                        <XAxis dataKey="uc" hide />
                                                                        <YAxis hide />
                                                                        <Bar dataKey="credito" radius={[8, 8, 0, 0]}>
                                                                            {faturasMes.map((entry, index) => <Cell key={index} fill={unidadesInfo[entry.uc].cor} />)}
                                                                        </Bar>
                                                                    </BarChart>
                                                                </ResponsiveContainer>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </section>

        </div>
    );
}
