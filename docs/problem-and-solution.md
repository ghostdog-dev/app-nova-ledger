# Nova Ledger — Problème et Solution

## Le Problème

Un indépendant, freelance ou PME en France utilise typiquement **3 à 8 services financiers différents** pour gérer son activité :

- **Encaissements** : Stripe pour les paiements carte, Fintecture pour les virements SEPA B2B, PayPal, GoCardless pour les prélèvements...
- **Facturation** : Evoliz, Pennylane, Sellsy, VosFactures...
- **Fournisseurs** : factures reçues par email, commandes sur différentes plateformes
- **TPE physiques** : SumUp, PayPlug, Zettle...
- **Banque** : Qonto, BNP, Société Générale...

### Le cycle mensuel douloureux

Chaque mois, l'entrepreneur doit :

1. **Se connecter à chaque service** manuellement (5 à 8 dashboards différents)
2. **Exporter les données** (CSV, PDF, ou copier-coller)
3. **Croiser les données** entre services — faire correspondre un paiement Stripe de 47.20€ avec la facture Evoliz #2024-0042
4. **Calculer les commissions** : Stripe prélève 1.4% + 0.25€, PayPal prélève 2.9% + 0.35€, etc.
5. **Construire les écritures comptables** ou les préparer pour l'expert-comptable
6. **Gérer les cas spéciaux** : remboursements, litiges, virements en attente, écarts de change

**Temps perdu estimé : 5 à 15 heures par mois.** Un freelance perd en moyenne 260 heures/an en tâches administratives.

### Ce que le marché ne résout pas

| Gap | Détail |
|-----|--------|
| **Pas de matching cross-source abordable** | Pennylane connecte 200+ outils mais ne fait pas le rapprochement automatique "paiement Stripe = facture Evoliz". Les solutions qui le font (Ledge, Optimus) sont enterprise-only (pricing sur devis). |
| **Les PSP sont des angles morts comptables** | Les experts-comptables traitent Stripe/PayPal comme des comptes bancaires séparés et gèrent manuellement commissions, remboursements, chargebacks. |
| **L'email reste inexploité pour la corrélation** | iPaidThat parse les emails pour collecter les factures, mais ne corrèle pas avec les paiements PSP. |
| **Aucune vue unifiée** | Pas de dashboard unique montrant tous les flux du mois avec ce qui est matché vs ce qui reste à réconcilier. |
| **Aucune solution abordable** | Les solutions de réconciliation multi-PSP sont à pricing enterprise. Les outils comptables ne font pas de matching cross-source. Rien à 10-30€/mois pour un freelance. |

---

## La Solution : Nova Ledger

Nova Ledger est un **moteur de réconciliation multi-sources** qui se place entre la collecte de données (APIs des services) et le logiciel comptable / l'expert-comptable.

### Principe

L'utilisateur connecte ses services en fournissant ses tokens/clés API. Nova Ledger :

1. **Récupère automatiquement** les données de chaque service via API
2. **Corrèle les données** entre sources (paiement ↔ facture ↔ email ↔ ligne bancaire)
3. **Présente une vue unifiée** de tous les flux financiers
4. **Identifie les écarts** et les éléments non réconciliés
5. **Prépare les exports comptables** (FEC, PCG, TVA)

### Architecture de corrélation sans agrégation bancaire

```
Factures émises (Evoliz/Pennylane)  ←───┐
                                         ├── MATCHING ──→ Rapprochement
Paiements reçus (Stripe/Fintecture/      │                automatique
GoCardless/SumUp/PayPlug/Mollie...)  ←───┤
                                         │
Factures fournisseurs (email/OCR)  ←─────┤
                                         │
Compte pro (Qonto API / CSV import)  ←───┘  ← source de vérité
```

**Chaque événement financier laisse des traces dans plusieurs services.** Un même paiement client apparaît :
- Comme un charge dans Stripe (montant, commission, client)
- Comme une facture payée dans Evoliz (numéro, TVA, lignes)
- Comme un email de confirmation dans Gmail
- Comme une ligne de crédit sur le compte Qonto (après settlement)

En croisant ces 4 preuves, Nova Ledger reconstruit le flux complet **sans jamais avoir besoin d'un agrégateur bancaire coûteux**.

### Pourquoi pas d'agrégation bancaire ?

Les agrégateurs bancaires (Powens, Tink, Bridge, Salt Edge) coûtent entre **500€ et 2000€/mois** pour un accès API. Ce coût est prohibitif pour un produit ciblant des indépendants et TPE/PME. De plus, l'accès bancaire nécessite souvent des licences réglementaires (AISP/PISP).

**Alternative choisie :**
- **Qonto API** (gratuit avec compte) pour les utilisateurs Qonto
- **Import CSV/OFX/QIF** en fallback pour toutes les banques françaises
- **Corrélation multi-sources** : si on a les données de tous les maillons du flux commercial, les données bancaires brutes deviennent complémentaires et non indispensables

---

## Services intégrés et roadmap

### Déjà intégrés ✅

| Service | Type | Auth | Données |
|---------|------|------|---------|
| **Stripe** | Paiement carte | API key (sk_xxx) | Balance transactions, charges, payouts, invoices, subscriptions, disputes |
| **PayPal** | Multi-paiement | OAuth2 client credentials | Transactions, invoices, disputes |
| **Mollie** | Multi-paiement | API key (test_/live_) | Payments, refunds, settlements, invoices |
| **Gmail** | Email | OAuth2 (Google) | Emails financiers (reçus, confirmations) |
| **Outlook** | Email | OAuth2 (Microsoft) | Emails financiers (reçus, confirmations) |

### Phase 1 — Encaissements 🔨

| Service | Type | Auth | Données | Cible |
|---------|------|------|---------|-------|
| **Fintecture** | Virement SEPA B2B | app_id + app_secret | Paiements initiés, sessions, virements | PME B2B |
| **GoCardless** | Prélèvement SEPA | Bearer token | Payments, mandates, subscriptions, payouts | SaaS, abonnements |
| **PayPlug** | Carte (FR) | API key (sk_live_) | Payments, refunds | PME françaises |
| **SumUp** | TPE mobile | API key / OAuth2 | Transactions, payouts | Micro-entrepreneurs |

### Phase 2 — Facturation 📄

| Service | Type | Auth | Données | Cible |
|---------|------|------|---------|-------|
| **Evoliz** | Facturation FR | JWT (company_id + keys) | Factures émises/reçues, paiements, clients | TPE/PME |
| **Pennylane** | Compta + facturation | Bearer token / OAuth2 | Factures client+fournisseur, paiements, compta | Startups, PME |
| **VosFactures** | Facturation | API token | Factures, clients, paiements, stock | Budget-friendly |

### Phase 3 — Source bancaire 🏦

| Service | Type | Auth | Données | Cible |
|---------|------|------|---------|-------|
| **Qonto** | Néobanque pro | API key / OAuth2 | Transactions, virements, relevés | Startups, freelances |
| **Import CSV/OFX** | Fichier bancaire | N/A | Transactions (toutes banques FR) | Universel |

### Phase 4 — Enrichissement 🔗

| Service | Type | Données |
|---------|------|---------|
| **E-commerce** (PrestaShop, Shopify, WooCommerce) | Commandes, produits, clients |
| **Alma** | BNPL — échéanciers de paiement 3x/4x |
| **Chorus Pro** | Factures secteur public (gratuit, gouv) |
| **Mindee OCR** | Extraction IA de factures PDF |
