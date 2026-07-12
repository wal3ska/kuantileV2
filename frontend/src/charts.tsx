/* El yapımı, bağımlılıksız grafik bileşenleri.
   Renk kuralları: tek ölçü -> tek hue (mavi); +/- kutuplu -> diverging mavi/kırmızı,
   nötr orta #383835. Metin her zaman metin renginde, seri renginde değil. */

import { useCallback, useRef, useState, type ReactNode } from "react";

/* Tema paleti — kökteki data-theme'e göre light/dark adımlar. */
function themeColors() {
  const dark = document.documentElement.dataset.theme === "dark";
  return dark
    ? {
        pos: "#3987e5", neg: "#e66767", neutralHex: "#383835",
        posRgb: [0x39, 0x87, 0xe5], negRgb: [0xe6, 0x67, 0x67], neutral: [0x38, 0x38, 0x35],
      }
    : {
        pos: "#2a78d6", neg: "#e34948", neutralHex: "#f0efec",
        posRgb: [0x2a, 0x78, 0xd6], negRgb: [0xe3, 0x49, 0x48], neutral: [0xf0, 0xef, 0xec],
      };
}

/* ---------- ortak tooltip ---------- */

interface TipState { x: number; y: number; content: ReactNode }

export function useTooltip() {
  const [tip, setTip] = useState<TipState | null>(null);
  const raf = useRef(0);

  const show = useCallback((e: React.MouseEvent, content: ReactNode) => {
    const { clientX, clientY } = e;
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() =>
      setTip({ x: clientX, y: clientY, content }));
  }, []);

  const hide = useCallback(() => {
    cancelAnimationFrame(raf.current);
    setTip(null);
  }, []);

  const node = tip ? (
    <div
      className="viz-tooltip"
      style={{
        left: Math.min(tip.x + 14, window.innerWidth - 300),
        top: Math.min(tip.y + 14, window.innerHeight - 120),
      }}
    >
      {tip.content}
    </div>
  ) : null;

  return { show, hide, node };
}

/* ---------- yatay bar ---------- */

export interface BarItem {
  label: string;
  value: number;
  tip?: ReactNode;
}

export function HBars({ items, format, diverging = false }: {
  items: BarItem[];
  format: (v: number) => string;
  diverging?: boolean;
}) {
  const { show, hide, node } = useTooltip();
  if (items.length === 0) return null;
  const { pos, neg } = themeColors();
  const maxAbs = Math.max(...items.map((i) => Math.abs(i.value)), 1e-9);

  return (
    <div>
      {items.map((it) => {
        const frac = Math.abs(it.value) / maxAbs;
        const color = !diverging ? pos : it.value >= 0 ? pos : neg;
        return (
          <div
            key={it.label}
            className="hbar-row"
            onMouseMove={(e) => show(e, it.tip ?? (
              <><div className="t">{it.label}</div>{format(it.value)}</>
            ))}
            onMouseLeave={hide}
          >
            <div className="hbar-label" title={it.label}>{it.label}</div>
            <div style={{ position: "relative", height: 18 }}>
              {/* taban çizgisi */}
              <div style={{
                position: "absolute", top: 0, bottom: 0, width: 1,
                left: diverging ? "50%" : 0, background: "var(--baseline)",
              }} />
              <div style={{
                position: "absolute",
                top: 2, bottom: 2,
                left: diverging ? (it.value >= 0 ? "50%" : `${50 - frac * 50}%`) : 0,
                width: `${frac * (diverging ? 50 : 100)}%`,
                minWidth: 2,
                background: color,
                borderRadius: it.value >= 0 ? "0 4px 4px 0" : "4px 0 0 4px",
              }} />
            </div>
            <div className="hbar-val">{format(it.value)}</div>
          </div>
        );
      })}
      {node}
    </div>
  );
}

/* ---------- korelasyon ısı haritası ---------- */

function lerp(a: readonly number[], b: readonly number[], t: number): string {
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export function CorrHeatmap({ matrix }: { matrix: Record<string, Record<string, number>> }) {
  const names = Object.keys(matrix);
  const { show, hide, node } = useTooltip();
  if (names.length < 2) return null;
  const { pos, neg, neutral, posRgb, negRgb, neutralHex } = themeColors();
  /* v in [-1,1] -> nötr zeminden kutup rengine */
  const divergingColor = (v: number) => {
    const t = Math.min(Math.abs(v), 1);
    return v >= 0 ? lerp(neutral, posRgb, t) : lerp(neutral, negRgb, t);
  };
  const showValues = names.length <= 8;
  const short = (s: string) => (s.length > 9 ? s.slice(0, 8) + "…" : s);

  return (
    <div style={{ maxWidth: 64 + names.length * 88 }}>
      <div className="heat-grid" style={{ gridTemplateColumns: `minmax(56px,1.4fr) repeat(${names.length}, 1fr)` }}>
        <div />
        {names.map((n) => <div key={n} className="heat-head" title={n}>{short(n)}</div>)}
        {names.map((row) => (
          [
            <div key={`${row}-h`} className="heat-head" style={{ justifyContent: "flex-end", paddingRight: 4 }} title={row}>
              {short(row)}
            </div>,
            ...names.map((col) => {
              const v = matrix[row]?.[col] ?? 0;
              return (
                <div
                  key={`${row}-${col}`}
                  className="heat-cell"
                  style={{
                    background: divergingColor(v),
                    color: Math.abs(v) > 0.55 ? "#ffffff" : "var(--ink)",
                    border: Math.abs(v) < 0.05 ? "1px solid var(--grid)" : "none",
                  }}
                  onMouseMove={(e) => show(e, (
                    <><div className="t">{row} × {col}</div>korelasyon: {v.toFixed(2)}</>
                  ))}
                  onMouseLeave={hide}
                >
                  {showValues ? v.toFixed(2) : ""}
                </div>
              );
            }),
          ]
        ))}
      </div>
      <div className="legend">
        <span className="it"><span className="sw" style={{ background: neg }} /> −1 ters yönlü</span>
        <span className="it"><span className="sw" style={{ background: neutralHex }} /> 0 ilişkisiz</span>
        <span className="it"><span className="sw" style={{ background: pos }} /> +1 aynı yönlü</span>
      </div>
      {node}
    </div>
  );
}
