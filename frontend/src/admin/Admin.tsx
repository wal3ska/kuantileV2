import { useState } from "react";
import { Universe } from "./Universe";
import { Portfolio } from "./Portfolio";
import { Optimize } from "./Optimize";
import { Risk } from "./Risk";
import { Deney } from "./Deney";
import { Manuel } from "./Manuel";

/* Quant Lab araclari — hepsi herkese acik. */
const TOOLS: { id: string; icon: string; title: string; desc: string; ready: boolean }[] = [
  {
    id: "universe",
    icon: "▦",
    title: "Varlık Evreni",
    desc: "Tüm BIST hisseleri: sektör, volatilite, geometrik getiri, likidite ve distress elemesi.",
    ready: true,
  },
  {
    id: "construct",
    icon: "◈",
    title: "Portföy & Analiz",
    desc: "Max-Sharpe/min-var/risk-parity/HRP ağırlık üretimi + OOS backtest + Monte Carlo projeksiyon + PDF risk raporu.",
    ready: true,
  },
  {
    id: "optimize",
    icon: "⟐",
    title: "Optimizasyon",
    desc: "Tüm yöntemleri kıyasla, etkin sınırda konumla, ½-Kelly kaldıraç.",
    ready: true,
  },
  {
    id: "risk",
    icon: "△",
    title: "Risk Ayrıştırma",
    desc: "Bileşen VaR/CVaR, yoğunlaşma ve faktör (sistematik/altın) maruziyeti.",
    ready: true,
  },
  {
    id: "experiment",
    icon: "⚗",
    title: "Deney",
    desc: "Tüm kısıt kombinasyonlarını tara, VaR>%3 ele, en iyi OOS-Sharpe portföyü bul.",
    ready: true,
  },
  {
    id: "manual",
    icon: "✎",
    title: "Manuel Test",
    desc: "Kendi hisse ve ağırlıklarını gir; sabit-ağırlık backtest, Sharpe/PSR, MC, VaR.",
    ready: true,
  },
];

function Panel() {
  const [active, setActive] = useState(TOOLS[0].id);
  const tool = TOOLS.find((t) => t.id === active)!;
  const noop = () => { /* herkese acik: auth-fail yok */ };

  return (
    <div className="a-shell">
      <aside className="a-side">
        <div className="a-brand">
          <img src="/logo.png" width="26" height="26" alt="" />
          <div>
            <b>Quant Lab</b>
            <span>portföy inşası</span>
          </div>
        </div>
        <nav className="a-nav">
          {TOOLS.map((t) => (
            <button key={t.id} className={t.id === active ? "on" : ""} onClick={() => setActive(t.id)}>
              <span className="a-nav-ic">{t.icon}</span>
              {t.title}
              {!t.ready && <span className="a-soon">yakında</span>}
            </button>
          ))}
        </nav>
        <div className="a-side-foot">
          <div className="a-side-links">
            <a href="/">← Kuantile'a dön</a>
          </div>
        </div>
      </aside>

      <main className="a-main">
        <header className="a-top">
          <div>
            <h1>{tool.title}</h1>
            <p>{tool.desc}</p>
          </div>
          <span className={`a-badge ${tool.ready ? "live" : ""}`}>{tool.ready ? "hazır" : "yapım aşamasında"}</span>
        </header>

        <section className="a-canvas">
          {active === "universe" ? (
            <Universe onAuthFail={noop} />
          ) : active === "construct" ? (
            <Portfolio onAuthFail={noop} />
          ) : active === "optimize" ? (
            <Optimize onAuthFail={noop} />
          ) : active === "risk" ? (
            <Risk onAuthFail={noop} />
          ) : active === "experiment" ? (
            <Deney onAuthFail={noop} />
          ) : active === "manual" ? (
            <Manuel onAuthFail={noop} />
          ) : (
            <div className="a-placeholder">
              <span className="a-ph-ic">{tool.icon}</span>
              <h2>{tool.title} aracı burada çalışacak</h2>
              <p>
                Motor bağlandığında bu bölge parametre paneli, sonuç tablosu ve canlı grafikle
                dolacak. Şimdilik iskelet hazır.
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export function Admin() {
  return <Panel />;
}
