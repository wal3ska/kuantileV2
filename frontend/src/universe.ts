/* Varlık evreni — app.py'deki listelerin TS karşılığı. */

import type { Currency, Source } from "./api";

export interface AssetInfo {
  name: string;
  ticker: string;
  currency: Currency;
  category: string;
  source: Source;
}

const BIST_100 = [
  "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKSA", "AKSEN", "ALARK", "ALBRK",
  "ALFAS", "ARCLK", "ASELS", "ASTOR", "BERA", "BIENY", "BIMAS", "BRSAN", "BRYAT", "BUCIM",
  "CANTE", "CCOLA", "CEMTS", "CIMSA", "CWENE", "DOAS", "DOHOL", "ECILC", "EGEEN", "EKGYO",
  "ENJSA", "ENKAI", "EREGL", "EUPWR", "EUREN", "FROTO", "GARAN", "GENIL", "GESAN", "GLYHO",
  "GUBRF", "GWIND", "HALKB", "HEKTS", "IMASM", "INDES", "INVEO", "ISCTR", "ISGYO", "ISMEN",
  "IZENR", "KALES", "KARSN", "KCAER", "KCHOL", "KLSER", "KMPUR", "KONTR", "KONYA", "KOZAA",
  "KOZAL", "KRDMD", "KZBGY", "MAVI", "MGROS", "MIATK", "ODAS", "OTKAR", "OYAKC", "PENTA",
  "PETKM", "PGSUS", "PNLSN", "QUAGR", "SAHOL", "SASA", "SAYAS", "SISE", "SKBNK", "SMRTG",
  "SOKM", "TABGD", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB", "TTKOM", "TTRAK",
  "TUKAS", "TUPRS", "ULKER", "VAKBN", "VESBE", "VESTL", "YEOTK", "YKBNK", "YYLGD", "ZOREN",
];

const CRYPTO: Record<string, string> = {
  "Bitcoin (BTC)": "BTC-USD", "Ethereum (ETH)": "ETH-USD", "Solana (SOL)": "SOL-USD",
  "XRP": "XRP-USD", "BNB": "BNB-USD", "Cardano (ADA)": "ADA-USD",
  "Dogecoin (DOGE)": "DOGE-USD", "Avalanche (AVAX)": "AVAX-USD",
  "Polkadot (DOT)": "DOT-USD", "Chainlink (LINK)": "LINK-USD",
};

const US_STOCKS: Record<string, string> = {
  "Apple (AAPL)": "AAPL", "Microsoft (MSFT)": "MSFT", "Nvidia (NVDA)": "NVDA",
  "Alphabet (GOOGL)": "GOOGL", "Amazon (AMZN)": "AMZN", "Meta (META)": "META",
  "Tesla (TSLA)": "TSLA", "Berkshire (BRK-B)": "BRK-B", "JPMorgan (JPM)": "JPM",
  "Visa (V)": "V", "Johnson & Johnson (JNJ)": "JNJ", "Exxon (XOM)": "XOM",
  "Coca-Cola (KO)": "KO", "McDonald's (MCD)": "MCD", "Disney (DIS)": "DIS",
  "Netflix (NFLX)": "NFLX", "AMD": "AMD", "Intel (INTC)": "INTC",
  "Boeing (BA)": "BA", "Caterpillar (CAT)": "CAT", "Goldman Sachs (GS)": "GS",
  "Palantir (PLTR)": "PLTR", "Uber (UBER)": "UBER", "Coinbase (COIN)": "COIN",
};

const COMMODITIES: Record<string, string> = {
  "Altın (ONS)": "GC=F", "Gümüş (ONS)": "SI=F", "Brent Petrol": "BZ=F",
  "WTI Petrol": "CL=F", "Doğalgaz": "NG=F", "Bakır": "HG=F",
};

/* Sentetik gram altın: backend GC=F * USDTRY / 31.1035 olarak türetir, TL cinsindendir. */
const GRAM_GOLD: AssetInfo = {
  name: "Altın (Gram TL)", ticker: "GRAMALTIN", currency: "TRY",
  category: "Emtia", source: "yahoo",
};

const INDICES: Record<string, string> = {
  "S&P 500": "^GSPC", "Nasdaq Composite": "^IXIC", "Nasdaq 100": "^NDX",
  "Dow Jones (DJIA)": "^DJI", "BIST 100": "XU100.IS", "BIST 30": "XU030.IS",
};

export const CATEGORIES = ["BIST", "Kripto", "ABD Hisse", "Emtia", "Endeks"] as const;

export const UNIVERSE: AssetInfo[] = [
  ...BIST_100.map((h) => ({
    name: h, ticker: `${h}.IS`, currency: "TRY" as Currency, category: "BIST", source: "yahoo" as Source,
  })),
  ...Object.entries(CRYPTO).map(([name, t]) => ({
    name, ticker: t, currency: "USD" as Currency, category: "Kripto", source: "yahoo" as Source,
  })),
  ...Object.entries(US_STOCKS).map(([name, t]) => ({
    name, ticker: t, currency: "USD" as Currency, category: "ABD Hisse", source: "yahoo" as Source,
  })),
  ...Object.entries(COMMODITIES).map(([name, t]) => ({
    name, ticker: t, currency: "USD" as Currency, category: "Emtia", source: "yahoo" as Source,
  })),
  GRAM_GOLD,
  ...Object.entries(INDICES).map(([name, t]) => ({
    name, ticker: t,
    currency: (t.endsWith(".IS") ? "TRY" : "USD") as Currency,
    category: "Endeks", source: "yahoo" as Source,
  })),
];

export function customBist(code: string): AssetInfo {
  const c = code.trim().toUpperCase().replace(/\.IS$/, "");
  return { name: c, ticker: `${c}.IS`, currency: "TRY", category: "BIST", source: "yahoo" };
}

export function customGlobal(code: string): AssetInfo {
  const c = code.trim().toUpperCase();
  return { name: c, ticker: c, currency: "USD", category: "Global", source: "yahoo" };
}

export function customTefas(code: string): AssetInfo {
  const c = code.trim().toUpperCase();
  return { name: `${c} (Fon)`, ticker: c, currency: "TRY", category: "TEFAS Fon", source: "tefas" };
}
