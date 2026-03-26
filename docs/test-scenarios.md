# Test Scenarios — Multi-Source Correlation

Based on REAL data in DB (bank txs from Powens sandbox + email txs from fake emails).

## Sources
1. **Bank** (Powens) — 153 transactions from sandbox
2. **Email** (AI pipeline) — 52 transactions from fake emails
3. **Stripe** — test account connected
4. **PayPal** — sandbox connected
5. **Mollie** — test account connected

## Scenarios

### S01: SNCF — Bank + Email + Stripe
- **Bank**: SNCF -26.48 EUR, 2026-03-31, deferred_card
- **Email**: SNCF Connect 26.48 EUR, order, 2026-03-31
- **Stripe**: Charge 2648 cents EUR, "SNCF ticket" (to create)
- **Expected**: Bank ↔ Email matched. Stripe = seller-side of same payment.

### S02: Alloresto — Bank + Email, fuzzy vendor, no provider
- **Bank**: ALLORESTO.FR PARIS -85.75 EUR, 2026-03-31
- **Email**: Alloresto.fr 85.75 EUR, order, 2026-03-31
- **Provider**: None (card payment)
- **Expected**: Bank ↔ Email fuzzy vendor match.

### S03: Uber Eats — Bank + Email exact match
- **Bank**: UBER EATS -82.14 EUR, 2026-03-20
- **Email**: Uber Eats 82.14 EUR, receipt, 2026-03-20
- **Expected**: Bank ↔ Email exact match.

### S04: Monoprix — Bank + Email partial (some have emails, some don't)
- **Bank**: MONOPRIX -68.35 EUR, 2026-03-16 → **has email** (Monoprix 68.35€)
- **Bank**: MONOPRIX -42.00 EUR, 2026-03-31 → **no email** (supermarket, no receipt)
- **Bank**: MONOPRIX -60.01 EUR, 2026-03-22 → **no email**
- **Expected**: First matched, others bank-only. Enriched as "groceries/personal".

### S05: Stripe subscription — Free Mobile
- **Stripe**: Charge 1999 cents EUR, "Free Mobile subscription" (to create)
- **Email**: Free Mobile 19.99 EUR, invoice, 2026-03-24
- **Bank**: Not directly visible (Stripe payout later)
- **Expected**: Stripe ↔ Email match by amount+date.

### S06: PayPal e-commerce — Amazon
- **PayPal**: Transaction 49.99 EUR, "Amazon.fr purchase" (from sandbox)
- **Email**: Amazon.fr 49.99 EUR, order, 2026-03-23
- **Bank**: No direct entry (PayPal holds funds)
- **Expected**: PayPal ↔ Email match by amount+date.

### S07: Mollie payment — Fnac order
- **Mollie**: Payment 279.99 EUR, "Fnac Order #F-001" (to create via API)
- **Email**: Fnac 279.99 EUR, order, 2026-03-15
- **Bank**: No direct entry (Mollie settlement later)
- **Expected**: Mollie ↔ Email match.

### S08: Stripe payout → Bank credit
- **Stripe**: Payout 500.00 EUR, arrival 2026-03-28 (to create)
- **Bank**: STRIPE 500.00 EUR credit, 2026-03-28 (fake bank tx to create)
- **Expected**: Stripe payout ↔ Bank credit match.

### S09: Refund via Stripe
- **Stripe**: Refund -25.00 EUR on a charge (to create)
- **Bank**: STRIPE REFUND 25.00 EUR credit (fake bank tx to create)
- **Email**: No refund email
- **Expected**: Stripe refund ↔ Bank credit. No email.

### S10: Failed payment — Stripe + Email
- **Stripe**: Failed charge 67.82 EUR (using pm_card_chargeDeclined) (to create)
- **Email**: EDF 67.82 EUR, invoice, 2026-03-23 (exists in DB)
- **Bank**: No entry (payment failed)
- **Expected**: Stripe failed + Email exists. No bank match.

### S11: Multi-currency — PayPal USD
- **PayPal**: Transaction 75.00 USD
- **Bank**: Original value -75.00 USD, converted ~63.50 EUR, original_currency=USD
- **Expected**: Cross-currency match via original_value.

### S12: Recurring — Google *Budgea (Stripe subscription)
- **Bank**: GOOGLE *BUDGEA -93.90 EUR (Feb 14), -93.27 EUR (Feb 02), -83.47 EUR (Jan 24)
- **Stripe**: 3 subscription invoices ~93 EUR/month (to create)
- **Expected**: Bank recurring detected. Stripe subscription ↔ Bank pattern.

### S13: Email-only — Netflix (different card)
- **Email**: Netflix 13.49 EUR, subscription, 2026-03-20
- **Bank**: No match (paid by a card not connected to Powens)
- **Provider**: None
- **Expected**: Email transaction standalone.

### S14: Bank-only — Docteur (no email)
- **Bank**: DOCTEUR -96.93 EUR, 2026-03-31
- **Email**: None (medical consultation, no email receipt)
- **Provider**: None
- **Expected**: Bank transaction standalone. Enriched as "healthcare".

### S15: Stripe fee (internal)
- **Stripe**: Balance tx type=stripe_fee, -1.50 EUR
- **Bank**: No entry (deducted from payout)
- **Email**: None
- **Expected**: Stripe fee tracked. Reduces net payout.

## Expected Results Matrix

| # | Bank | Email | Stripe | PayPal | Mollie | Result |
|---|------|-------|--------|--------|--------|--------|
| S01 | -26.48 SNCF | 26.48 SNCF | charge 26.48 | | | 3-way match |
| S02 | -85.75 ALLORESTO | 85.75 Alloresto | | | | Bank↔Email fuzzy |
| S03 | -82.14 UBER EATS | 82.14 Uber Eats | | | | Bank↔Email exact |
| S04 | -68.35 MONOPRIX | 68.35 Monoprix | | | | Partial match |
| S05 | | 19.99 Free Mobile | charge 19.99 | | | Stripe↔Email |
| S06 | | 49.99 Amazon | | tx 49.99 | | PayPal↔Email |
| S07 | | 279.99 Fnac | | | pay 279.99 | Mollie↔Email |
| S08 | +500 STRIPE | | payout 500 | | | Stripe↔Bank |
| S09 | +25 STRIPE REFUND | | refund -25 | | | Stripe↔Bank |
| S10 | | 67.82 EDF | failed 67.82 | | | Failed, no bank |
| S11 | -63.50 (orig $75) | | | tx $75 | | Cross-currency |
| S12 | -93.xx GOOGLE*BUDGEA | | sub ~93/mo | | | Recurring |
| S13 | | 13.49 Netflix | | | | Email standalone |
| S14 | -96.93 DOCTEUR | | | | | Bank standalone |
| S15 | | | fee -1.50 | | | Stripe fee |
