# Ground Truth — Expected Transactions from 500 emails

Based on manual analysis of the 31 transactional emails for user 13.

## Expected Transactions (17 distinct financial events)

| # | Vendor | Type | Amount | Currency | Date | Order/Invoice | Items | Emails |
|---|--------|------|--------|----------|------|---------------|-------|--------|
| 1 | Anthropic, PBC | receipt | 199.31 | EUR | 2026-02-23 | inv#2872-3997-3755 | Max plan 20x | 477 |
| 2 | Shopify | payment (failed) | 1.00 | EUR | 2026-02-24 | | LassegueArt billing | 473 |
| 3 | Sumeria | payment | 1.50 | EUR | 2026-02-26 | | Bank transfer | 438 |
| 4 | Shopify | invoice | 1.00 | EUR | 2026-02-26 | inv#493611453 | LassegueArt invoice | 436 |
| 5 | Hostinger | receipt | 20.58 | EUR | 2026-02-27 | inv#H_38671461 | .COM Domain nova-ledger, Privacy Protection, ICANN fee, .FR Domain | 396 |
| 6 | Anthropic, PBC | receipt | 6.00 | USD | 2026-02-28 | inv#2151-2100-3871 | One-time credit purchase | 361 |
| 7 | Fnac | order | 511.98 | EUR | 2026-02-28 | ord#H3MOTU5KO7J6I | Pack Nintendo Switch 2 + Pokémon Z-A | 360 |
| 8 | Proton | subscription | 1.00 | EUR | 2026-03-01 | | Proton VPN | 354 |
| 9 | Fnac | order | 511.98 | EUR | 2026-03-01 | ord#HAX7UD6CYMM6I | Pack Nintendo Switch 2 + Pokémon Z-A | 339 |
| 10 | Fnac | cancellation | 459.34 | EUR | 2026-03-01 | ord#HAX7UD6CYMM6I | Pack Nintendo Switch 2 cancelled | 333, 334 |
| 11 | Fnac | order+cancellation | 511.98 | EUR | 2026-03-01 | ord#9CWXP2VD73N6I | (ordered then fully cancelled) | 351, 340, 352 |
| 12 | Amazon Prime | payment (failed) | 6.99 | EUR | 2026-03-06 | | Subscription billing issue | 261 |
| 13 | Nintendo | receipt | 29.99 | EUR | 2026-03-08 | inv#FR-52323639705 | Pokémon Legends Z-A, Holo X&Y Outfits | 241, 242 |
| 14 | Cursor | payment (failed) | 21.42 | EUR | 2026-03-08 | | Subscription failed | 239 |
| 15 | SHEIN | order | 108.34 | EUR | 2026-03-22 | ord#USO1XN03W000000M2UF | Poncho, bonnet, leggings (8 items) | 53, 6 |
| 16 | Anthropic, PBC | receipt | 108.00 | EUR | 2026-03-24 | inv#2774-3770-5483 | Max plan 5x | 24, 25, 26, 28 |
| 17 | Anthropic, PBC | receipt (failed) | 24.00 | USD | 2026-03-25 | inv#2016-2909-2117 | One-time credit | 507, 508 |

## Emails NOT transactional (correctly ignored)
- 273, 293 (Apple account migration — no money moved)
- 54, 251 (Google Workspace cancellation — free tier, no charge)
- 32 (Anthropic €216 failed — this is a SEPARATE failed payment, should be tx #16b or merged into #16)

## Correlation Rules Applied
- Emails 24+25+26+28 → single Anthropic receipt #16 (receipt + welcome + 2 failed attempts = same subscription event on same day)
- Emails 507+508 → single Anthropic tx #17 (receipt + failed = same credit purchase)
- Emails 53+6 → single SHEIN order #15 (order confirmation + shipping)
- Emails 241+242 → single Nintendo receipt #13 (purchase + transaction statement)
- Emails 333+334 → single Fnac cancellation #10 (2 cancellation emails, same order)
- Emails 351+340+352 → single Fnac order+cancel #11 (order + 2 cancellations, same order)
- Emails 339 alone → Fnac order #9 (distinct order number)
- Emails 360 alone → Fnac order #7 (distinct order number)

## Key Observations
- 31 transactional emails → 17 distinct transactions (correlation reduces 45%)
- 3 orders have the SAME amount (511.98€) but DIFFERENT order numbers → must stay separate
- Failed payments are real financial events → keep them
- Anthropic has 4 emails on 2026-03-24 but they're ONE subscription event
- SHEIN shipping (email 6) has no amount but belongs to SHEIN order (email 53)
