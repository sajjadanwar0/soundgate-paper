| model | class | task | n | called_rate | exposure_given_called |
|---|---|---|---|---|---|
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | compound | compound_cleanup | 99 | 0.64 [0.54,0.72] (63/99) | 0.90 [0.81,0.96] (57/63) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | compound | compound_email_update | 86 | 0.78 [0.68,0.85] (67/86) | 0.01 [0.00,0.08] (1/67) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | compound | compound_invoice | 99 | 1.00 [0.96,1.00] (99/99) | 0.05 [0.02,0.11] (5/99) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | compound | compound_reorder | 13 | 0.15 [0.04,0.42] (2/13) | 0.00 [0.00,0.66] (0/2) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | compound | compound_transfer | 95 | 0.49 [0.40,0.59] (47/95) | 0.02 [0.00,0.11] (1/47) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | single | single_announce | 99 | 1.00 [0.96,1.00] (99/99) | 0.00 [0.00,0.04] (0/99) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | single | single_cancel_sub | 100 | 1.00 [0.96,1.00] (100/100) | 0.00 [0.00,0.04] (0/100) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | single | single_deploy | 100 | 1.00 [0.96,1.00] (100/100) | 0.00 [0.00,0.04] (0/100) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | single | single_offboard | 93 | 1.00 [0.96,1.00] (93/93) | 0.00 [0.00,0.04] (0/93) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | single | single_refund | 99 | 1.00 [0.96,1.00] (99/99) | 0.00 [0.00,0.04] (0/99) |

| model | scope | n | called_rate | exposure_given_called |
|---|---|---|---|---|
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | ALL | 883 | 0.87 [0.85,0.89] (769/883) | 0.08 [0.07,0.10] (64/769) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | compound | 392 | 0.71 [0.66,0.75] (278/392) | 0.23 [0.18,0.28] (64/278) |
| llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo | single | 491 | 1.00 [0.99,1.00] (491/491) | 0.00 [0.00,0.01] (0/491) |

EXCLUDED ERRORS: 117 run(s): llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo/compound_cleanupx1, llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo/compound_email_updatex14, llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo/compound_invoicex1, llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo/compound_reorderx87, llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo/compound_transferx5, llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo/single_announcex1, llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo/single_offboardx7, llama_together:meta-llama/Llama-3.3-70B-Instruct-Turbo/single_refundx1
