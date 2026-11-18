# Machine weight audit — 6 October 2026

Live session snapshot; standard = approved raw-material kilograms / approved product quantity. Measured weights are received scale readings, not inferred values.

| Machine | Job | Standard kg | Measured kg | Difference % |
|---|---|---:|---:|---:|
| IMM 301 | 119581 | 0.3580 | Not received | — |
| IMM 302 | 119043 | 0.0163 | Not received | — |
| IMM 303 | No active job | — | Not received | — |
| IMM 304 | 118619 | 0.2180 | 0.20722 | -4.94 |
| IMM 305 | 119644 | 0.0166 | Not received | — |
| IMM 306 | 118607 | 0.1355 | 0.13090 | -3.39 |
| IMM 307 | No active job | — | Not received | — |
| IMM 308 | 119051 | 0.0485 | 0.04348 | -10.35 |
| IMM 309 | 119034 | 0.1460 | 0.14518 | -0.56 |
| IMM 310 | 119040 | 0.0785 | 0.07858 | 0.10 |
| IMM 311 | 119443 | 0.0340 | 0.03185 | -6.32 |
| IMM 314 | 119369 | 0.1603 | 0.15925 | -0.66 |
| IMM 315 | 119535 | 0.1050 | 0.10106 | -3.75 |
| IMM 413 | 119375 | 0.0515 | 0.05366 | 4.19 |
| IMM 414 | 119083 | 0.0990 | 0.09660 | -2.42 |
| TEST-MACHINE | No active job | — | Not received | — |

309: sticker allocation 20000 / 20000 contributed a false 1 kg; corrected 1.1460 → 0.1460 kg.
414: sticker allocation 15000 / 15000 contributed a false 1 kg; corrected 1.0990 → 0.0990 kg.
301, 302, 305: current measured weight and received timestamp are null. No replacement measurements were fabricated.
308: latest stored measurement received 3 October 2026; other available readings were received 6 October.

Code corrected; running server needs restart to load the backend change.