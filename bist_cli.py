"""BIST veri hatti CLI (cron/elle calistirma).

Kullanim:
  python bist_cli.py universe      # hisse listesi + sektor + hafif fundamentaller
  python bist_cli.py prices        # Yahoo fiyat/hacim (incremental)
  python bist_cli.py fundamentals  # MaliTablo bilanco/gelir (Altman Z girdileri)
  python bist_cli.py snapshot      # ham metrikleri hesapla -> bist_metrics
  python bist_cli.py all           # universe -> prices -> fundamentals -> snapshot
"""

import sys
import time

from db import init_db


def _log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    job = argv[1].lower()
    init_db()

    import bist_data
    import bist_snapshot

    steps = ["universe", "prices", "fundamentals", "snapshot"] if job == "all" else [job]
    for step in steps:
        t0 = time.time()
        try:
            if step == "snapshot":
                res = bist_snapshot.run()
            else:
                res = bist_data.run(step)
            _log(f"{res}  ({time.time() - t0:.1f}s)")
        except Exception as exc:
            _log(f"HATA {step}: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
