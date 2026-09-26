# qglib — Quant Guild hesaplamalı finans kütüphanesi

Quant Guild Library'deki (Roman Paolucci, 142 ders) hesaplamalı finans yöntemlerinin temiz,
vektörize ve test edilmiş Python sürümü. Bağımlılık: `numpy`, `scipy` (`statsmodels` opsiyonel).

## Kurulum (kendi projene bağlamak için)
```bash
cp -r qglib/ tests/ pyproject.toml <proje-klasörün>/   # ya da bu klasörü alt modül olarak ekle
pip install -e .            # veya: pip install -e ".[stats,test]"
pytest -q                   # 49 test
```

## Modüller
| Modül | İçerik |
|---|---|
| `qglib.pricing` | Black-Scholes, Greeks, implied vol, CRR (Amerikan), Crank-Nicolson, MC (antithetic + control variate), bariyer/Asya, Heston (CF, Gil-Pelaez, Carr-Madan FFT, MC), Bates, varyans swap, delta-hedge P&L |
| `qglib.processes` | Ters dönüşüm, ABM/GBM/OU (tam şema), Brownian bridge, fBM (Davies-Harte), Volterra + Markovian lifting (rough vol), Poisson/thinning, Merton sıçramaları, Hawkes (simülasyon + MLE) |
| `qglib.timeseries` | AR(1)→OU, ADF, EWMA, GARCH(1,1) MLE (normal/t) + tahmin, Kalman (genel, OU, local level, dinamik regresyon), Markov zinciri, Gaussian HMM (filter/smooth/Viterbi/Baum-Welch) |
| `qglib.portfolio` | MVO, tangency, min-var, efficient frontier, risk parity, Black-Litterman, Kelly, CAPM alfa/beta (t-stat), hedge oranı, PCA |
| `qglib.metrics` | CAGR, vol drag, Sharpe (+SE, PSR, MinTRL), Sortino, drawdown, Calmar, VaR/CVaR (tarihsel, parametrik, Cornish-Fisher), kuyruk olasılığı, gambler's ruin, ergodiklik, VRP, walk-forward |

## Doğrulama noktaları
- BS(100,100,1,%5,%20) = 10.450583572185565; Amerikan put ≈ 6.0896
- Heston Fang-Oosterlee referansı 5.785155450 (integral 1e-6, FFT 1e-5 hassasiyet)
- Tüm MC sonuçları 4 standart hata içinde; fBM/Volterra varyansları t^{2H}

## Orijinal notebook'lardan düzeltilen noktalar
- EWMA/GARCH başlangıç varyansı tüm örneklemden alınıyordu (look-ahead) → burn-in / uzun dönem varyans.
- Volterra ayrıklaştırması H<½ için varyansı ~%15 eksik veriyordu → varyans-eşlemeli ağırlıklar.
- Global `np.random.seed` yerine her fonksiyonda `rng` parametresi.

Skill'ler: `skills/` klasöründe üç SKILL.md (qg-derivatives-pricing, qg-stochastic-models, qg-portfolio-risk).
