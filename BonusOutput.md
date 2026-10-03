## Standard: conflict handling

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Advanced conflict off | 1339 | 19454 | 64.3% | 66.8% | 261 | 0 |
| Advanced conflict on | 1350 | 19842 | 100.0% | 100.0% | 275 | 0 |

## Stress: conflict handling

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Advanced conflict off | 682 | 16441 | 66.7% | 75.0% | 174 | 1 |
| Advanced conflict on | 742 | 16664 | 100.0% | 100.0% | 205 | 1 |

