# ACPC 2010 2P LIMIT reliability

Source files: `data\raw\acpc_2010_2p_limit`
Files parsed: 29,000
Hands parsed: 87,000,000
Hand-player entries: 174,000,000

## Split-half stability
Overall player bb/100 split-half: Pearson 1.000, Spearman 0.993.
Directed pairwise bb/100 split-half: Pearson 1.000, Spearman 0.986.

## Overall player halves
| player          |   half0 |   half1 |
|:----------------|--------:|--------:|
| Hyperborean_tbr |   18.03 |   18.11 |
| Sartre          |   16.94 |   17.62 |
| GS6_iro         |   15.91 |   15.66 |
| Jester          |   13.52 |   13.38 |
| Arnold2         |   13.16 |   13.66 |
| GS6_tbr         |   11.76 |   11.57 |
| LittleRock      |    9.23 |    9.29 |
| PULPO           |    8.83 |    8.92 |
| Rockhopper      |    8.65 |    8.30 |
| Hyperborean_iro |    8.33 |    8.20 |
| Slumbot         |    8.06 |    7.85 |
| GGValuta        |    7.56 |    7.94 |
| PLICAS          |   -6.94 |   -7.14 |
| ASVP            |  -36.33 |  -36.51 |
| longhorn        | -144.03 | -143.96 |

## Pairwise summary sample
| player          | opponent        |   hands |   bb100 |
|:----------------|:----------------|--------:|--------:|
| GGValuta        | Slumbot         | 3000000 |    0.23 |
| GGValuta        | Hyperborean_iro | 3000000 |   -0.24 |
| GGValuta        | PULPO           | 3000000 |    0.25 |
| Hyperborean_iro | Rockhopper      | 3000000 |   -0.29 |
| Hyperborean_iro | GGValuta        | 3000000 |    0.24 |
| Hyperborean_iro | PULPO           | 3000000 |    0.16 |
| GGValuta        | Rockhopper      | 3000000 |   -0.69 |
| Rockhopper      | PULPO           | 3000000 |    0.87 |
| Slumbot         | PULPO           | 3000000 |    0.33 |
| Slumbot         | GGValuta        | 3000000 |   -0.23 |
| Slumbot         | Hyperborean_iro | 3000000 |   -0.30 |
| Slumbot         | Rockhopper      | 3000000 |   -0.67 |
| Rockhopper      | Hyperborean_iro | 3000000 |    0.29 |
| Rockhopper      | GGValuta        | 3000000 |    0.69 |
| Rockhopper      | Slumbot         | 3000000 |    0.67 |
| PULPO           | GGValuta        | 3000000 |   -0.25 |
| PULPO           | Hyperborean_iro | 3000000 |   -0.16 |
| Hyperborean_iro | Slumbot         | 3000000 |    0.30 |
| PULPO           | Slumbot         | 3000000 |   -0.33 |
| PULPO           | Rockhopper      | 3000000 |   -0.87 |
| Arnold2         | GGValuta        |  600000 |   -3.19 |
| Arnold2         | GS6_iro         |  600000 |   -1.25 |
| Arnold2         | GS6_tbr         |  600000 |   -1.23 |
| ASVP            | Slumbot         |  600000 |  -56.17 |
| ASVP            | Sartre          |  600000 |  -76.19 |
| Arnold2         | PLICAS          |  600000 |   19.09 |
| Arnold2         | Sartre          |  600000 |   -1.52 |
| Arnold2         | Slumbot         |  600000 |   -3.41 |
| GGValuta        | ASVP            |  600000 |   46.05 |
| Arnold2         | longhorn        |  600000 |  139.58 |
| GGValuta        | Arnold2         |  600000 |    3.19 |
| Arnold2         | Hyperborean_iro |  600000 |   -3.24 |
| Arnold2         | Jester          |  600000 |    2.47 |
| Arnold2         | Hyperborean_tbr |  600000 |   -3.55 |
| GGValuta        | Hyperborean_tbr |  600000 |   -0.33 |
| GGValuta        | GS6_tbr         |  600000 |    3.12 |
| GGValuta        | GS6_iro         |  600000 |    3.10 |
| Arnold2         | ASVP            |  600000 |   47.53 |
| ASVP            | longhorn        |  600000 |  183.63 |
| GGValuta        | LittleRock      |  600000 |    7.68 |