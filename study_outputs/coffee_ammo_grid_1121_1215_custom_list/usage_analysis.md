# Usage-weighted analysis

- Grid root: `study_outputs/coffee_ammo_grid_1121_1215_custom_list`
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
| 6.8x51mm Hybrid |        0.086 |               8 |        6.75  |            7   |     0.46291 |   0.359508  |     0.378884  |                   0     |                         1 |            -0.715581 |
| 5.8x42mm DVC12  |        0.062 |               8 |        6     |            6   |     0       |   0.134304  |     0.121762  |                   0     |                         1 |           nan        |
| 5.56x45mm M995  |        0.034 |               8 |       78.75  |           66.5 |    77.7703  |   0.611865  |     0.608164  |                   0.375 |                         1 |             0.845815 |
| 4.6x30mm AP SX  |        0.019 |               8 |       30.125 |            6   |    67.8326  |   0.113544  |     0.104943  |                   0     |                         1 |             0.814875 |
| 7.62x51mm M62   |        0.016 |               8 |       87.75  |           90.5 |    58.3946  |   0.668251  |     0.680127  |                   0.375 |                         1 |             0.936578 |
| 9x39mm BP       |        0.015 |               8 |      114.75  |          114.5 |   102.295   |   0.288179  |     0.266564  |                   0.375 |                         1 |             0.994806 |
| 12.7x55mm PS12B |        0.011 |               8 |       22.75  |           17   |    24.2355  |   0.0580665 |     0.0472093 |                   0     |                         1 |            -0.107186 |
| 5.7x28mm SS190  |        0.01  |               8 |       13.5   |            7   |    18.7921  |   0.121554  |     0.128443  |                   0     |                         1 |             0.80899  |
| 7.62x54R BT     |        0.006 |               8 |       33     |           30   |    15.3809  |   0.457779  |     0.460703  |                   0     |                         1 |             0.775313 |
| 7.62x39mm AP    |      nan     |               8 |      120.75  |          126.5 |    97.9982  |   0.63803   |     0.648106  |                   0.5   |                         1 |             0.999995 |

## Experiment-level usage-weighted summary

| experiment              | freq   | max_lag   |   n_items_total |   n_items_with_usage |   usage_weighted_lag_mean_h |   usage_weighted_corr_mean |   usage_weighted_share_peak_in_96_168h |
|:------------------------|:-------|:----------|----------------:|---------------------:|----------------------------:|---------------------------:|---------------------------------------:|
| g1_24h                  | 1H     | 24h       |              10 |                    9 |                     6.62162 |                   0.313775 |                               0        |
| g2_2d                   | 1H     | 2D        |              10 |                    9 |                     9.59459 |                   0.314438 |                               0        |
| g3_3d                   | 1H     | 3D        |              10 |                    9 |                    13.8571  |                   0.314935 |                               0        |
| g4_5d_granger3d         | 1H     | 5D        |              10 |                    9 |                    15.2471  |                   0.315331 |                               0        |
| g5_7d_ffill0_granger3d  | 1H     | 7D        |              10 |                    9 |                    44.8069  |                   0.319056 |                               0.250965 |
| g6_7d_ffill3_granger3d  | 1H     | 7D        |              10 |                    9 |                    41.8224  |                   0.320968 |                               0.250965 |
| g7_freq2h_7d_granger3d  | 2H     | 7D        |              10 |                    9 |                    38.6178  |                   0.325083 |                               0.250965 |
| g8_freq6h_14d_granger3d | 6H     | 14D       |              10 |                    9 |                    73.7838  |                   0.303701 |                               0        |

## Cross-sectional diagnostics

| metric                                   |      value |   n |
|:-----------------------------------------|-----------:|----:|
| spearman(usage_rate, lag_median_h)       | -0.327743  |   9 |
| spearman(usage_rate, corr_median)        |  0.0666667 |   9 |
| spearman(usage_rate, corr_lag_vs_maxlag) |  0.047619  |   9 |

## Missing usage_rate for items

- 7.62x39mm AP
