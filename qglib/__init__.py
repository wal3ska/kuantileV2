"""qglib -- computational finance methods distilled from the Quant Guild Library
(Roman Paolucci, github.com/romanmichaelpaolucci/Quant-Guild-Library,
youtube.com/@QuantGuild), rewritten as a clean, vectorized, tested package.

Modules
-------
pricing     Black-Scholes/Greeks/IV, CRR, Crank-Nicolson, Monte Carlo + variance
            reduction, exotics, Heston (CF, Gil-Pelaez, Carr-Madan FFT, MC), Bates,
            variance swaps, delta-hedge P&L.
processes   Inverse transform, ABM/GBM/OU, Brownian bridge, fBM (Davies-Harte),
            Volterra & Markovian lifting (rough vol), Poisson, Merton jumps, Hawkes.
timeseries  AR(1)->OU, EWMA/GARCH(1,1) (fit & forecast), Kalman filters, Markov
            chains, Gaussian HMM (filter/smooth/Viterbi/Baum-Welch).
portfolio   MVO, tangency, risk parity, Black-Litterman, Kelly, CAPM alpha/beta, PCA.
metrics     CAGR, vol drag, Sharpe (+SE, PSR, MinTRL), Sortino, drawdowns, VaR/CVaR,
            tail probabilities, gambler's ruin, ergodicity, VRP, walk-forward splits.

Dependencies: numpy, scipy (statsmodels optional for adf_test).

NOT: Bu vendored kopyada yalnizca `metrics` ve `portfolio` eager import edilir
(Kuantile Quant Lab bunlari kullanir); pricing/processes/timeseries dosyalari
durur ama api import yolunu ve gereksiz bagimliliklari (statsmodels) tetiklemez.
"""
from . import metrics, portfolio  # noqa: F401

__version__ = "0.1.0"
