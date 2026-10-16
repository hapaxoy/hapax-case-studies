# Vendor drift review -- Saarnitukku Oy FY2026

Source ledger: `data/06b/gl_transactions_06b.csv`

Method: per-vendor, per-month volume-weighted unit price (falling back to invoice-level totals where no item granularity exists); expanding prior-months baseline (minimum 3 months of history, minimum 3 invoices to score a month); one-sided CUSUM of standardised monthly deviations (k = 0.5); flagged at CUSUM > h = 4.0. Deterministic, no machine learning. Parameters fixed before any 06b data existed and never tuned against this ledger's output.

**200 vendors in the ledger; 195 scoreable (cleared the 3-invoices/month floor in at least 4 months); 5 not scoreable at all.**

## Ranked table (top 25 of 195 scoreable vendors, by peak CUSUM)

| Rank | Vendor ID | Vendor name | Peak CUSUM | Peak month | Flagged | First crossing month |
|---|---|---|---|---|---|---|
| 1 | V-0005 | Virtakanki Oy | 32.71 | Dec | **YES** | Aug |
| 2 | V-0001 | Louhimalmi Oy | 26.79 | Dec | **YES** | May |
| 3 | V-0003 | Rantavalssi Oy | 26.76 | Dec | **YES** | May |
| 4 | V-0128 | Kanervamateriaali Oy | 15.11 | Jun | **YES** | Apr |
| 5 | V-0002 | Ahoharkko Oy | 11.49 | Dec | **YES** | Jul |
| 6 | V-0053 | Vaahteraasennus Oy | 10.34 | May | **YES** | May |
| 7 | V-0008 | Saaritarvike Oy | 8.82 | May | **YES** | Apr |
| 8 | V-0032 | Harjutekniikka Oy Ab | 8.27 | Oct | **YES** | Apr |
| 9 | V-0137 | Louhimateriaali Ky | 8.17 | Jul | **YES** | Jun |
| 10 | V-0077 | Metsähuolto Oy Ab | 7.85 | May | **YES** | Apr |
| 11 | V-0122 | Saraaihio Oy | 7.65 | Dec | **YES** | May |
| 12 | V-0085 | Mannerjärjestelmä Oy | 7.28 | Jun | **YES** | May |
| 13 | V-0031 | Kanervatarvike Oy | 6.99 | Oct | **YES** | Aug |
| 14 | V-0106 | Vaahteralogistiikka Ky | 6.87 | Aug | **YES** | Aug |
| 15 | V-0131 | Kiviasennus Oy | 6.83 | Sep | **YES** | Aug |
| 16 | V-0030 | Metsäharkko Tmi | 6.82 | Aug | **YES** | Aug |
| 17 | V-0015 | Niittyaihio Oy | 6.69 | May | **YES** | Apr |
| 18 | V-0105 | Koskiaihio Oy | 6.50 | Oct | **YES** | Sep |
| 19 | V-0039 | Rinnekomponentti Ky | 6.30 | Jun | **YES** | May |
| 20 | V-0057 | Vaahterajärjestelmä Oy Ab | 6.01 | Aug | **YES** | Jul |
| 21 | V-0157 | Niittykomponentti Tmi | 5.99 | Apr | **YES** | Apr |
| 22 | V-0020 | Kantologistiikka Oy | 5.64 | Apr | **YES** | Apr |
| 23 | V-0119 | Virtakomponentti Tmi | 5.50 | Jun | **YES** | Jun |
| 24 | V-0040 | Kuusamoväline Tmi | 5.39 | Sep | **YES** | Sep |
| 25 | V-0064 | Lehtotukku Oy Ab | 5.39 | May | **YES** | May |

## Flagged vendors (47) -- trajectory detail

### Virtakanki Oy (V-0005)

Peak CUSUM 32.71 in Dec; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 99.79 | - | - | - | - |
| Feb | baseline-only | 100.01 | - | - | - | - |
| Mar | baseline-only | 100.34 | - | - | - | - |
| Apr | scored | 99.96 | 100.05 | 0.229 | -0.36 | 0.00 |
| May | scored | 99.24 | 100.02 | 0.202 | -3.90 | 0.00 |
| Jun | scored | 100.10 | 99.87 | 0.363 | 0.64 | 0.14 |
| Jul | scored | 99.70 | 99.91 | 0.342 | -0.60 | 0.00 |
| Aug | scored | 108.93 | 99.88 | 0.325 | 27.84 | 27.34 |
| Sep | scored | 110.59 | 101.01 | 3.008 | 3.19 | 30.03 |
| Oct | scored | 108.38 | 102.07 | 4.136 | 1.52 | 31.05 |
| Nov | scored | 108.14 | 102.70 | 4.356 | 1.25 | 31.80 |
| Dec | scored | 109.43 | 103.20 | 4.438 | 1.40 | 32.71 |

### Louhimalmi Oy (V-0001)

Peak CUSUM 26.79 in Dec; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 80.19 | - | - | - | - |
| Feb | baseline-only | 80.16 | - | - | - | - |
| Mar | baseline-only | 80.91 | - | - | - | - |
| Apr | scored | 80.38 | 80.42 | 0.343 | -0.12 | 0.00 |
| May | scored | 84.59 | 80.41 | 0.298 | 14.03 | 13.53 |
| Jun | scored | 85.73 | 81.25 | 1.691 | 2.65 | 15.68 |
| Jul | scored | 89.24 | 81.99 | 2.275 | 3.18 | 18.36 |
| Aug | scored | 91.86 | 83.03 | 3.295 | 2.68 | 20.54 |
| Sep | scored | 91.26 | 84.13 | 4.247 | 1.68 | 21.72 |
| Oct | scored | 95.43 | 84.92 | 4.589 | 2.29 | 23.51 |
| Nov | scored | 96.55 | 85.98 | 5.375 | 1.97 | 24.98 |
| Dec | scored | 100.69 | 86.94 | 5.958 | 2.31 | 26.79 |

### Rantavalssi Oy (V-0003)

Peak CUSUM 26.76 in Dec; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 149.66 | - | - | - | - |
| Feb | baseline-only | 149.29 | - | - | - | - |
| Mar | baseline-only | 150.14 | - | - | - | - |
| Apr | scored | 149.51 | 149.70 | 0.350 | -0.52 | 0.00 |
| May | scored | 152.12 | 149.65 | 0.313 | 7.90 | 7.40 |
| Jun | scored | 159.56 | 150.14 | 1.028 | 9.16 | 16.06 |
| Jul | scored | 159.59 | 151.71 | 3.633 | 2.17 | 17.73 |
| Aug | scored | 162.62 | 152.84 | 4.349 | 2.25 | 19.48 |
| Sep | scored | 167.69 | 154.06 | 5.197 | 2.62 | 21.60 |
| Oct | scored | 173.51 | 155.58 | 6.508 | 2.76 | 23.86 |
| Nov | scored | 174.80 | 157.37 | 8.189 | 2.13 | 25.49 |
| Dec | scored | 175.36 | 158.95 | 9.277 | 1.77 | 26.76 |

### Kanervamateriaali Oy (V-0128)

Peak CUSUM 15.11 in Jun; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.24 | - | - | - | - |
| Feb | baseline-only | 24.36 | - | - | - | - |
| Mar | baseline-only | 24.37 | - | - | - | - |
| Apr | scored | 25.01 | 24.32 | 0.058 | 11.93 | 11.43 |
| May | scored | 25.02 | 24.49 | 0.302 | 1.73 | 12.66 |
| Jun | scored | 25.60 | 24.60 | 0.341 | 2.95 | 15.11 |
| Jul | scored | 23.83 | 24.77 | 0.487 | -1.93 | 12.68 |
| Aug | scored | 25.52 | 24.63 | 0.558 | 1.59 | 13.78 |
| Sep | scored | 24.97 | 24.74 | 0.599 | 0.38 | 13.65 |
| Oct | scored | 24.96 | 24.77 | 0.569 | 0.34 | 13.49 |
| Nov | scored | 24.97 | 24.79 | 0.543 | 0.34 | 13.33 |
| Dec | scored | 25.12 | 24.80 | 0.520 | 0.61 | 13.44 |

### Ahoharkko Oy (V-0002)

Peak CUSUM 11.49 in Dec; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 59.31 | - | - | - | - |
| Feb | baseline-only | 61.41 | - | - | - | - |
| Mar | baseline-only | 60.98 | - | - | - | - |
| Apr | scored | 61.90 | 60.57 | 0.906 | 1.47 | 0.97 |
| May | scored | 63.19 | 60.90 | 0.974 | 2.35 | 2.82 |
| Jun | scored | 62.15 | 61.36 | 1.264 | 0.63 | 2.95 |
| Jul | scored | 64.46 | 61.49 | 1.191 | 2.49 | 4.94 |
| Aug | scored | 64.91 | 61.91 | 1.516 | 1.98 | 6.42 |
| Sep | scored | 66.15 | 62.29 | 1.730 | 2.23 | 8.15 |
| Oct | scored | 65.95 | 62.72 | 2.033 | 1.59 | 9.24 |
| Nov | scored | 65.74 | 63.04 | 2.159 | 1.25 | 9.99 |
| Dec | scored | 67.68 | 63.29 | 2.199 | 2.00 | 11.49 |

### Vaahteraasennus Oy (V-0053)

Peak CUSUM 10.34 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 776.77 | - | - | - | - |
| Feb | baseline-only | 789.69 | - | - | - | - |
| Mar | baseline-only | 849.43 | - | - | - | - |
| Apr | scored | 808.59 | 805.30 | 31.651 | 0.10 | 0.00 |
| May | scored | 1103.70 | 806.12 | 27.448 | 10.84 | 10.34 |
| Jun | scored | 828.37 | 865.64 | 121.535 | -0.31 | 9.53 |
| Jul | scored | 573.77 | 859.43 | 111.812 | -2.55 | 6.48 |
| Aug | scored | 924.23 | 818.62 | 143.901 | 0.73 | 6.71 |
| Sep | scored | 1076.17 | 831.82 | 139.065 | 1.76 | 7.97 |
| Oct | scored | 978.40 | 858.97 | 151.946 | 0.79 | 8.26 |
| Nov | scored | 802.41 | 870.91 | 148.534 | -0.46 | 7.30 |
| Dec | scored | 1131.01 | 864.69 | 142.984 | 1.86 | 8.66 |

### Saaritarvike Oy (V-0008)

Peak CUSUM 8.82 in May; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 2395.80 | - | - | - | - |
| Feb | baseline-only | 2119.87 | - | - | - | - |
| Mar | baseline-only | 2556.21 | - | - | - | - |
| Apr | scored | 3896.17 | 2357.29 | 180.202 | 8.54 | 8.04 |
| May | scored | 3617.52 | 2742.01 | 684.386 | 1.28 | 8.82 |
| Jun | scored | 2617.35 | 2917.12 | 705.229 | -0.43 | 7.89 |
| Jul | scored | 1931.67 | 2867.15 | 653.405 | -1.43 | 5.96 |
| Aug | scored | 2007.95 | 2733.51 | 687.827 | -1.05 | 4.41 |
| Sep | scored | 1864.40 | 2642.82 | 686.693 | -1.13 | 2.77 |
| Oct | scored | 3324.95 | 2556.33 | 692.097 | 1.11 | 3.38 |
| Nov | scored | 2612.22 | 2633.19 | 695.894 | -0.03 | 2.85 |
| Dec | scored | 2440.83 | 2631.28 | 663.536 | -0.29 | 2.07 |

### Harjutekniikka Oy Ab (V-0032)

Peak CUSUM 8.27 in Oct; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.52 | - | - | - | - |
| Feb | baseline-only | 24.13 | - | - | - | - |
| Mar | baseline-only | 24.34 | - | - | - | - |
| Apr | scored | 25.29 | 24.33 | 0.161 | 5.97 | 5.47 |
| May | scored | 24.83 | 24.57 | 0.439 | 0.58 | 5.55 |
| Jun | scored | 24.70 | 24.62 | 0.405 | 0.20 | 5.25 |
| Jul | scored | 25.13 | 24.63 | 0.371 | 1.35 | 6.10 |
| Aug | scored | 25.48 | 24.71 | 0.386 | 2.00 | 7.60 |
| Sep | scored | 25.07 | 24.80 | 0.442 | 0.61 | 7.70 |
| Oct | scored | 25.29 | 24.83 | 0.425 | 1.07 | 8.27 |
| Nov | scored | 24.53 | 24.88 | 0.426 | -0.82 | 6.96 |
| Dec | scored | 24.61 | 24.85 | 0.418 | -0.55 | 5.90 |

### Louhimateriaali Ky (V-0137)

Peak CUSUM 8.17 in Jul; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1743.45 | - | - | - | - |
| Mar | baseline-only | 1385.53 | - | - | - | - |
| Apr | baseline-only | 1222.45 | - | - | - | - |
| Jun | scored | 2773.20 | 1450.48 | 217.599 | 6.08 | 5.58 |
| Jul | scored | 3645.56 | 1781.16 | 602.960 | 3.09 | 8.17 |
| Aug | scored | 1109.79 | 2154.04 | 920.331 | -1.13 | 6.54 |
| Sep | scored | 2116.87 | 1980.00 | 925.902 | 0.15 | 6.18 |
| Nov | scored | 2177.07 | 1999.55 | 858.556 | 0.21 | 5.89 |
| Dec | scored | 1936.17 | 2021.74 | 805.249 | -0.11 | 5.28 |

### Metsähuolto Oy Ab (V-0077)

Peak CUSUM 7.85 in May; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 972.63 | - | - | - | - |
| Feb | baseline-only | 1019.40 | - | - | - | - |
| Mar | baseline-only | 996.27 | - | - | - | - |
| Apr | scored | 1143.24 | 996.10 | 19.097 | 7.71 | 7.21 |
| May | scored | 1108.26 | 1032.89 | 65.827 | 1.15 | 7.85 |
| Jun | scored | 785.80 | 1047.96 | 66.148 | -3.96 | 3.39 |
| Jul | scored | 937.23 | 1004.27 | 114.856 | -0.58 | 2.30 |
| Aug | scored | 726.12 | 994.69 | 108.893 | -2.47 | 0.00 |
| Sep | scored | 946.88 | 961.12 | 135.146 | -0.11 | 0.00 |
| Oct | scored | 984.77 | 959.54 | 127.495 | 0.20 | 0.00 |
| Nov | scored | 946.69 | 962.06 | 121.189 | -0.13 | 0.00 |
| Dec | scored | 1046.13 | 960.66 | 115.634 | 0.74 | 0.24 |

### Saraaihio Oy (V-0122)

Peak CUSUM 7.65 in Dec; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Feb | baseline-only | 107.89 | - | - | - | - |
| Mar | baseline-only | 107.23 | - | - | - | - |
| Apr | baseline-only | 105.42 | - | - | - | - |
| May | scored | 111.91 | 106.84 | 1.042 | 4.86 | 4.36 |
| Jun | scored | 111.89 | 108.11 | 2.372 | 1.59 | 5.45 |
| Sep | scored | 108.12 | 108.87 | 2.606 | -0.29 | 4.67 |
| Oct | scored | 108.71 | 108.74 | 2.395 | -0.01 | 4.15 |
| Dec | scored | 117.59 | 108.74 | 2.217 | 3.99 | 7.65 |

### Mannerjärjestelmä Oy (V-0085)

Peak CUSUM 7.28 in Jun; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.90 | - | - | - | - |
| Feb | baseline-only | 24.88 | - | - | - | - |
| Mar | baseline-only | 24.72 | - | - | - | - |
| Apr | scored | 25.02 | 24.83 | 0.078 | 2.42 | 1.92 |
| May | scored | 25.41 | 24.88 | 0.106 | 4.98 | 6.41 |
| Jun | scored | 25.30 | 24.99 | 0.231 | 1.37 | 7.28 |
| Jul | scored | 24.75 | 25.04 | 0.242 | -1.18 | 5.59 |
| Aug | scored | 25.44 | 25.00 | 0.246 | 1.79 | 6.88 |
| Sep | scored | 24.94 | 25.05 | 0.272 | -0.43 | 5.95 |
| Oct | scored | 24.81 | 25.04 | 0.259 | -0.89 | 4.56 |
| Nov | scored | 25.32 | 25.02 | 0.255 | 1.19 | 5.25 |
| Dec | scored | 24.80 | 25.04 | 0.258 | -0.95 | 3.80 |

### Kanervatarvike Oy (V-0031)

Peak CUSUM 6.99 in Oct; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1707.96 | - | - | - | - |
| Feb | baseline-only | 1804.67 | - | - | - | - |
| Mar | baseline-only | 1431.60 | - | - | - | - |
| Apr | scored | 1812.48 | 1648.08 | 158.084 | 1.04 | 0.54 |
| May | scored | 2143.50 | 1689.18 | 154.307 | 2.94 | 2.98 |
| Jun | scored | 2018.27 | 1780.04 | 228.198 | 1.04 | 3.53 |
| Jul | scored | 1865.16 | 1819.75 | 226.445 | 0.20 | 3.23 |
| Aug | scored | 2428.94 | 1826.24 | 210.249 | 2.87 | 5.60 |
| Sep | scored | 2006.27 | 1901.57 | 280.017 | 0.37 | 5.47 |
| Oct | scored | 2451.11 | 1913.21 | 266.045 | 2.02 | 6.99 |
| Nov | scored | 1898.97 | 1967.00 | 299.570 | -0.23 | 6.26 |
| Dec | scored | 2030.48 | 1960.81 | 286.298 | 0.24 | 6.01 |

### Vaahteralogistiikka Ky (V-0106)

Peak CUSUM 6.87 in Aug; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1979.24 | - | - | - | - |
| Feb | baseline-only | 1791.81 | - | - | - | - |
| Mar | baseline-only | 2049.00 | - | - | - | - |
| Apr | scored | 2021.66 | 1940.02 | 108.601 | 0.75 | 0.25 |
| May | scored | 1731.42 | 1960.43 | 100.477 | -2.28 | 0.00 |
| Jun | scored | 2120.32 | 1914.63 | 128.325 | 1.60 | 1.10 |
| Jul | scored | 1868.02 | 1948.91 | 139.996 | -0.58 | 0.03 |
| Aug | scored | 2911.91 | 1937.35 | 132.666 | 7.35 | 6.87 |
| Oct | scored | 1840.39 | 2059.17 | 345.371 | -0.63 | 5.74 |
| Nov | scored | 2577.33 | 2034.87 | 332.798 | 1.63 | 6.87 |
| Dec | scored | 1625.23 | 2089.11 | 355.195 | -1.31 | 5.06 |

### Kiviasennus Oy (V-0131)

Peak CUSUM 6.83 in Sep; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.53 | - | - | - | - |
| Feb | baseline-only | 24.92 | - | - | - | - |
| Mar | baseline-only | 24.74 | - | - | - | - |
| Apr | scored | 25.08 | 24.73 | 0.161 | 2.20 | 1.70 |
| May | scored | 24.78 | 24.82 | 0.208 | -0.20 | 1.00 |
| Jun | scored | 24.97 | 24.81 | 0.187 | 0.86 | 1.37 |
| Jul | scored | 25.37 | 24.84 | 0.181 | 2.98 | 3.85 |
| Aug | scored | 25.46 | 24.91 | 0.252 | 2.18 | 5.52 |
| Sep | scored | 25.52 | 24.98 | 0.297 | 1.81 | 6.83 |
| Oct | scored | 25.05 | 25.04 | 0.327 | 0.03 | 6.36 |
| Nov | scored | 24.92 | 25.04 | 0.311 | -0.38 | 5.48 |
| Dec | scored | 24.57 | 25.03 | 0.298 | -1.55 | 3.43 |

### Metsäharkko Tmi (V-0030)

Peak CUSUM 6.82 in Aug; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1860.53 | - | - | - | - |
| Feb | baseline-only | 1736.58 | - | - | - | - |
| Mar | baseline-only | 1942.01 | - | - | - | - |
| Apr | scored | 1882.33 | 1846.38 | 84.464 | 0.43 | 0.00 |
| May | scored | 2100.82 | 1855.36 | 74.786 | 3.28 | 2.78 |
| Jun | scored | 2072.16 | 1904.45 | 118.803 | 1.41 | 3.69 |
| Jul | scored | 1794.05 | 1932.40 | 125.171 | -1.11 | 2.09 |
| Aug | scored | 2569.98 | 1912.64 | 125.593 | 5.23 | 6.82 |
| Sep | scored | 1752.09 | 1994.81 | 247.108 | -0.98 | 5.34 |
| Oct | scored | 1667.29 | 1967.84 | 245.145 | -1.23 | 3.61 |
| Nov | scored | 1899.38 | 1937.78 | 249.432 | -0.15 | 2.96 |
| Dec | scored | 1633.20 | 1934.29 | 238.080 | -1.26 | 1.20 |

### Niittyaihio Oy (V-0015)

Peak CUSUM 6.69 in May; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1480.19 | - | - | - | - |
| Feb | baseline-only | 1697.10 | - | - | - | - |
| Mar | baseline-only | 1193.80 | - | - | - | - |
| Apr | scored | 2425.69 | 1457.03 | 206.125 | 4.70 | 4.20 |
| May | scored | 3060.30 | 1699.19 | 455.848 | 2.99 | 6.69 |
| Jun | scored | 1761.05 | 1971.41 | 680.188 | -0.31 | 5.88 |
| Jul | scored | 1815.73 | 1936.35 | 625.854 | -0.19 | 5.18 |
| Aug | scored | 1671.64 | 1919.12 | 580.963 | -0.43 | 4.26 |
| Sep | scored | 1441.88 | 1888.19 | 549.570 | -0.81 | 2.95 |
| Oct | scored | 1585.21 | 1838.60 | 536.788 | -0.47 | 1.97 |
| Nov | scored | 1676.18 | 1813.26 | 514.884 | -0.27 | 1.21 |
| Dec | scored | 1823.62 | 1800.80 | 492.502 | 0.05 | 0.75 |

### Koskiaihio Oy (V-0105)

Peak CUSUM 6.50 in Oct; first crossed h = 4.0 in Sep.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.52 | - | - | - | - |
| Feb | baseline-only | 24.82 | - | - | - | - |
| Mar | baseline-only | 24.95 | - | - | - | - |
| Apr | scored | 25.13 | 24.76 | 0.180 | 2.04 | 1.54 |
| May | scored | 24.90 | 24.85 | 0.223 | 0.18 | 1.22 |
| Jun | scored | 24.93 | 24.86 | 0.200 | 0.31 | 1.04 |
| Jul | scored | 25.41 | 24.87 | 0.184 | 2.91 | 3.44 |
| Aug | scored | 25.17 | 24.95 | 0.253 | 0.88 | 3.82 |
| Sep | scored | 25.20 | 24.98 | 0.248 | 0.90 | 4.22 |
| Oct | scored | 25.68 | 25.00 | 0.244 | 2.78 | 6.50 |
| Nov | scored | 24.51 | 25.07 | 0.308 | -1.80 | 4.20 |
| Dec | scored | 24.84 | 25.02 | 0.334 | -0.53 | 3.17 |

### Rinnekomponentti Ky (V-0039)

Peak CUSUM 6.30 in Jun; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.81 | - | - | - | - |
| Feb | baseline-only | 25.07 | - | - | - | - |
| Mar | baseline-only | 24.87 | - | - | - | - |
| Apr | scored | 24.86 | 24.92 | 0.114 | -0.54 | 0.00 |
| May | scored | 25.37 | 24.90 | 0.102 | 4.61 | 4.11 |
| Jun | scored | 25.56 | 25.00 | 0.209 | 2.70 | 6.30 |
| Jul | scored | 25.18 | 25.09 | 0.284 | 0.31 | 6.11 |
| Aug | scored | 24.53 | 25.10 | 0.264 | -2.16 | 3.45 |
| Sep | scored | 24.17 | 25.03 | 0.311 | -2.77 | 0.18 |
| Oct | scored | 24.93 | 24.94 | 0.399 | -0.00 | 0.00 |
| Nov | scored | 25.40 | 24.94 | 0.379 | 1.23 | 0.73 |
| Dec | scored | 24.74 | 24.98 | 0.385 | -0.62 | 0.00 |

### Vaahterajärjestelmä Oy Ab (V-0057)

Peak CUSUM 6.01 in Aug; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 722.68 | - | - | - | - |
| Feb | baseline-only | 571.12 | - | - | - | - |
| Mar | baseline-only | 797.01 | - | - | - | - |
| Apr | scored | 900.51 | 696.94 | 94.001 | 2.17 | 1.67 |
| May | scored | 945.00 | 747.83 | 119.989 | 1.64 | 2.81 |
| Jun | scored | 884.46 | 787.26 | 133.185 | 0.73 | 3.04 |
| Jul | scored | 1080.08 | 803.46 | 126.863 | 2.18 | 4.72 |
| Aug | scored | 1116.16 | 842.98 | 152.198 | 1.79 | 6.01 |
| Sep | scored | 773.29 | 877.13 | 168.615 | -0.62 | 4.90 |
| Oct | scored | 736.96 | 865.59 | 162.287 | -0.79 | 3.61 |
| Nov | scored | 891.30 | 852.73 | 158.721 | 0.24 | 3.35 |
| Dec | scored | 751.49 | 856.23 | 151.740 | -0.69 | 2.16 |

### Niittykomponentti Tmi (V-0157)

Peak CUSUM 5.99 in Apr; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 778.19 | - | - | - | - |
| Feb | baseline-only | 873.90 | - | - | - | - |
| Mar | baseline-only | 846.41 | - | - | - | - |
| Apr | scored | 1093.82 | 832.83 | 40.235 | 6.49 | 5.99 |
| May | scored | 659.84 | 898.08 | 118.260 | -2.01 | 3.47 |
| Jun | scored | 708.08 | 850.43 | 142.370 | -1.00 | 1.97 |
| Jul | scored | 1080.44 | 826.71 | 140.376 | 1.81 | 3.28 |
| Aug | scored | 1122.88 | 862.95 | 157.397 | 1.65 | 4.43 |
| Sep | scored | 875.20 | 895.44 | 170.489 | -0.12 | 3.81 |
| Oct | scored | 790.37 | 893.19 | 160.865 | -0.64 | 2.67 |
| Nov | scored | 970.51 | 882.91 | 155.696 | 0.56 | 2.74 |
| Dec | scored | 911.17 | 890.88 | 150.571 | 0.13 | 2.37 |

### Kantologistiikka Oy (V-0020)

Peak CUSUM 5.64 in Apr; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1843.73 | - | - | - | - |
| Feb | baseline-only | 1662.04 | - | - | - | - |
| Mar | baseline-only | 1477.12 | - | - | - | - |
| Apr | scored | 2579.48 | 1660.96 | 149.671 | 6.14 | 5.64 |
| May | scored | 1650.67 | 1890.59 | 418.320 | -0.57 | 4.56 |
| Jun | scored | 1610.67 | 1842.61 | 386.268 | -0.60 | 3.46 |
| Jul | scored | 2078.34 | 1803.95 | 363.053 | 0.76 | 3.72 |
| Aug | scored | 1782.94 | 1843.15 | 349.567 | -0.17 | 3.05 |
| Sep | scored | 1689.71 | 1835.62 | 327.596 | -0.45 | 2.10 |
| Oct | scored | 1229.31 | 1819.41 | 312.246 | -1.89 | 0.00 |
| Nov | scored | 1909.32 | 1760.40 | 345.092 | 0.43 | 0.00 |
| Dec | scored | 1762.17 | 1773.94 | 331.805 | -0.04 | 0.00 |

### Virtakomponentti Tmi (V-0119)

Peak CUSUM 5.50 in Jun; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.65 | - | - | - | - |
| Feb | baseline-only | 24.88 | - | - | - | - |
| Mar | baseline-only | 24.80 | - | - | - | - |
| Apr | scored | 24.71 | 24.78 | 0.092 | -0.74 | 0.00 |
| May | scored | 24.72 | 24.76 | 0.085 | -0.47 | 0.00 |
| Jun | scored | 25.22 | 24.75 | 0.077 | 6.00 | 5.50 |
| Jul | scored | 24.87 | 24.83 | 0.187 | 0.19 | 5.19 |
| Aug | scored | 24.70 | 24.84 | 0.174 | -0.78 | 3.91 |
| Sep | scored | 25.07 | 24.82 | 0.168 | 1.48 | 4.89 |
| Oct | scored | 25.04 | 24.85 | 0.177 | 1.07 | 5.46 |
| Nov | scored | 24.76 | 24.87 | 0.177 | -0.62 | 4.34 |
| Dec | scored | 24.78 | 24.86 | 0.172 | -0.41 | 3.43 |

### Kuusamoväline Tmi (V-0040)

Peak CUSUM 5.39 in Sep; first crossed h = 4.0 in Sep.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 25.14 | - | - | - | - |
| Feb | baseline-only | 25.24 | - | - | - | - |
| Mar | baseline-only | 24.49 | - | - | - | - |
| Apr | scored | 24.72 | 24.96 | 0.329 | -0.71 | 0.00 |
| May | scored | 24.90 | 24.90 | 0.302 | 0.02 | 0.00 |
| Jun | scored | 24.85 | 24.90 | 0.270 | -0.17 | 0.00 |
| Jul | scored | 25.83 | 24.89 | 0.247 | 3.80 | 3.30 |
| Aug | scored | 24.86 | 25.03 | 0.401 | -0.40 | 2.40 |
| Sep | scored | 26.33 | 25.01 | 0.379 | 3.49 | 5.39 |
| Oct | scored | 24.85 | 25.15 | 0.548 | -0.56 | 4.33 |
| Nov | scored | 25.12 | 25.12 | 0.528 | -0.00 | 3.83 |
| Dec | scored | 25.15 | 25.12 | 0.503 | 0.06 | 3.40 |

### Lehtotukku Oy Ab (V-0064)

Peak CUSUM 5.39 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1881.86 | - | - | - | - |
| Feb | baseline-only | 1780.92 | - | - | - | - |
| Mar | baseline-only | 1788.57 | - | - | - | - |
| Apr | scored | 1994.86 | 1817.12 | 45.887 | 3.87 | 3.37 |
| May | scored | 2079.60 | 1861.56 | 86.619 | 2.52 | 5.39 |
| Jun | scored | 1632.05 | 1905.16 | 116.658 | -2.34 | 2.55 |
| Jul | scored | 2057.66 | 1859.65 | 147.311 | 1.34 | 3.39 |
| Aug | scored | 1680.85 | 1887.93 | 152.976 | -1.35 | 1.54 |
| Sep | scored | 1754.84 | 1862.05 | 158.642 | -0.68 | 0.36 |
| Oct | scored | 1747.31 | 1850.14 | 153.317 | -0.67 | 0.00 |
| Nov | scored | 1794.93 | 1839.85 | 148.684 | -0.30 | 0.00 |
| Dec | scored | 1886.55 | 1835.77 | 142.352 | 0.36 | 0.00 |

### Virtapalvelu Oy (V-0037)

Peak CUSUM 5.01 in Jun; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.78 | - | - | - | - |
| Feb | baseline-only | 24.86 | - | - | - | - |
| Mar | baseline-only | 25.01 | - | - | - | - |
| Apr | scored | 24.63 | 24.88 | 0.093 | -2.77 | 0.00 |
| May | scored | 25.56 | 24.82 | 0.138 | 5.35 | 4.85 |
| Jun | scored | 25.18 | 24.97 | 0.319 | 0.66 | 5.01 |
| Jul | scored | 25.11 | 25.00 | 0.302 | 0.37 | 4.88 |
| Aug | scored | 24.72 | 25.02 | 0.282 | -1.05 | 3.32 |
| Sep | scored | 24.69 | 24.98 | 0.282 | -1.03 | 1.80 |
| Oct | scored | 25.31 | 24.95 | 0.281 | 1.30 | 2.60 |
| Nov | scored | 24.84 | 24.99 | 0.288 | -0.50 | 1.61 |
| Dec | scored | 25.35 | 24.97 | 0.278 | 1.36 | 2.46 |

### Rantatekniikka Oy (V-0166)

Peak CUSUM 4.88 in Jun; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 25.10 | - | - | - | - |
| Feb | baseline-only | 25.10 | - | - | - | - |
| Mar | baseline-only | 25.07 | - | - | - | - |
| Apr | scored | 25.00 | 25.09 | 0.015 | -6.13 | 0.00 |
| May | scored | 25.04 | 25.07 | 0.041 | -0.67 | 0.00 |
| Jun | scored | 25.27 | 25.06 | 0.039 | 5.38 | 4.88 |
| Jul | scored | 24.70 | 25.10 | 0.085 | -4.65 | 0.00 |
| Aug | scored | 24.54 | 25.04 | 0.160 | -3.15 | 0.00 |
| Sep | scored | 24.38 | 24.98 | 0.224 | -2.69 | 0.00 |
| Oct | scored | 24.85 | 24.91 | 0.284 | -0.23 | 0.00 |
| Nov | scored | 24.66 | 24.91 | 0.270 | -0.93 | 0.00 |
| Dec | scored | 24.49 | 24.88 | 0.267 | -1.47 | 0.00 |

### Vaahterahuolto Oy Ab (V-0147)

Peak CUSUM 4.81 in Dec; first crossed h = 4.0 in Dec.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1030.46 | - | - | - | - |
| Feb | baseline-only | 910.21 | - | - | - | - |
| Mar | baseline-only | 815.87 | - | - | - | - |
| Apr | scored | 985.77 | 918.85 | 87.819 | 0.76 | 0.26 |
| May | scored | 891.81 | 935.58 | 81.388 | -0.54 | 0.00 |
| Jun | scored | 975.70 | 926.82 | 74.871 | 0.65 | 0.15 |
| Jul | scored | 926.30 | 934.97 | 70.733 | -0.12 | 0.00 |
| Aug | scored | 805.33 | 933.73 | 65.556 | -1.96 | 0.00 |
| Sep | scored | 850.42 | 917.68 | 74.590 | -0.90 | 0.00 |
| Oct | scored | 916.09 | 910.21 | 73.433 | 0.08 | 0.00 |
| Nov | scored | 903.01 | 910.80 | 69.687 | -0.11 | 0.00 |
| Dec | scored | 1263.08 | 910.09 | 66.481 | 5.31 | 4.81 |

### Tuomimateriaali Oy Ab (V-0138)

Peak CUSUM 4.71 in Apr; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.97 | - | - | - | - |
| Feb | baseline-only | 24.92 | - | - | - | - |
| Mar | baseline-only | 25.02 | - | - | - | - |
| Apr | scored | 25.19 | 24.97 | 0.043 | 5.21 | 4.71 |
| May | scored | 24.86 | 25.03 | 0.104 | -1.58 | 2.64 |
| Jun | scored | 25.01 | 24.99 | 0.113 | 0.12 | 2.25 |
| Jul | scored | 24.89 | 25.00 | 0.104 | -1.00 | 0.76 |
| Aug | scored | 24.91 | 24.98 | 0.102 | -0.71 | 0.00 |
| Sep | scored | 24.85 | 24.97 | 0.099 | -1.24 | 0.00 |
| Oct | scored | 25.13 | 24.96 | 0.101 | 1.69 | 1.19 |
| Nov | scored | 25.15 | 24.97 | 0.108 | 1.66 | 2.35 |
| Dec | scored | 24.89 | 24.99 | 0.116 | -0.86 | 0.99 |

### Pihkahuolto Oy Ab (V-0090)

Peak CUSUM 4.70 in Sep; first crossed h = 4.0 in Sep.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1738.16 | - | - | - | - |
| Feb | baseline-only | 1720.65 | - | - | - | - |
| Mar | baseline-only | 1421.38 | - | - | - | - |
| Apr | scored | 1662.77 | 1626.73 | 145.380 | 0.25 | 0.00 |
| May | scored | 2067.08 | 1635.74 | 126.867 | 3.40 | 2.90 |
| Jun | scored | 1854.18 | 1722.01 | 206.504 | 0.64 | 3.04 |
| Jul | scored | 1802.44 | 1744.04 | 194.840 | 0.30 | 2.84 |
| Aug | scored | 1702.63 | 1752.38 | 181.541 | -0.27 | 2.07 |
| Sep | scored | 2280.99 | 1746.16 | 170.611 | 3.13 | 4.70 |
| Oct | scored | 1635.20 | 1805.59 | 232.646 | -0.73 | 3.47 |
| Nov | scored | 1660.27 | 1788.55 | 226.549 | -0.57 | 2.40 |
| Dec | scored | 2067.32 | 1776.89 | 219.132 | 1.33 | 3.23 |

### Louhosmateriaali Tmi (V-0195)

Peak CUSUM 4.70 in Dec; first crossed h = 4.0 in Nov.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 110.46 | - | - | - | - |
| Feb | baseline-only | 110.45 | - | - | - | - |
| Mar | baseline-only | 109.75 | - | - | - | - |
| Apr | scored | 108.20 | 110.22 | 0.332 | -6.09 | 0.00 |
| May | scored | 110.01 | 109.71 | 0.921 | 0.33 | 0.00 |
| Jun | scored | 110.43 | 109.77 | 0.833 | 0.79 | 0.29 |
| Jul | scored | 109.29 | 109.88 | 0.799 | -0.74 | 0.00 |
| Aug | scored | 111.66 | 109.80 | 0.768 | 2.42 | 1.92 |
| Sep | scored | 111.88 | 110.03 | 0.945 | 1.95 | 3.37 |
| Oct | scored | 110.82 | 110.24 | 1.063 | 0.54 | 3.42 |
| Nov | scored | 111.65 | 110.29 | 1.023 | 1.33 | 4.24 |
| Dec | scored | 111.42 | 110.42 | 1.051 | 0.95 | 4.70 |

### Honkatukku Ky (V-0118)

Peak CUSUM 4.62 in Jul; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 2017.23 | - | - | - | - |
| Feb | baseline-only | 1690.14 | - | - | - | - |
| Mar | baseline-only | 2022.61 | - | - | - | - |
| Apr | scored | 2268.95 | 1909.99 | 155.477 | 2.31 | 1.81 |
| May | scored | 2346.28 | 1999.73 | 205.643 | 1.69 | 2.99 |
| Jun | scored | 1858.60 | 2069.04 | 230.318 | -0.91 | 1.58 |
| Jul | scored | 2827.66 | 2033.97 | 224.401 | 3.54 | 4.62 |
| Aug | scored | 2137.42 | 2147.35 | 346.842 | -0.03 | 4.09 |
| Sep | scored | 1944.96 | 2146.11 | 324.458 | -0.62 | 2.97 |
| Oct | scored | 1482.57 | 2123.76 | 312.365 | -2.05 | 0.42 |
| Nov | scored | 1827.01 | 2059.64 | 353.293 | -0.66 | 0.00 |
| Dec | scored | 1925.69 | 2038.49 | 343.426 | -0.33 | 0.00 |

### Kaljukomponentti Oy Ab (V-0098)

Peak CUSUM 4.60 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 916.87 | - | - | - | - |
| Feb | baseline-only | 979.69 | - | - | - | - |
| Mar | baseline-only | 944.74 | - | - | - | - |
| Apr | scored | 1062.01 | 947.10 | 25.699 | 4.47 | 3.97 |
| May | scored | 1037.58 | 975.83 | 54.506 | 1.13 | 4.60 |
| Jun | scored | 665.32 | 988.18 | 54.652 | -5.91 | 0.00 |
| Aug | scored | 1110.10 | 934.37 | 130.255 | 1.35 | 0.85 |
| Sep | scored | 1238.26 | 959.47 | 135.367 | 2.06 | 2.41 |
| Oct | scored | 1260.60 | 994.32 | 156.635 | 1.70 | 3.61 |
| Nov | scored | 821.68 | 1023.91 | 169.740 | -1.19 | 1.92 |
| Dec | scored | 945.73 | 1003.69 | 172.078 | -0.34 | 1.08 |

### Kiviaihio Oy (V-0004)

Peak CUSUM 4.59 in Aug; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 50.53 | - | - | - | - |
| Feb | baseline-only | 52.14 | - | - | - | - |
| Mar | baseline-only | 52.33 | - | - | - | - |
| Apr | scored | 51.77 | 51.67 | 0.806 | 0.13 | 0.00 |
| May | scored | 52.29 | 51.69 | 0.700 | 0.85 | 0.35 |
| Jun | scored | 53.54 | 51.81 | 0.669 | 2.58 | 2.43 |
| Jul | scored | 54.06 | 52.10 | 0.888 | 2.21 | 4.14 |
| Aug | scored | 53.40 | 52.38 | 1.071 | 0.95 | 4.59 |
| Sep | scored | 52.80 | 52.51 | 1.057 | 0.27 | 4.36 |
| Oct | scored | 52.22 | 52.54 | 1.000 | -0.32 | 3.54 |
| Nov | scored | 52.82 | 52.51 | 0.954 | 0.32 | 3.37 |
| Dec | scored | 52.22 | 52.54 | 0.914 | -0.34 | 2.52 |

### Kanervapalvelu Oy (V-0104)

Peak CUSUM 4.52 in Aug; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 107.93 | - | - | - | - |
| Feb | baseline-only | 111.88 | - | - | - | - |
| Mar | baseline-only | 109.50 | - | - | - | - |
| Apr | scored | 112.23 | 109.77 | 1.624 | 1.52 | 1.02 |
| May | scored | 111.49 | 110.38 | 1.765 | 0.63 | 1.15 |
| Jun | scored | 112.52 | 110.60 | 1.640 | 1.17 | 1.82 |
| Jul | scored | 113.20 | 110.92 | 1.659 | 1.37 | 2.69 |
| Aug | scored | 115.29 | 111.25 | 1.730 | 2.34 | 4.52 |
| Sep | scored | 109.82 | 111.75 | 2.099 | -0.92 | 3.10 |
| Oct | scored | 108.97 | 111.54 | 2.069 | -1.24 | 1.36 |
| Nov | scored | 111.26 | 111.28 | 2.109 | -0.01 | 0.85 |
| Dec | scored | 111.39 | 111.28 | 2.011 | 0.06 | 0.41 |

### Lehtovalssi Ky (V-0058)

Peak CUSUM 4.49 in Nov; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1906.93 | - | - | - | - |
| Feb | baseline-only | 1492.36 | - | - | - | - |
| Apr | baseline-only | 1263.07 | - | - | - | - |
| May | scored | 2615.17 | 1554.12 | 266.458 | 3.98 | 3.48 |
| Jun | scored | 2393.48 | 1819.38 | 514.142 | 1.12 | 4.10 |
| Aug | scored | 2069.37 | 1934.20 | 514.012 | 0.26 | 3.86 |
| Nov | scored | 2489.41 | 1956.73 | 471.923 | 1.13 | 4.49 |
| Dec | scored | 1676.86 | 2032.82 | 475.016 | -0.75 | 3.24 |

### Saramalmi Tmi (V-0079)

Peak CUSUM 4.48 in Sep; first crossed h = 4.0 in Aug.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 834.91 | - | - | - | - |
| Feb | baseline-only | 1051.05 | - | - | - | - |
| Mar | baseline-only | 827.71 | - | - | - | - |
| Apr | scored | 727.61 | 904.55 | 103.627 | -1.71 | 0.00 |
| May | scored | 902.40 | 860.32 | 118.001 | 0.36 | 0.00 |
| Jun | scored | 606.29 | 868.73 | 106.877 | -2.46 | 0.00 |
| Jul | scored | 1115.37 | 824.99 | 138.147 | 2.10 | 1.60 |
| Aug | scored | 1389.26 | 866.48 | 163.350 | 3.20 | 4.30 |
| Sep | scored | 1089.20 | 931.83 | 230.740 | 0.68 | 4.48 |
| Oct | scored | 699.12 | 949.31 | 223.095 | -1.12 | 2.86 |
| Nov | scored | 1097.36 | 924.29 | 224.561 | 0.77 | 3.13 |
| Dec | scored | 1133.12 | 940.03 | 219.815 | 0.88 | 3.51 |

### Pihkapalvelu Oy (V-0034)

Peak CUSUM 4.40 in Aug; first crossed h = 4.0 in Jun.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.97 | - | - | - | - |
| Feb | baseline-only | 25.02 | - | - | - | - |
| Mar | baseline-only | 24.92 | - | - | - | - |
| Apr | scored | 24.75 | 24.97 | 0.038 | -5.88 | 0.00 |
| May | scored | 25.16 | 24.91 | 0.102 | 2.44 | 1.94 |
| Jun | scored | 25.35 | 24.96 | 0.135 | 2.85 | 4.30 |
| Jul | scored | 25.14 | 25.03 | 0.189 | 0.59 | 4.39 |
| Aug | scored | 25.14 | 25.04 | 0.179 | 0.51 | 4.40 |
| Sep | scored | 25.02 | 25.06 | 0.171 | -0.24 | 3.66 |
| Oct | scored | 24.39 | 25.05 | 0.161 | -4.09 | 0.00 |
| Nov | scored | 24.95 | 24.99 | 0.250 | -0.14 | 0.00 |
| Dec | scored | 24.86 | 24.98 | 0.239 | -0.53 | 0.00 |

### Pihkajärjestelmä Oy Ab (V-0014)

Peak CUSUM 4.35 in Jul; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 25.15 | - | - | - | - |
| Feb | baseline-only | 24.97 | - | - | - | - |
| Mar | baseline-only | 24.85 | - | - | - | - |
| Apr | scored | 24.65 | 24.99 | 0.123 | -2.75 | 0.00 |
| May | scored | 25.53 | 24.91 | 0.181 | 3.43 | 2.93 |
| Jun | scored | 25.28 | 25.03 | 0.297 | 0.84 | 3.27 |
| Jul | scored | 25.53 | 25.07 | 0.287 | 1.58 | 4.35 |
| Aug | scored | 24.83 | 25.14 | 0.309 | -0.99 | 2.86 |
| Sep | scored | 25.03 | 25.10 | 0.307 | -0.24 | 2.12 |
| Oct | scored | 25.11 | 25.09 | 0.290 | 0.05 | 1.67 |
| Nov | scored | 24.37 | 25.09 | 0.275 | -2.62 | 0.00 |
| Dec | scored | 24.84 | 25.03 | 0.334 | -0.56 | 0.00 |

### Kanervaväline Oy (V-0187)

Peak CUSUM 4.32 in Aug; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 24.37 | - | - | - | - |
| Feb | baseline-only | 24.95 | - | - | - | - |
| Mar | baseline-only | 25.03 | - | - | - | - |
| Apr | scored | 25.00 | 24.78 | 0.297 | 0.72 | 0.22 |
| May | scored | 25.23 | 24.84 | 0.273 | 1.42 | 1.14 |
| Jun | scored | 24.89 | 24.92 | 0.290 | -0.08 | 0.56 |
| Jul | scored | 26.03 | 24.91 | 0.264 | 4.25 | 4.31 |
| Aug | scored | 25.31 | 25.07 | 0.463 | 0.51 | 4.32 |
| Sep | scored | 24.80 | 25.10 | 0.440 | -0.69 | 3.12 |
| Oct | scored | 24.55 | 25.07 | 0.426 | -1.22 | 1.40 |
| Nov | scored | 24.91 | 25.02 | 0.433 | -0.24 | 0.66 |
| Dec | scored | 25.30 | 25.01 | 0.414 | 0.72 | 0.88 |

### Jääaihio Oy (V-0171)

Peak CUSUM 4.25 in Dec; first crossed h = 4.0 in Dec.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 872.56 | - | - | - | - |
| Feb | baseline-only | 1062.34 | - | - | - | - |
| Mar | baseline-only | 924.91 | - | - | - | - |
| Apr | scored | 606.53 | 953.27 | 80.031 | -4.33 | 0.00 |
| May | scored | 704.97 | 866.58 | 165.369 | -0.98 | 0.00 |
| Jun | scored | 696.98 | 834.26 | 161.420 | -0.85 | 0.00 |
| Sep | scored | 1105.92 | 811.38 | 155.985 | 1.89 | 1.39 |
| Oct | scored | 1120.42 | 853.46 | 177.421 | 1.50 | 2.39 |
| Nov | scored | 963.78 | 886.83 | 187.986 | 0.41 | 2.30 |
| Dec | scored | 1333.45 | 895.38 | 178.877 | 2.45 | 4.25 |

### Vuoritukku Oy Ab (V-0103)

Peak CUSUM 4.24 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1038.61 | - | - | - | - |
| Feb | baseline-only | 926.88 | - | - | - | - |
| Mar | baseline-only | 888.75 | - | - | - | - |
| Apr | scored | 761.74 | 951.41 | 63.594 | -2.98 | 0.00 |
| May | scored | 1372.68 | 903.99 | 98.886 | 4.74 | 4.24 |
| Jun | scored | 996.77 | 997.73 | 207.293 | -0.00 | 3.74 |
| Jul | scored | 873.79 | 997.57 | 189.232 | -0.65 | 2.58 |
| Aug | scored | 758.04 | 979.89 | 180.470 | -1.23 | 0.85 |
| Sep | scored | 865.50 | 952.16 | 184.068 | -0.47 | 0.00 |
| Oct | scored | 916.28 | 942.53 | 175.665 | -0.15 | 0.00 |
| Nov | scored | 1020.76 | 939.90 | 166.836 | 0.48 | 0.00 |
| Dec | scored | 1095.62 | 947.25 | 160.762 | 0.92 | 0.42 |

### Hankiaihio Oy Ab (V-0087)

Peak CUSUM 4.23 in Oct; first crossed h = 4.0 in Oct.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 25.43 | - | - | - | - |
| Feb | baseline-only | 24.97 | - | - | - | - |
| Mar | baseline-only | 25.06 | - | - | - | - |
| Apr | scored | 24.69 | 25.15 | 0.202 | -2.29 | 0.00 |
| May | scored | 24.47 | 25.04 | 0.266 | -2.13 | 0.00 |
| Jun | scored | 24.77 | 24.92 | 0.329 | -0.48 | 0.00 |
| Jul | scored | 24.32 | 24.90 | 0.306 | -1.88 | 0.00 |
| Aug | scored | 24.59 | 24.82 | 0.347 | -0.64 | 0.00 |
| Sep | scored | 25.29 | 24.79 | 0.333 | 1.50 | 1.00 |
| Oct | scored | 26.15 | 24.84 | 0.351 | 3.73 | 4.23 |
| Nov | scored | 24.76 | 24.97 | 0.515 | -0.42 | 3.31 |
| Dec | scored | 24.78 | 24.95 | 0.495 | -0.34 | 2.47 |

### Lehtoharkko Tmi (V-0093)

Peak CUSUM 4.22 in Oct; first crossed h = 4.0 in Oct.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 1796.09 | - | - | - | - |
| Feb | baseline-only | 1777.56 | - | - | - | - |
| Mar | baseline-only | 1915.93 | - | - | - | - |
| Apr | scored | 1716.58 | 1829.86 | 61.329 | -1.85 | 0.00 |
| May | scored | 1944.17 | 1801.54 | 72.298 | 1.97 | 1.47 |
| Jun | scored | 1910.12 | 1830.07 | 86.235 | 0.93 | 1.90 |
| Jul | scored | 1804.31 | 1843.41 | 84.185 | -0.46 | 0.94 |
| Aug | scored | 2003.60 | 1837.83 | 79.132 | 2.09 | 2.53 |
| Sep | scored | 1980.68 | 1858.55 | 92.113 | 1.33 | 3.36 |
| Oct | scored | 2001.74 | 1872.12 | 94.949 | 1.37 | 4.22 |
| Nov | scored | 1796.05 | 1885.08 | 98.112 | -0.91 | 2.82 |
| Dec | scored | 1749.90 | 1876.99 | 96.985 | -1.31 | 1.00 |

### Petäjäpalvelu Oy Ab (V-0054)

Peak CUSUM 4.16 in May; first crossed h = 4.0 in Apr.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 901.78 | - | - | - | - |
| Feb | baseline-only | 968.69 | - | - | - | - |
| Mar | baseline-only | 923.90 | - | - | - | - |
| Apr | scored | 1058.43 | 931.45 | 27.836 | 4.56 | 4.06 |
| May | scored | 999.22 | 963.20 | 60.034 | 0.60 | 4.16 |
| Jun | scored | 910.30 | 970.40 | 55.596 | -1.08 | 2.58 |
| Jul | scored | 1048.88 | 960.39 | 55.475 | 1.60 | 3.68 |
| Aug | scored | 1020.51 | 973.03 | 59.973 | 0.79 | 3.97 |
| Sep | scored | 874.90 | 978.96 | 58.256 | -1.79 | 1.68 |
| Oct | scored | 932.47 | 967.40 | 63.925 | -0.55 | 0.63 |
| Nov | scored | 1045.45 | 963.91 | 61.543 | 1.33 | 1.46 |
| Dec | scored | 839.54 | 971.32 | 63.188 | -2.09 | 0.00 |

### Kivivaraosa Tmi (V-0178)

Peak CUSUM 4.05 in May; first crossed h = 4.0 in May.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 784.86 | - | - | - | - |
| Feb | baseline-only | 1114.69 | - | - | - | - |
| Mar | baseline-only | 800.23 | - | - | - | - |
| Apr | scored | 1300.50 | 899.92 | 151.989 | 2.64 | 2.14 |
| May | scored | 1526.19 | 1000.07 | 217.743 | 2.42 | 4.05 |
| Sep | scored | 1078.91 | 1105.29 | 286.736 | -0.09 | 3.46 |
| Nov | scored | 972.09 | 1100.89 | 261.938 | -0.49 | 2.47 |
| Dec | scored | 963.61 | 1082.49 | 246.660 | -0.48 | 1.49 |

### Kivilastu Oy (V-0024)

Peak CUSUM 4.03 in Jul; first crossed h = 4.0 in Jul.

| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |
|---|---|---|---|---|---|---|
| Jan | baseline-only | 25.03 | - | - | - | - |
| Feb | baseline-only | 24.92 | - | - | - | - |
| Mar | baseline-only | 25.14 | - | - | - | - |
| Apr | scored | 25.20 | 25.03 | 0.087 | 2.00 | 1.50 |
| May | scored | 25.09 | 25.07 | 0.107 | 0.18 | 1.18 |
| Jun | scored | 24.74 | 25.08 | 0.096 | -3.48 | 0.00 |
| Jul | scored | 25.71 | 25.02 | 0.152 | 4.53 | 4.03 |
| Aug | scored | 24.80 | 25.12 | 0.280 | -1.14 | 2.40 |
| Sep | scored | 25.11 | 25.08 | 0.282 | 0.09 | 1.99 |
| Oct | scored | 24.80 | 25.08 | 0.266 | -1.06 | 0.42 |
| Nov | scored | 25.58 | 25.06 | 0.266 | 1.97 | 1.89 |
| Dec | scored | 24.95 | 25.10 | 0.295 | -0.51 | 0.88 |

## Not scoreable (5 vendors)

These vendors never reached 3 invoices in enough calendar months to build a baseline and score at least one month -- out of scope for this method, not a negative finding.

| Vendor ID | Vendor name | Total invoices | Months with >= 3 invoices |
|---|---|---|---|
| V-0081 | Sarapalvelu Oy | 8 | 0 |
| V-0132 | Tuomiharkko Ky | 7 | 0 |
| V-0007 | Hankitekniikka Ky | 5 | 0 |
| V-0112 | Honkamateriaali Oy | 4 | 0 |
| V-0172 | Kivitekniikka Tmi | 2 | 0 |

