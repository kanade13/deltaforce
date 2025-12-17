# Usage-weighted analysis

- Grid root: `study_outputs/coffee_ammo_grid_0922_1109_custom_list`
- README: `README.md`

## Weapon usage mapping (by weapon)

| weapon   |   usage_rate | ammo            |
|:---------|-------------:|:----------------|
| ash12    |        0.011 | 12.7x55mm PS12B |
| mp7      |        0.019 | 4.6x30mm AP SX  |
| k416     |        0.034 | 5.56x45mm M995  |
| p90      |        0.01  | 5.7x28mm SS190  |
| CI-19    |        0.062 | 5.8x42mm DVC12  |
| m7       |        0.086 | 6.8x51mm Hybrid |
| m14      |        0.016 | 7.62x51mm M62   |
| pkm      |        0.006 | 7.62x54R BT     |
| asval    |        0.015 | 9x39mm BP       |

## Ammo-level summary (joined usage_rate by ammo)

| item            |   usage_rate |   n_experiments |   lag_mean_h |   lag_median_h |   lag_std_h |   corr_mean |   corr_median |   share_peak_in_96_168h |   share_granger_p_lt_0_05 |   corr_lag_vs_maxlag |
|:----------------|-------------:|----------------:|-------------:|---------------:|------------:|------------:|--------------:|------------------------:|--------------------------:|---------------------:|
| 6.8x51mm Hybrid |        0.086 |               8 |        6.75  |              7 |     0.46291 |    0.34347  |      0.335245 |                     0   |                     0.875 |            -0.715581 |
| 5.8x42mm DVC12  |        0.062 |               8 |        6.75  |              7 |     0.46291 |    0.338219 |      0.333957 |                     0   |                     1     |            -0.715581 |
| 5.56x45mm M995  |        0.034 |               8 |      109.75  |            127 |    74.6166  |    0.541874 |      0.540289 |                     0.5 |                     1     |             0.967546 |
| 4.6x30mm AP SX  |        0.019 |               8 |       30     |             30 |    12.8285  |    0.424769 |      0.416494 |                     0   |                     0.875 |             0.391397 |
| 7.62x51mm M62   |        0.016 |               8 |       43.5   |             55 |    22.6021  |    0.707091 |      0.705749 |                     0   |                     1     |             0.691131 |
| 9x39mm BP       |        0.015 |               8 |       45.125 |             54 |    17.7397  |    0.385249 |      0.391318 |                     0   |                     1     |             0.617677 |
| 12.7x55mm PS12B |        0.011 |               8 |        6     |              6 |     0       |    0.405599 |      0.40272  |                     0   |                     0.875 |           nan        |
| 5.7x28mm SS190  |        0.01  |               8 |        6     |              6 |     0       |    0.288836 |      0.297237 |                     0   |                     1     |           nan        |
| 7.62x54R BT     |        0.006 |               8 |        8.75  |              6 |     8.61477 |    0.643814 |      0.651979 |                     0   |                     0     |             0.791289 |
| 7.62x39mm AP    |      nan     |               8 |      126.75  |            126 |    94.7836  |    0.540389 |      0.548729 |                     0.5 |                     1     |             0.996018 |

## Experiment-level usage-weighted summary

| experiment              | freq   | max_lag   |   n_items_total |   n_items_with_usage |   usage_weighted_lag_mean_h |   usage_weighted_corr_mean |   usage_weighted_share_peak_in_96_168h |
|:------------------------|:-------|:----------|----------------:|---------------------:|----------------------------:|---------------------------:|---------------------------------------:|
| g1_24h                  | 1H     | 24h       |              10 |                    9 |                     6.76448 |                   0.393297 |                               0        |
| g2_2d                   | 1H     | 2D        |              10 |                    9 |                    13.1236  |                   0.396657 |                               0        |
| g3_3d                   | 1H     | 3D        |              10 |                    9 |                    20.5714  |                   0.401455 |                               0        |
| g4_5d_granger3d         | 1H     | 5D        |              10 |                    9 |                    26.8726  |                   0.40362  |                               0.131274 |
| g5_7d_ffill0_granger3d  | 1H     | 7D        |              10 |                    9 |                    33.1737  |                   0.40538  |                               0.131274 |
| g6_7d_ffill3_granger3d  | 1H     | 7D        |              10 |                    9 |                    33.1737  |                   0.404578 |                               0.131274 |
| g7_freq2h_7d_granger3d  | 2H     | 7D        |              10 |                    9 |                    34.3861  |                   0.384454 |                               0.131274 |
| g8_freq6h_14d_granger3d | 6H     | 14D       |              10 |                    9 |                    43.5753  |                   0.463299 |                               0        |

## Cross-sectional diagnostics

| metric                                   |     value |   n |
|:-----------------------------------------|----------:|----:|
| spearman(usage_rate, lag_median_h)       |  0.519266 |   9 |
| spearman(usage_rate, corr_median)        | -0.183333 |   9 |
| spearman(usage_rate, corr_lag_vs_maxlag) | -0.594619 |   9 |

## Missing usage_rate for items

- 7.62x39mm AP
