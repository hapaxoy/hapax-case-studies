# Vendor drift review -- Saarnitukku Oy FY2025 (6a frozen ledger, retrospective, in-sample)

Source ledger: `data/gl_transactions.csv`

Method: per-vendor, per-month volume-weighted unit price (falling back to invoice-level totals where no item granularity exists); expanding prior-months baseline (minimum 3 months of history, minimum 3 invoices to score a month); one-sided CUSUM of standardised monthly deviations (k = 0.5); flagged at CUSUM > h = 4.0. Deterministic, no machine learning. Parameters fixed before any 06b data existed and never tuned against this ledger's output.

**200 vendors in the ledger; 177 scoreable (cleared the 3-invoices/month floor in at least 4 months); 23 not scoreable at all.**

## Ranked table (top 25 of 177 scoreable vendors, by peak CUSUM)

| Rank | Vendor ID | Vendor name | Peak CUSUM | Peak month | Flagged | First crossing month |
|---|---|---|---|---|---|---|
| 1 | V-0080 | Porttilogistiikka Oy | 30.36 | May | **YES** | May |
| 2 | V-0065 | Myrkvarn Malmteknik | 19.70 | Jun | **YES** | Apr |
| 3 | V-0068 | Kuuseoru VaruGrupp | 13.70 | Apr | **YES** | Apr |
| 4 | V-0072 | Nostotukku Tmi | 12.64 | Dec | **YES** | May |
| 5 | V-0132 | Kulmatekniikka Tmi | 12.00 | Aug | **YES** | May |
| 6 | V-0103 | Ruuvimateriaali Oy | 10.93 | Nov | **YES** | Apr |
| 7 | V-0155 | Pistetukku Oy Ab | 10.75 | Dec | **YES** | Apr |
| 8 | V-0195 | Fjellskor Nordhandel AS | 10.19 | Dec | **YES** | Apr |
| 9 | V-0165 | Kiskohuolto Tmi | 9.94 | Oct | **YES** | Apr |
| 10 | V-0084 | Kotelopalvelu Oy | 9.43 | Jul | **YES** | Jun |
| 11 | V-0142 | Felsmark Technikhandel GmbH | 9.26 | Jun | **YES** | Jun |
| 12 | V-0110 | Levykomponentti Oy Ab | 9.14 | May | **YES** | Apr |
| 13 | V-0061 | Turvavaraosa Oy | 8.52 | May | **YES** | Apr |
| 14 | V-0159 | Palkkitukku Oy | 7.93 | Jun | **YES** | May |
| 15 | V-0160 | Fjellskor Stalteknikk AS | 7.79 | May | **YES** | May |
| 16 | V-0069 | Porttijärjestelmä Tmi | 7.24 | Aug | **YES** | Jun |
| 17 | V-0176 | Hällsvik Nordgrossist | 7.20 | Jun | **YES** | Jun |
| 18 | V-0180 | Akselitarvike Oy Ab | 7.02 | Jun | **YES** | May |
| 19 | V-0182 | Varaosahuolto Ky | 6.98 | Aug | **YES** | Aug |
| 20 | V-0029 | Poratekniikka Tmi | 6.96 | Jun | **YES** | Apr |
| 21 | V-0058 | Levymateriaali Tmi | 6.92 | Apr | **YES** | Apr |
| 22 | V-0088 | Siltamateriaali Ky | 6.87 | Sep | **YES** | Aug |
| 23 | V-0094 | Levylogistiikka Oy | 6.80 | Dec | **YES** | Jun |
| 24 | V-0034 | Metallimateriaali Oy Ab | 6.65 | Jul | **YES** | Jul |
| 25 | V-0181 | Skavlund Nordteknikk AS | 6.35 | Dec | **YES** | Dec |

## Flagged vendors (48) -- trajectory detail

### Porttilogistiikka Oy (V-0080)

Peak CUSUM 30.36 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 560.24 | - | - | - | - |
| Feb | baseline-only | 548.50 | - | - | - | - |
| Mar | baseline-only | 581.31 | - | - | - | - |
| Apr | scored | 612.72 | 563.35 | 13.576 | 3.64 | 3.14 |
| May | scored | 1252.06 | 575.69 | 24.397 | 27.72 | 30.36 |
| Jun | scored | 525.20 | 710.96 | 271.428 | -0.68 | 29.18 |
| Jul | scored | 915.47 | 680.00 | 257.268 | 0.92 | 29.59 |
| Aug | scored | 642.00 | 713.64 | 252.034 | -0.28 | 28.81 |
| Sep | scored | 676.89 | 704.69 | 236.944 | -0.12 | 28.19 |
| Oct | scored | 807.84 | 701.60 | 223.563 | 0.48 | 28.16 |
| Nov | scored | 667.61 | 712.22 | 214.472 | -0.21 | 27.46 |
| Dec | scored | 737.67 | 708.17 | 204.893 | 0.14 | 27.10 |

### Myrkvarn Malmteknik (V-0065)

Peak CUSUM 19.70 in Jun; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 567.22 | - | - | - | - |
| Feb | baseline-only | 574.86 | - | - | - | - |
| Mar | baseline-only | 579.06 | - | - | - | - |
| Apr | scored | 640.20 | 573.71 | 4.901 | 13.57 | 13.07 |
| May | scored | 762.71 | 590.33 | 29.102 | 5.92 | 18.49 |
| Jun | scored | 750.67 | 624.81 | 73.701 | 1.71 | 19.70 |
| Jul | scored | 660.08 | 645.78 | 82.017 | 0.17 | 19.37 |
| Aug | scored | 591.54 | 647.83 | 76.097 | -0.74 | 18.13 |
| Sep | scored | 632.86 | 640.79 | 73.576 | -0.11 | 17.52 |
| Oct | scored | 704.06 | 639.91 | 69.413 | 0.92 | 17.95 |
| Nov | scored | 628.97 | 646.32 | 68.606 | -0.25 | 17.20 |
| Dec | scored | 661.48 | 644.75 | 65.603 | 0.26 | 16.95 |

### Kuuseoru VaruGrupp (V-0068)

Peak CUSUM 13.70 in Apr; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 3358.29 | - | - | - | - |
| Feb | baseline-only | 3322.70 | - | - | - | - |
| Mar | baseline-only | 3348.45 | - | - | - | - |
| Apr | scored | 3556.19 | 3343.15 | 15.005 | 14.20 | 13.70 |
| May | scored | 3321.82 | 3396.41 | 93.160 | -0.80 | 12.40 |
| Jun | scored | 3164.36 | 3381.49 | 88.505 | -2.45 | 9.44 |
| Jul | scored | 3032.02 | 3345.30 | 114.349 | -2.74 | 6.20 |
| Aug | scored | 3486.51 | 3300.55 | 152.398 | 1.22 | 6.92 |
| Sep | scored | 2920.17 | 3323.79 | 155.256 | -2.60 | 3.82 |
| Oct | scored | 3041.09 | 3278.95 | 193.691 | -1.23 | 2.10 |
| Nov | scored | 3377.05 | 3255.16 | 197.120 | 0.62 | 2.21 |
| Dec | scored | 3426.06 | 3266.24 | 191.185 | 0.84 | 2.55 |

### Nostotukku Tmi (V-0072)

Peak CUSUM 12.64 in Dec; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 579.25 | - | - | - | - |
| Feb | baseline-only | 594.00 | - | - | - | - |
| Mar | baseline-only | 585.14 | - | - | - | - |
| Apr | scored | 611.24 | 586.13 | 6.064 | 4.14 | 3.64 |
| May | scored | 703.87 | 592.41 | 12.074 | 9.23 | 12.37 |
| Jun | scored | 629.53 | 614.70 | 45.874 | 0.32 | 12.20 |
| Jul | scored | 580.35 | 617.17 | 42.241 | -0.87 | 10.82 |
| Aug | scored | 646.85 | 611.91 | 41.176 | 0.85 | 11.17 |
| Sep | scored | 570.82 | 616.28 | 40.212 | -1.13 | 9.54 |
| Oct | scored | 698.76 | 611.23 | 40.515 | 2.16 | 11.20 |
| Nov | scored | 653.92 | 619.98 | 46.550 | 0.73 | 11.43 |
| Dec | scored | 700.47 | 623.07 | 45.444 | 1.70 | 12.64 |

### Kulmatekniikka Tmi (V-0132)

Peak CUSUM 12.00 in Aug; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 2990.91 | - | - | - | - |
| Feb | baseline-only | 2961.89 | - | - | - | - |
| Mar | baseline-only | 3106.00 | - | - | - | - |
| Apr | scored | 3063.65 | 3019.60 | 62.228 | 0.71 | 0.21 |
| May | scored | 3686.34 | 3030.61 | 57.167 | 11.47 | 11.18 |
| Jun | scored | 3369.74 | 3161.76 | 267.230 | 0.78 | 11.46 |
| Jul | scored | 3334.80 | 3196.42 | 255.964 | 0.54 | 11.50 |
| Aug | scored | 3458.87 | 3216.19 | 241.874 | 1.00 | 12.00 |
| Sep | scored | 3200.54 | 3246.53 | 240.065 | -0.19 | 11.31 |
| Oct | scored | 3320.93 | 3241.42 | 226.796 | 0.35 | 11.16 |
| Nov | scored | 2994.98 | 3249.37 | 216.476 | -1.18 | 9.48 |
| Dec | scored | 2907.47 | 3226.24 | 218.975 | -1.46 | 7.53 |

### Ruuvimateriaali Oy (V-0103)

Peak CUSUM 10.93 in Nov; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1726.18 | - | - | - | - |
| Feb | baseline-only | 1563.62 | - | - | - | - |
| Mar | baseline-only | 1493.50 | - | - | - | - |
| Apr | scored | 2146.20 | 1594.43 | 97.458 | 5.66 | 5.16 |
| May | scored | 2542.21 | 1732.37 | 253.393 | 3.20 | 7.86 |
| Oct | scored | 2928.31 | 1894.34 | 395.347 | 2.62 | 9.97 |
| Nov | scored | 2836.24 | 2066.67 | 527.954 | 1.46 | 10.93 |
| Dec | scored | 2376.04 | 2176.61 | 558.064 | 0.36 | 10.79 |

### Pistetukku Oy Ab (V-0155)

Peak CUSUM 10.75 in Dec; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 857.38 | - | - | - | - |
| Feb | baseline-only | 890.14 | - | - | - | - |
| Mar | baseline-only | 876.58 | - | - | - | - |
| Apr | scored | 1020.07 | 874.70 | 13.439 | 10.82 | 10.32 |
| May | scored | 772.54 | 911.04 | 64.012 | -2.16 | 7.65 |
| Jun | scored | 912.84 | 883.34 | 79.670 | 0.37 | 7.52 |
| Jul | scored | 853.82 | 888.26 | 73.554 | -0.47 | 6.56 |
| Aug | scored | 947.57 | 883.34 | 69.156 | 0.93 | 6.98 |
| Sep | scored | 1102.80 | 891.37 | 68.088 | 3.11 | 9.59 |
| Oct | scored | 1020.43 | 914.86 | 92.391 | 1.14 | 10.23 |
| Nov | scored | 894.54 | 925.42 | 93.197 | -0.33 | 9.40 |
| Dec | scored | 1088.00 | 922.61 | 89.302 | 1.85 | 10.75 |

### Fjellskor Nordhandel AS (V-0195)

Peak CUSUM 10.19 in Dec; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1392.55 | - | - | - | - |
| Feb | baseline-only | 1777.96 | - | - | - | - |
| Mar | baseline-only | 1602.75 | - | - | - | - |
| Apr | scored | 2725.42 | 1591.09 | 157.559 | 7.20 | 6.70 |
| May | scored | 1763.30 | 1874.67 | 509.782 | -0.22 | 5.98 |
| Jun | scored | 3237.93 | 1852.40 | 458.133 | 3.02 | 8.51 |
| Aug | scored | 2225.48 | 2083.32 | 664.477 | 0.21 | 8.22 |
| Oct | scored | 2486.67 | 2103.63 | 617.194 | 0.62 | 8.34 |
| Nov | scored | 1960.13 | 2151.51 | 591.067 | -0.32 | 7.52 |
| Dec | scored | 3909.25 | 2130.24 | 560.499 | 3.17 | 10.19 |

### Kiskohuolto Tmi (V-0165)

Peak CUSUM 9.94 in Oct; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 2481.42 | - | - | - | - |
| Feb | baseline-only | 2147.24 | - | - | - | - |
| Mar | baseline-only | 2579.82 | - | - | - | - |
| Apr | scored | 3802.82 | 2402.83 | 185.141 | 7.56 | 7.06 |
| May | scored | 2408.11 | 2752.82 | 627.060 | -0.55 | 6.01 |
| Jun | scored | 3068.42 | 2683.88 | 577.561 | 0.67 | 6.18 |
| Sep | scored | 4026.56 | 2747.97 | 546.368 | 2.34 | 8.02 |
| Oct | scored | 4568.76 | 2930.63 | 675.316 | 2.43 | 9.94 |
| Nov | scored | 2558.49 | 3135.39 | 832.197 | -0.69 | 8.75 |
| Dec | scored | 1954.95 | 3071.29 | 805.278 | -1.39 | 6.86 |

### Kotelopalvelu Oy (V-0084)

Peak CUSUM 9.43 in Jul; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 2394.31 | - | - | - | - |
| Feb | baseline-only | 2506.78 | - | - | - | - |
| Mar | baseline-only | 2605.74 | - | - | - | - |
| Apr | scored | 2772.82 | 2502.28 | 86.373 | 3.13 | 2.63 |
| May | scored | 2677.66 | 2569.91 | 138.994 | 0.78 | 2.91 |
| Jun | scored | 2889.95 | 2591.46 | 131.579 | 2.27 | 4.68 |
| Jul | scored | 3500.92 | 2641.21 | 163.714 | 5.25 | 9.43 |
| Aug | scored | 2778.29 | 2764.03 | 336.862 | 0.04 | 8.97 |
| Sep | scored | 2409.15 | 2765.81 | 315.141 | -1.13 | 7.34 |
| Oct | scored | 1918.69 | 2726.18 | 317.557 | -2.54 | 4.30 |
| Nov | scored | 2567.82 | 2645.43 | 386.577 | -0.20 | 3.59 |
| Dec | scored | 3172.89 | 2638.38 | 369.261 | 1.45 | 4.54 |

### Felsmark Technikhandel GmbH (V-0142)

Peak CUSUM 9.26 in Jun; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 3550.20 | - | - | - | - |
| Apr | baseline-only | 3722.01 | - | - | - | - |
| May | baseline-only | 3625.80 | - | - | - | - |
| Jun | scored | 4319.14 | 3632.67 | 70.312 | 9.76 | 9.26 |
| Jul | scored | 3421.41 | 3804.29 | 303.421 | -1.26 | 7.50 |
| Aug | scored | 3756.31 | 3727.71 | 311.619 | 0.09 | 7.09 |
| Oct | scored | 3318.45 | 3732.48 | 284.667 | -1.45 | 5.14 |
| Nov | scored | 2963.44 | 3673.33 | 300.747 | -2.36 | 2.28 |

### Levykomponentti Oy Ab (V-0110)

Peak CUSUM 9.14 in May; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 526.85 | - | - | - | - |
| Feb | baseline-only | 572.83 | - | - | - | - |
| Mar | baseline-only | 483.45 | - | - | - | - |
| Apr | scored | 746.51 | 527.71 | 36.494 | 6.00 | 5.50 |
| May | scored | 996.38 | 582.41 | 99.876 | 4.14 | 9.14 |
| Jun | scored | 431.53 | 665.20 | 188.148 | -1.24 | 7.40 |
| Jul | scored | 645.65 | 626.26 | 192.570 | 0.10 | 7.00 |
| Aug | scored | 538.35 | 629.03 | 178.415 | -0.51 | 5.99 |
| Sep | scored | 659.56 | 617.69 | 169.564 | 0.25 | 5.74 |
| Oct | scored | 632.81 | 622.34 | 160.407 | 0.07 | 5.30 |
| Nov | scored | 612.86 | 623.39 | 152.208 | -0.07 | 4.73 |
| Dec | scored | 638.97 | 622.43 | 145.156 | 0.11 | 4.35 |

### Turvavaraosa Oy (V-0061)

Peak CUSUM 8.52 in May; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1708.03 | - | - | - | - |
| Feb | baseline-only | 1767.04 | - | - | - | - |
| Mar | baseline-only | 1758.93 | - | - | - | - |
| Apr | scored | 1974.81 | 1744.67 | 26.116 | 8.81 | 8.31 |
| May | scored | 1874.28 | 1802.20 | 102.191 | 0.71 | 8.52 |
| Jun | scored | 1813.91 | 1816.62 | 95.842 | -0.03 | 7.99 |
| Jul | scored | 1826.55 | 1816.17 | 87.497 | 0.12 | 7.61 |
| Aug | scored | 1836.12 | 1817.65 | 81.088 | 0.23 | 7.34 |
| Sep | scored | 1700.15 | 1819.96 | 76.096 | -1.57 | 5.26 |
| Oct | scored | 1931.80 | 1806.65 | 81.025 | 1.54 | 6.31 |
| Nov | scored | 1979.23 | 1819.16 | 85.546 | 1.87 | 7.68 |
| Dec | scored | 1860.19 | 1833.71 | 93.651 | 0.28 | 7.46 |

### Palkkitukku Oy (V-0159)

Peak CUSUM 7.93 in Jun; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1821.11 | - | - | - | - |
| Feb | baseline-only | 1871.24 | - | - | - | - |
| Mar | baseline-only | 1751.20 | - | - | - | - |
| Apr | scored | 1903.63 | 1814.52 | 49.225 | 1.81 | 1.31 |
| May | scored | 2026.38 | 1836.79 | 57.499 | 3.30 | 4.11 |
| Jun | scored | 2270.94 | 1874.71 | 91.627 | 4.32 | 7.93 |
| Jul | scored | 1525.02 | 1940.75 | 169.711 | -2.45 | 4.98 |
| Aug | scored | 1874.05 | 1881.36 | 214.127 | -0.03 | 4.45 |
| Sep | scored | 1691.47 | 1880.44 | 200.312 | -0.94 | 3.00 |
| Oct | scored | 1771.53 | 1859.45 | 197.974 | -0.44 | 2.06 |
| Nov | scored | 1768.79 | 1850.66 | 189.658 | -0.43 | 1.13 |
| Dec | scored | 1907.80 | 1843.21 | 182.357 | 0.35 | 0.98 |

### Fjellskor Stalteknikk AS (V-0160)

Peak CUSUM 7.79 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1939.36 | - | - | - | - |
| Feb | baseline-only | 1874.77 | - | - | - | - |
| Mar | baseline-only | 1835.45 | - | - | - | - |
| Apr | scored | 1937.17 | 1883.20 | 42.838 | 1.26 | 0.76 |
| May | scored | 2226.69 | 1896.69 | 43.846 | 7.53 | 7.79 |
| Jun | scored | 1864.81 | 1962.69 | 137.703 | -0.71 | 6.58 |
| Jul | scored | 1724.49 | 1946.38 | 130.891 | -1.70 | 4.38 |
| Aug | scored | 1823.41 | 1914.68 | 143.923 | -0.63 | 3.25 |
| Sep | scored | 1704.94 | 1903.27 | 137.969 | -1.44 | 1.31 |
| Oct | scored | 2024.56 | 1881.23 | 144.241 | 0.99 | 1.80 |
| Nov | scored | 1891.68 | 1895.56 | 143.435 | -0.03 | 1.28 |
| Dec | scored | 1809.80 | 1895.21 | 136.765 | -0.62 | 0.15 |

### Porttijärjestelmä Tmi (V-0069)

Peak CUSUM 7.24 in Aug; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 687.67 | - | - | - | - |
| Feb | baseline-only | 897.29 | - | - | - | - |
| Mar | baseline-only | 681.37 | - | - | - | - |
| Apr | scored | 811.57 | 755.45 | 100.335 | 0.56 | 0.06 |
| May | scored | 977.97 | 769.48 | 90.227 | 2.31 | 1.87 |
| Jun | scored | 1224.43 | 811.17 | 116.050 | 3.56 | 4.93 |
| Jul | scored | 1231.25 | 880.05 | 186.928 | 1.88 | 6.31 |
| Aug | scored | 1233.05 | 930.22 | 212.258 | 1.43 | 7.24 |
| Sep | scored | 616.37 | 968.08 | 222.379 | -1.58 | 5.16 |
| Oct | scored | 1150.64 | 929.00 | 237.011 | 0.94 | 5.59 |
| Nov | scored | 833.69 | 951.16 | 234.475 | -0.50 | 4.59 |
| Dec | scored | 919.49 | 940.48 | 226.099 | -0.09 | 4.00 |

### Hällsvik Nordgrossist (V-0176)

Peak CUSUM 7.20 in Jun; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 584.13 | - | - | - | - |
| Feb | baseline-only | 603.82 | - | - | - | - |
| Mar | baseline-only | 689.88 | - | - | - | - |
| Apr | scored | 609.56 | 625.94 | 45.921 | -0.36 | 0.00 |
| May | scored | 579.79 | 621.85 | 40.396 | -1.04 | 0.00 |
| Jun | scored | 920.15 | 613.44 | 39.855 | 7.70 | 7.20 |
| Jul | scored | 605.33 | 664.56 | 119.954 | -0.49 | 6.20 |
| Aug | scored | 680.08 | 656.09 | 112.973 | 0.21 | 5.91 |
| Sep | scored | 602.18 | 659.09 | 105.974 | -0.54 | 4.88 |
| Oct | scored | 689.12 | 652.77 | 101.502 | 0.36 | 4.74 |
| Nov | scored | 745.29 | 656.40 | 96.908 | 0.92 | 5.15 |
| Dec | scored | 685.49 | 664.48 | 95.867 | 0.22 | 4.87 |

### Akselitarvike Oy Ab (V-0180)

Peak CUSUM 7.02 in Jun; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 771.87 | - | - | - | - |
| Feb | baseline-only | 916.96 | - | - | - | - |
| Mar | baseline-only | 802.76 | - | - | - | - |
| Apr | scored | 758.85 | 830.53 | 62.400 | -1.15 | 0.00 |
| May | scored | 1253.85 | 812.61 | 62.319 | 7.08 | 6.58 |
| Jun | scored | 1074.48 | 900.86 | 185.090 | 0.94 | 7.02 |
| Jul | scored | 736.05 | 929.80 | 180.929 | -1.07 | 5.45 |
| Aug | scored | 955.06 | 902.12 | 180.708 | 0.29 | 5.24 |
| Sep | scored | 1107.20 | 908.74 | 169.941 | 1.17 | 5.91 |
| Oct | scored | 954.70 | 930.79 | 171.933 | 0.14 | 5.55 |
| Nov | scored | 965.00 | 933.18 | 163.268 | 0.19 | 5.24 |
| Dec | scored | 679.85 | 936.07 | 155.939 | -1.64 | 3.10 |

### Varaosahuolto Ky (V-0182)

Peak CUSUM 6.98 in Aug; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1807.34 | - | - | - | - |
| Feb | baseline-only | 1272.84 | - | - | - | - |
| Mar | baseline-only | 1580.57 | - | - | - | - |
| Apr | scored | 2410.68 | 1553.58 | 219.039 | 3.91 | 3.41 |
| May | scored | 1563.81 | 1767.86 | 416.803 | -0.49 | 2.42 |
| Jun | scored | 1444.75 | 1727.05 | 381.630 | -0.74 | 1.18 |
| Jul | scored | 2105.08 | 1680.00 | 363.918 | 1.17 | 1.85 |
| Aug | scored | 3812.76 | 1740.72 | 368.296 | 5.63 | 6.98 |
| Sep | scored | 1254.93 | 1999.73 | 766.987 | -0.97 | 5.51 |
| Oct | scored | 1124.12 | 1916.97 | 760.061 | -1.04 | 3.96 |
| Nov | scored | 1987.73 | 1837.69 | 759.275 | 0.20 | 3.66 |
| Dec | scored | 1760.50 | 1851.33 | 725.225 | -0.13 | 3.04 |

### Poratekniikka Tmi (V-0029)

Peak CUSUM 6.96 in Jun; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 654.46 | - | - | - | - |
| Feb | baseline-only | 663.31 | - | - | - | - |
| Mar | baseline-only | 687.14 | - | - | - | - |
| Apr | scored | 749.73 | 668.30 | 13.802 | 5.90 | 5.40 |
| May | scored | 643.20 | 688.66 | 37.231 | -1.22 | 3.68 |
| Jun | scored | 823.15 | 679.57 | 37.942 | 3.78 | 6.96 |
| Jul | scored | 640.23 | 703.50 | 63.742 | -0.99 | 5.47 |
| Aug | scored | 731.68 | 694.46 | 63.030 | 0.59 | 5.56 |
| Sep | scored | 613.47 | 699.11 | 60.231 | -1.42 | 3.64 |
| Oct | scored | 551.42 | 689.60 | 62.842 | -2.20 | 0.94 |
| Nov | scored | 689.93 | 675.78 | 72.613 | 0.19 | 0.63 |
| Dec | scored | 569.28 | 677.07 | 69.353 | -1.55 | 0.00 |

### Levymateriaali Tmi (V-0058)

Peak CUSUM 6.92 in Apr; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 595.96 | - | - | - | - |
| Feb | baseline-only | 539.06 | - | - | - | - |
| Mar | baseline-only | 578.04 | - | - | - | - |
| Apr | scored | 747.28 | 571.02 | 23.756 | 7.42 | 6.92 |
| May | scored | 596.28 | 615.09 | 79.046 | -0.24 | 6.18 |
| Jun | scored | 570.46 | 611.32 | 71.100 | -0.57 | 5.11 |
| Jul | scored | 591.25 | 604.51 | 66.668 | -0.20 | 4.41 |
| Aug | scored | 627.94 | 602.62 | 61.897 | 0.41 | 4.32 |
| Sep | scored | 585.10 | 605.78 | 58.501 | -0.35 | 3.46 |
| Oct | scored | 552.04 | 603.49 | 55.537 | -0.93 | 2.04 |
| Nov | scored | 716.45 | 598.34 | 54.901 | 2.15 | 3.69 |
| Dec | scored | 828.00 | 609.08 | 62.395 | 3.51 | 6.70 |

### Siltamateriaali Ky (V-0088)

Peak CUSUM 6.87 in Sep; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 3289.55 | - | - | - | - |
| Feb | baseline-only | 2842.24 | - | - | - | - |
| Mar | baseline-only | 3079.80 | - | - | - | - |
| Apr | scored | 3139.83 | 3070.53 | 182.734 | 0.38 | 0.00 |
| May | scored | 3581.26 | 3087.85 | 161.072 | 3.06 | 2.56 |
| Jun | scored | 3545.03 | 3186.53 | 244.350 | 1.47 | 3.53 |
| Jul | scored | 3315.23 | 3246.28 | 260.012 | 0.27 | 3.30 |
| Aug | scored | 4216.21 | 3256.13 | 241.930 | 3.97 | 6.76 |
| Sep | scored | 3611.03 | 3376.14 | 389.909 | 0.60 | 6.87 |
| Oct | scored | 3176.59 | 3402.24 | 374.948 | -0.60 | 5.76 |
| Nov | scored | 3413.52 | 3379.68 | 362.091 | 0.09 | 5.36 |
| Dec | scored | 3194.61 | 3382.75 | 345.377 | -0.54 | 4.31 |

### Levylogistiikka Oy (V-0094)

Peak CUSUM 6.80 in Dec; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 2892.88 | - | - | - | - |
| Feb | baseline-only | 2668.16 | - | - | - | - |
| Mar | baseline-only | 2853.86 | - | - | - | - |
| Apr | scored | 3026.82 | 2804.96 | 98.040 | 2.26 | 1.76 |
| May | scored | 3055.63 | 2860.43 | 128.211 | 1.52 | 2.79 |
| Jun | scored | 3513.87 | 2899.47 | 138.733 | 4.43 | 6.71 |
| Jul | scored | 2493.95 | 3001.87 | 261.665 | -1.94 | 4.27 |
| Aug | scored | 3652.80 | 2929.31 | 300.462 | 2.41 | 6.18 |
| Sep | scored | 2896.34 | 3019.75 | 369.112 | -0.33 | 5.35 |
| Oct | scored | 2972.92 | 3006.03 | 350.156 | -0.09 | 4.75 |
| Nov | scored | 3343.43 | 3002.72 | 332.336 | 1.03 | 5.28 |
| Dec | scored | 3705.85 | 3033.70 | 331.662 | 2.03 | 6.80 |

### Metallimateriaali Oy Ab (V-0034)

Peak CUSUM 6.65 in Jul; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1746.14 | - | - | - | - |
| Feb | baseline-only | 2217.82 | - | - | - | - |
| Apr | baseline-only | 1290.95 | - | - | - | - |
| May | scored | 2847.30 | 1751.63 | 378.413 | 2.90 | 2.40 |
| Jul | scored | 4765.10 | 2025.55 | 576.616 | 4.75 | 6.65 |
| Nov | scored | 1823.60 | 2573.46 | 1211.118 | -0.62 | 5.53 |

### Skavlund Nordteknikk AS (V-0181)

Peak CUSUM 6.35 in Dec; first crossed h = 4.0 in Dec.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 609.20 | - | - | - | - |
| Feb | baseline-only | 465.70 | - | - | - | - |
| Mar | baseline-only | 589.77 | - | - | - | - |
| Apr | scored | 572.29 | 554.89 | 63.565 | 0.27 | 0.00 |
| May | scored | 639.00 | 559.24 | 55.562 | 1.44 | 0.94 |
| Jun | scored | 589.79 | 575.19 | 59.055 | 0.25 | 0.68 |
| Jul | scored | 619.43 | 577.63 | 54.183 | 0.77 | 0.95 |
| Aug | scored | 598.62 | 583.60 | 52.253 | 0.29 | 0.74 |
| Sep | scored | 530.82 | 585.48 | 49.130 | -1.11 | 0.00 |
| Oct | scored | 717.43 | 579.40 | 49.402 | 2.79 | 2.29 |
| Nov | scored | 716.16 | 593.21 | 62.539 | 1.97 | 3.76 |
| Dec | scored | 818.24 | 604.38 | 69.318 | 3.09 | 6.35 |

### Hällsvik Nordhandel 18 (V-0197)

Peak CUSUM 6.13 in Aug; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 2848.86 | - | - | - | - |
| Feb | baseline-only | 2772.79 | - | - | - | - |
| Mar | baseline-only | 2872.38 | - | - | - | - |
| Apr | scored | 2746.96 | 2831.34 | 42.502 | -1.99 | 0.00 |
| May | scored | 2783.11 | 2810.25 | 51.864 | -0.52 | 0.00 |
| Jun | scored | 2922.62 | 2804.82 | 47.642 | 2.47 | 1.97 |
| Jul | scored | 3006.62 | 2824.45 | 61.796 | 2.95 | 4.42 |
| Aug | scored | 3039.49 | 2850.48 | 85.653 | 2.21 | 6.13 |
| Sep | scored | 2875.10 | 2874.10 | 101.622 | 0.01 | 5.64 |
| Oct | scored | 2968.94 | 2874.21 | 95.811 | 0.99 | 6.13 |
| Nov | scored | 2721.65 | 2883.69 | 95.233 | -1.70 | 3.92 |
| Dec | scored | 2943.19 | 2868.96 | 102.052 | 0.73 | 4.15 |

### Ratasasennus Oy Ab (V-0179)

Peak CUSUM 5.98 in May; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 608.81 | - | - | - | - |
| Feb | baseline-only | 650.87 | - | - | - | - |
| Mar | baseline-only | 628.87 | - | - | - | - |
| Apr | scored | 710.02 | 629.52 | 17.179 | 4.69 | 4.19 |
| May | scored | 736.71 | 649.64 | 37.900 | 2.30 | 5.98 |
| Jun | scored | 633.73 | 667.06 | 48.602 | -0.69 | 4.80 |
| Jul | scored | 560.93 | 661.50 | 46.073 | -2.18 | 2.11 |
| Aug | scored | 532.51 | 647.13 | 55.299 | -2.07 | 0.00 |
| Sep | scored | 608.31 | 632.81 | 64.131 | -0.38 | 0.00 |
| Oct | scored | 723.48 | 630.08 | 60.952 | 1.53 | 1.03 |
| Nov | scored | 601.60 | 639.42 | 64.254 | -0.59 | 0.00 |
| Dec | scored | 611.50 | 635.99 | 62.222 | -0.39 | 0.00 |

### Rautaväline Tmi (V-0075)

Peak CUSUM 5.62 in Sep; first crossed h = 4.0 in Sep.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 947.39 | - | - | - | - |
| Feb | baseline-only | 844.66 | - | - | - | - |
| Mar | baseline-only | 896.44 | - | - | - | - |
| Apr | scored | 782.93 | 896.16 | 41.938 | -2.70 | 0.00 |
| May | scored | 893.32 | 867.85 | 61.018 | 0.42 | 0.00 |
| Jun | scored | 746.72 | 872.95 | 55.518 | -2.27 | 0.00 |
| Jul | scored | 828.92 | 851.91 | 69.149 | -0.33 | 0.00 |
| Aug | scored | 1001.83 | 848.62 | 64.523 | 2.37 | 1.87 |
| Sep | scored | 1202.04 | 867.78 | 78.805 | 4.24 | 5.62 |
| Oct | scored | 683.14 | 904.92 | 128.669 | -1.72 | 3.39 |
| Nov | scored | 1045.63 | 882.74 | 139.021 | 1.17 | 4.06 |
| Dec | scored | 942.51 | 897.55 | 140.580 | 0.32 | 3.88 |

### Tarviketekniikka Oy (V-0041)

Peak CUSUM 5.59 in Apr; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 647.90 | - | - | - | - |
| Feb | baseline-only | 605.87 | - | - | - | - |
| Mar | baseline-only | 570.85 | - | - | - | - |
| Apr | scored | 800.15 | 608.21 | 31.501 | 6.09 | 5.59 |
| May | scored | 695.52 | 656.19 | 87.475 | 0.45 | 5.54 |
| Jun | scored | 691.47 | 664.06 | 79.806 | 0.34 | 5.39 |
| Jul | scored | 631.08 | 668.63 | 73.565 | -0.51 | 4.38 |
| Aug | scored | 569.84 | 663.26 | 69.364 | -1.35 | 2.53 |
| Sep | scored | 625.55 | 651.58 | 71.865 | -0.36 | 1.67 |
| Oct | scored | 649.63 | 648.69 | 68.247 | 0.01 | 1.18 |
| Nov | scored | 674.55 | 648.79 | 64.745 | 0.40 | 1.08 |
| Dec | scored | 607.18 | 651.13 | 62.175 | -0.71 | 0.00 |

### Kaapeliväline Oy (V-0184)

Peak CUSUM 5.19 in Jul; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 959.09 | - | - | - | - |
| Feb | baseline-only | 866.20 | - | - | - | - |
| Mar | baseline-only | 666.95 | - | - | - | - |
| Apr | scored | 771.26 | 830.74 | 121.871 | -0.49 | 0.00 |
| May | scored | 942.93 | 815.87 | 108.640 | 1.17 | 0.67 |
| Jun | scored | 1378.42 | 841.29 | 109.659 | 4.90 | 5.07 |
| Jul | scored | 1070.63 | 930.81 | 223.812 | 0.62 | 5.19 |
| Aug | scored | 875.52 | 950.78 | 212.908 | -0.35 | 4.34 |
| Sep | scored | 1064.07 | 941.37 | 200.707 | 0.61 | 4.45 |
| Oct | scored | 920.81 | 955.01 | 193.117 | -0.18 | 3.77 |
| Nov | scored | 1122.42 | 951.59 | 183.494 | 0.93 | 4.20 |
| Dec | scored | 879.52 | 967.12 | 181.716 | -0.48 | 3.22 |

### Turvatukku Oy (V-0140)

Peak CUSUM 5.10 in Dec; first crossed h = 4.0 in Dec.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 2098.66 | - | - | - | - |
| Feb | baseline-only | 3377.70 | - | - | - | - |
| Mar | baseline-only | 2154.01 | - | - | - | - |
| Apr | scored | 2663.78 | 2543.45 | 590.331 | 0.20 | 0.00 |
| May | scored | 2568.62 | 2573.54 | 513.890 | -0.01 | 0.00 |
| Jun | scored | 2323.34 | 2572.55 | 459.641 | -0.54 | 0.00 |
| Aug | scored | 2179.08 | 2531.02 | 429.749 | -0.82 | 0.00 |
| Sep | scored | 3882.53 | 2480.74 | 416.493 | 3.37 | 2.87 |
| Oct | scored | 2874.28 | 2655.96 | 605.563 | 0.36 | 2.73 |
| Nov | scored | 2146.42 | 2680.22 | 575.038 | -0.93 | 1.30 |
| Dec | scored | 5071.44 | 2626.84 | 568.547 | 4.30 | 5.10 |

### Myrkvarn Bergsgrossist (V-0153)

Peak CUSUM 4.98 in Jul; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 3084.70 | - | - | - | - |
| Feb | baseline-only | 2974.67 | - | - | - | - |
| Mar | baseline-only | 3230.57 | - | - | - | - |
| Apr | scored | 2938.10 | 3096.64 | 104.810 | -1.51 | 0.00 |
| May | scored | 3219.44 | 3057.01 | 113.805 | 1.43 | 0.93 |
| Jun | scored | 3292.67 | 3089.50 | 120.760 | 1.68 | 2.11 |
| Jul | scored | 3573.92 | 3123.36 | 133.738 | 3.37 | 4.98 |
| Aug | scored | 3103.58 | 3187.72 | 200.472 | -0.42 | 4.06 |
| Sep | scored | 3074.14 | 3177.21 | 189.578 | -0.54 | 3.02 |
| Oct | scored | 3307.00 | 3165.75 | 181.647 | 0.78 | 3.29 |
| Nov | scored | 3110.06 | 3179.88 | 177.459 | -0.39 | 2.40 |
| Dec | scored | 3053.61 | 3173.53 | 170.387 | -0.70 | 1.20 |

### Porttimateriaali Oy (V-0024)

Peak CUSUM 4.94 in Nov; first crossed h = 4.0 in Nov.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1835.36 | - | - | - | - |
| Feb | baseline-only | 2050.04 | - | - | - | - |
| Mar | baseline-only | 1529.66 | - | - | - | - |
| Apr | scored | 1717.70 | 1805.02 | 213.526 | -0.41 | 0.00 |
| May | scored | 1730.56 | 1783.19 | 188.745 | -0.28 | 0.00 |
| Jun | scored | 1908.19 | 1772.66 | 170.126 | 0.80 | 0.30 |
| Jul | scored | 1894.22 | 1795.25 | 163.310 | 0.61 | 0.40 |
| Aug | scored | 1987.64 | 1809.39 | 155.111 | 1.15 | 1.05 |
| Sep | scored | 1939.26 | 1831.67 | 156.612 | 0.69 | 1.24 |
| Oct | scored | 2187.96 | 1843.63 | 151.477 | 2.27 | 3.01 |
| Nov | scored | 2306.95 | 1878.06 | 176.979 | 2.42 | 4.94 |
| Dec | scored | 1557.66 | 1917.05 | 208.989 | -1.72 | 2.72 |

### Palkkijärjestelmä Ky (V-0139)

Peak CUSUM 4.81 in Sep; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 551.20 | - | - | - | - |
| Feb | baseline-only | 633.03 | - | - | - | - |
| Mar | baseline-only | 650.19 | - | - | - | - |
| Apr | scored | 584.74 | 611.48 | 43.192 | -0.62 | 0.00 |
| May | scored | 586.20 | 604.79 | 39.157 | -0.47 | 0.00 |
| Jun | scored | 616.86 | 601.07 | 35.803 | 0.44 | 0.00 |
| Jul | scored | 648.75 | 603.70 | 33.209 | 1.36 | 0.86 |
| Aug | scored | 739.25 | 610.14 | 34.551 | 3.74 | 4.09 |
| Sep | scored | 691.38 | 626.28 | 53.551 | 1.22 | 4.81 |
| Oct | scored | 592.31 | 633.51 | 54.476 | -0.76 | 3.55 |
| Nov | scored | 667.68 | 629.39 | 53.138 | 0.72 | 3.77 |
| Dec | scored | 644.14 | 632.87 | 51.847 | 0.22 | 3.49 |

### Kiskoväline Oy Ab (V-0074)

Peak CUSUM 4.79 in Sep; first crossed h = 4.0 in Sep.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 625.63 | - | - | - | - |
| Feb | baseline-only | 640.43 | - | - | - | - |
| Mar | baseline-only | 684.73 | - | - | - | - |
| Apr | scored | 650.51 | 650.26 | 25.109 | 0.01 | 0.00 |
| May | scored | 645.16 | 650.32 | 21.745 | -0.24 | 0.00 |
| Jun | scored | 663.84 | 649.29 | 19.559 | 0.74 | 0.24 |
| Jul | scored | 694.91 | 651.72 | 18.660 | 2.31 | 2.06 |
| Aug | scored | 686.09 | 657.89 | 22.955 | 1.23 | 2.79 |
| Sep | scored | 720.11 | 661.41 | 23.410 | 2.51 | 4.79 |
| Oct | scored | 637.46 | 667.93 | 28.765 | -1.06 | 3.24 |
| Nov | scored | 671.68 | 664.89 | 28.779 | 0.24 | 2.97 |
| Dec | scored | 620.78 | 665.50 | 27.509 | -1.63 | 0.85 |

### Vasaratarvike Oy Ab (V-0055)

Peak CUSUM 4.68 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 661.19 | - | - | - | - |
| Feb | baseline-only | 685.67 | - | - | - | - |
| Mar | baseline-only | 504.67 | - | - | - | - |
| Apr | scored | 675.60 | 617.18 | 80.180 | 0.73 | 0.23 |
| May | scored | 997.86 | 631.78 | 73.902 | 4.95 | 4.68 |
| Jun | scored | 750.53 | 705.00 | 160.660 | 0.28 | 4.47 |
| Jul | scored | 388.32 | 712.58 | 147.640 | -2.20 | 1.77 |
| Aug | scored | 389.98 | 666.26 | 177.648 | -1.56 | 0.00 |
| Sep | scored | 527.48 | 631.73 | 189.639 | -0.55 | 0.00 |
| Oct | scored | 603.72 | 620.14 | 181.770 | -0.09 | 0.00 |
| Nov | scored | 768.35 | 618.50 | 172.513 | 0.87 | 0.37 |
| Dec | scored | 609.68 | 632.12 | 170.032 | -0.13 | 0.00 |

### Akselikomponentti Oy (V-0183)

Peak CUSUM 4.68 in Sep; first crossed h = 4.0 in Sep.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 3224.35 | - | - | - | - |
| Feb | baseline-only | 2883.81 | - | - | - | - |
| Mar | baseline-only | 2997.19 | - | - | - | - |
| Apr | scored | 2830.60 | 3035.12 | 141.587 | -1.44 | 0.00 |
| May | scored | 2892.67 | 2983.99 | 151.254 | -0.60 | 0.00 |
| Jun | scored | 3291.81 | 2965.73 | 140.131 | 2.33 | 1.83 |
| Jul | scored | 3158.88 | 3020.07 | 176.442 | 0.79 | 2.11 |
| Aug | scored | 3439.71 | 3039.90 | 170.422 | 2.35 | 3.96 |
| Sep | scored | 3341.90 | 3089.88 | 207.114 | 1.22 | 4.68 |
| Oct | scored | 3199.18 | 3117.88 | 210.720 | 0.39 | 4.56 |
| Nov | scored | 3078.00 | 3126.01 | 201.389 | -0.24 | 3.82 |
| Dec | scored | 3161.31 | 3121.65 | 192.512 | 0.21 | 3.53 |

### Ratastukku Oy Ab (V-0125)

Peak CUSUM 4.47 in Oct; first crossed h = 4.0 in Oct.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 810.89 | - | - | - | - |
| Feb | baseline-only | 1145.70 | - | - | - | - |
| Mar | baseline-only | 963.96 | - | - | - | - |
| Apr | scored | 957.32 | 973.52 | 136.854 | -0.12 | 0.00 |
| May | scored | 953.71 | 969.47 | 118.727 | -0.13 | 0.00 |
| Jun | scored | 696.20 | 966.32 | 106.379 | -2.54 | 0.00 |
| Jul | scored | 757.80 | 921.30 | 139.871 | -1.17 | 0.00 |
| Aug | scored | 1174.76 | 897.94 | 141.570 | 1.96 | 1.46 |
| Sep | scored | 1204.58 | 932.54 | 160.991 | 1.69 | 2.65 |
| Oct | scored | 1367.08 | 962.77 | 174.205 | 2.32 | 4.47 |
| Nov | scored | 737.47 | 1003.20 | 204.999 | -1.30 | 2.67 |
| Dec | scored | 1106.17 | 979.04 | 209.857 | 0.61 | 2.78 |

### Hällsvik Malmgrossist (V-0066)

Peak CUSUM 4.41 in Jun; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 691.80 | - | - | - | - |
| Feb | baseline-only | 637.03 | - | - | - | - |
| Mar | baseline-only | 542.26 | - | - | - | - |
| Apr | scored | 614.00 | 623.69 | 61.771 | -0.16 | 0.00 |
| May | scored | 631.95 | 621.27 | 53.660 | 0.20 | 0.00 |
| Jun | scored | 860.08 | 623.41 | 48.184 | 4.91 | 4.41 |
| Aug | scored | 697.52 | 662.85 | 98.562 | 0.35 | 4.26 |
| Sep | scored | 581.81 | 667.80 | 92.054 | -0.93 | 2.83 |
| Oct | scored | 587.37 | 657.06 | 90.684 | -0.77 | 1.56 |
| Nov | scored | 411.95 | 649.31 | 88.258 | -2.69 | 0.00 |
| Dec | scored | 680.31 | 625.58 | 109.914 | 0.50 | 0.00 |

### Koteloväline Tmi (V-0123)

Peak CUSUM 4.38 in Nov; first crossed h = 4.0 in Oct.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 668.12 | - | - | - | - |
| Feb | baseline-only | 670.59 | - | - | - | - |
| Mar | baseline-only | 596.19 | - | - | - | - |
| Apr | scored | 585.79 | 644.97 | 34.506 | -1.72 | 0.00 |
| May | scored | 589.58 | 630.17 | 39.365 | -1.03 | 0.00 |
| Jun | scored | 736.76 | 622.05 | 38.772 | 2.96 | 2.46 |
| Jul | scored | 609.46 | 641.17 | 55.498 | -0.57 | 1.39 |
| Aug | scored | 675.98 | 636.64 | 52.566 | 0.75 | 1.64 |
| Sep | scored | 765.15 | 641.56 | 50.863 | 2.43 | 3.57 |
| Oct | scored | 725.62 | 655.29 | 61.711 | 1.14 | 4.20 |
| Nov | scored | 704.41 | 662.32 | 62.229 | 0.68 | 4.38 |
| Dec | scored | 683.24 | 666.15 | 60.554 | 0.28 | 4.16 |

### Muovivaraosa Oy Ab (V-0039)

Peak CUSUM 4.35 in Sep; first crossed h = 4.0 in Sep.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 645.87 | - | - | - | - |
| Feb | baseline-only | 577.38 | - | - | - | - |
| Mar | baseline-only | 614.77 | - | - | - | - |
| Apr | scored | 639.38 | 612.68 | 28.001 | 0.95 | 0.45 |
| May | scored | 668.12 | 619.35 | 26.866 | 1.82 | 1.77 |
| Jun | scored | 615.79 | 629.11 | 30.951 | -0.43 | 0.84 |
| Jul | scored | 690.03 | 626.89 | 28.687 | 2.20 | 2.54 |
| Aug | scored | 659.05 | 635.91 | 34.550 | 0.67 | 2.71 |
| Sep | scored | 709.94 | 638.80 | 33.212 | 2.14 | 4.35 |
| Oct | scored | 624.20 | 646.70 | 38.474 | -0.58 | 3.27 |
| Nov | scored | 637.36 | 644.45 | 37.119 | -0.19 | 2.58 |
| Dec | scored | 679.78 | 643.81 | 35.450 | 1.01 | 3.09 |

### Kiskoasennus Ky (V-0119)

Peak CUSUM 4.28 in Jun; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 3110.65 | - | - | - | - |
| Feb | baseline-only | 3170.93 | - | - | - | - |
| Mar | baseline-only | 3077.73 | - | - | - | - |
| Apr | scored | 3242.98 | 3119.77 | 38.591 | 3.19 | 2.69 |
| May | scored | 3116.08 | 3150.58 | 62.955 | -0.55 | 1.64 |
| Jun | scored | 3325.58 | 3143.68 | 57.975 | 3.14 | 4.28 |
| Jul | scored | 3082.32 | 3173.99 | 86.004 | -1.07 | 2.72 |
| Aug | scored | 2916.07 | 3160.90 | 85.843 | -2.85 | 0.00 |
| Sep | scored | 3476.14 | 3130.29 | 114.035 | 3.03 | 2.53 |
| Oct | scored | 3269.09 | 3168.72 | 152.880 | 0.66 | 2.69 |
| Nov | scored | 3179.12 | 3178.76 | 148.128 | 0.00 | 2.19 |
| Dec | scored | 3213.79 | 3178.79 | 141.234 | 0.25 | 1.94 |

### Kulmavaraosa Ky (V-0172)

Peak CUSUM 4.10 in Jul; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1754.93 | - | - | - | - |
| Feb | baseline-only | 1607.41 | - | - | - | - |
| Mar | baseline-only | 1954.59 | - | - | - | - |
| Apr | scored | 1897.73 | 1772.31 | 142.266 | 0.88 | 0.38 |
| May | scored | 1864.59 | 1803.67 | 134.645 | 0.45 | 0.33 |
| Jun | scored | 2163.50 | 1815.85 | 122.871 | 2.83 | 2.66 |
| Jul | scored | 2205.93 | 1873.79 | 171.368 | 1.94 | 4.10 |
| Aug | scored | 1896.49 | 1921.24 | 196.671 | -0.13 | 3.48 |
| Sep | scored | 2023.94 | 1918.15 | 184.151 | 0.57 | 3.55 |
| Oct | scored | 1789.05 | 1929.90 | 176.774 | -0.80 | 2.25 |
| Nov | scored | 2127.61 | 1915.81 | 172.944 | 1.22 | 2.98 |
| Dec | scored | 2006.86 | 1935.07 | 175.778 | 0.41 | 2.89 |

### Ruuvimateriaali Oy Ab (V-0082)

Peak CUSUM 4.08 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1699.93 | - | - | - | - |
| Feb | baseline-only | 1621.62 | - | - | - | - |
| Mar | baseline-only | 1800.38 | - | - | - | - |
| Apr | scored | 1931.11 | 1707.31 | 73.166 | 3.06 | 2.56 |
| May | scored | 1997.68 | 1763.26 | 115.785 | 2.02 | 4.08 |
| Jun | scored | 1409.30 | 1810.14 | 139.704 | -2.87 | 0.71 |
| Jul | scored | 1754.19 | 1743.34 | 196.418 | 0.06 | 0.27 |
| Aug | scored | 1666.97 | 1744.89 | 181.888 | -0.43 | 0.00 |
| Sep | scored | 1971.46 | 1735.15 | 172.080 | 1.37 | 0.87 |
| Oct | scored | 1865.48 | 1761.41 | 178.429 | 0.58 | 0.96 |
| Nov | scored | 1695.16 | 1771.81 | 172.128 | -0.45 | 0.01 |
| Dec | scored | 1477.00 | 1764.84 | 165.591 | -1.74 | 0.00 |

### Porttivaraosa Tmi (V-0086)

Peak CUSUM 4.04 in Sep; first crossed h = 4.0 in Sep.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 957.41 | - | - | - | - |
| Feb | baseline-only | 894.01 | - | - | - | - |
| Mar | baseline-only | 857.05 | - | - | - | - |
| Apr | scored | 1003.80 | 902.83 | 41.445 | 2.44 | 1.94 |
| May | scored | 899.47 | 928.07 | 56.569 | -0.51 | 0.93 |
| Jun | scored | 1009.82 | 922.35 | 51.874 | 1.69 | 2.12 |
| Jul | scored | 1007.45 | 936.93 | 57.489 | 1.23 | 2.84 |
| Aug | scored | 1011.54 | 947.00 | 58.667 | 1.10 | 3.44 |
| Sep | scored | 1019.75 | 955.07 | 58.883 | 1.10 | 4.04 |
| Oct | scored | 924.62 | 962.26 | 59.120 | -0.64 | 2.91 |
| Nov | scored | 940.56 | 958.49 | 57.211 | -0.31 | 2.09 |
| Dec | scored | 774.82 | 956.86 | 54.792 | -3.32 | 0.00 |

### Kumipalvelu Oy Ab (V-0078)

Peak CUSUM 4.03 in Jul; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 3187.86 | - | - | - | - |
| Feb | baseline-only | 2868.33 | - | - | - | - |
| Mar | baseline-only | 3252.31 | - | - | - | - |
| Apr | scored | 3384.46 | 3102.83 | 167.895 | 1.68 | 1.18 |
| May | scored | 3068.64 | 3173.24 | 189.772 | -0.55 | 0.13 |
| Jun | scored | 3631.95 | 3152.32 | 174.818 | 2.74 | 2.37 |
| Jul | scored | 3749.72 | 3232.26 | 239.622 | 2.16 | 4.03 |
| Aug | scored | 3285.79 | 3306.18 | 286.364 | -0.07 | 3.46 |
| Sep | scored | 2913.17 | 3303.63 | 267.953 | -1.46 | 1.50 |
| Oct | scored | 3308.17 | 3260.25 | 280.854 | 0.17 | 1.17 |
| Nov | scored | 3756.33 | 3265.04 | 266.829 | 1.84 | 2.51 |
| Dec | scored | 3104.39 | 3309.70 | 290.987 | -0.71 | 1.31 |

### Turvahuolto Tmi (V-0047)

Peak CUSUM 4.03 in Dec; first crossed h = 4.0 in Dec.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1807.78 | - | - | - | - |
| Feb | baseline-only | 1696.09 | - | - | - | - |
| Mar | baseline-only | 1982.21 | - | - | - | - |
| Apr | scored | 1674.40 | 1828.69 | 117.740 | -1.31 | 0.00 |
| May | scored | 1736.50 | 1790.12 | 121.905 | -0.44 | 0.00 |
| Jun | scored | 1940.71 | 1779.39 | 111.125 | 1.45 | 0.95 |
| Jul | scored | 1625.69 | 1806.28 | 117.919 | -1.53 | 0.00 |
| Aug | scored | 1438.51 | 1780.48 | 126.143 | -2.71 | 0.00 |
| Sep | scored | 2123.26 | 1737.73 | 163.443 | 2.36 | 1.86 |
| Oct | scored | 1793.12 | 1780.57 | 196.023 | 0.06 | 1.42 |
| Nov | scored | 2258.86 | 1781.82 | 186.002 | 2.56 | 3.49 |
| Dec | scored | 2057.94 | 1825.19 | 224.185 | 1.04 | 4.03 |

### Tarvikemateriaali Tmi (V-0143)

Peak CUSUM 4.02 in Oct; first crossed h = 4.0 in Oct.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1848.94 | - | - | - | - |
| Feb | baseline-only | 1968.62 | - | - | - | - |
| Mar | baseline-only | 1907.76 | - | - | - | - |
| Apr | scored | 1595.89 | 1908.44 | 48.863 | -6.40 | 0.00 |
| May | scored | 2082.44 | 1830.30 | 141.799 | 1.78 | 1.28 |
| Jun | scored | 1758.11 | 1880.73 | 162.040 | -0.76 | 0.02 |
| Jul | scored | 1255.23 | 1860.29 | 154.819 | -3.91 | 0.00 |
| Aug | scored | 1991.27 | 1773.86 | 255.682 | 0.85 | 0.35 |
| Sep | scored | 1950.11 | 1801.03 | 249.743 | 0.60 | 0.45 |
| Oct | scored | 2795.81 | 1817.60 | 240.076 | 4.07 | 4.02 |
| Nov | scored | 1951.67 | 1915.42 | 371.475 | 0.10 | 3.62 |
| Dec | scored | 1863.48 | 1918.71 | 354.340 | -0.16 | 2.96 |

## Not scoreable (23 vendors)

These vendors never reached 3 invoices in enough calendar months to build a baseline and score at least one month -- out of scope for this method, not a negative finding.

| Vendor ID | Vendor name | Total invoices | Months with >= 3 invoices |
|---|---|---|---|
| V-0001 | Teräskontio Oy | 24 | 0 |
| V-0002 | Kuormaraitti Oy | 24 | 0 |
| V-0077 | Siltavaraosa Tmi | 17 | 0 |
| V-0128 | Myrkvarn Sjoteknik | 15 | 0 |
| V-0007 | Neuvantila Oy | 12 | 0 |
| V-0016 | Kiinteistö Oy Vantaan Teollisuustalo | 12 | 0 |
| V-0003 | Kärrenbach Dichtungstechnik GmbH | 7 | 0 |
| V-0091 | Turvalogistiikka Oy Ab | 7 | 0 |
| V-0200 | Kantamateriaali Ky | 7 | 0 |
| V-0011 | Säiliöpalvelu Oy Ab | 6 | 0 |
| V-0004 | Kaerrenbach Dichtungstechnik GmbH | 5 | 0 |
| V-0008 | Pulttitarvike Tmi | 4 | 0 |
| V-0009 | Poralogistiikka Tmi | 4 | 0 |
| V-0010 | Kumipalvelu Tmi | 4 | 0 |
| V-0012 | Ratashuolto Oy | 4 | 0 |
| V-0013 | Kantamateriaali Tmi | 4 | 0 |
| V-0014 | Verkkokomponentti Oy Ab | 4 | 0 |
| V-0005 | KARRENBACH DICHTUNGSTECHNIK GMBH | 3 | 0 |
| V-0015 | Kairakomponentti Oy Ab | 2 | 0 |
| V-0017 | Varastopalvelu Toivanen Ky | 2 | 0 |
| ... | (3 more) | | |

