# Nova Ledger

**Plateforme intelligente de rapprochement comptable multi-sources, propulsee par IA.**

Nova Ledger connecte vos emails, banques, et fournisseurs de paiement pour automatiser le rapprochement de transactions grace a un pipeline d'agents IA (Claude).

> **Ce projet est en cours de developpement.** De nombreux bugs sont encore presents. L'application est en phase de test et d'optimisation. Les contributions et retours sont les bienvenus.

---

## Fonctionnalites

- **Connexions multi-sources** : emails (Gmail, Outlook), banques (Powens, Qonto, import CSV/OFX), paiements (Stripe, PayPal, Mollie, GoCardless, Fintecture, PayPlug, SumUp, Alma), facturation (Evoliz, Pennylane, VosFactures), e-commerce (Shopify, PrestaShop, WooCommerce), Chorus Pro
- **Pipeline IA agentique** : ingestion, enrichissement, correlation, classification et verification automatiques des transactions
- **Ledger unifie** : vue consolidee de toutes les transactions avec rapprochement intelligent
- **Detection de recurrence** : identification automatique des abonnements et paiements recurrents
- **Import bancaire** : upload de fichiers CSV, OFX, QFX pour import manuel
- **Interface React** : frontend moderne avec Vite, React 19, TypeScript

## Architecture

```
Backend :  Django 5 + Django REST Framework + SimpleJWT
Frontend : React 19 + Vite + TypeScript + Zustand
IA :       Claude (Anthropic) — Haiku pour les taches rapides, Sonnet pour le jugement comptable
BDD :      SQLite (dev) — PostgreSQL prevu pour la production
```

## Installation

### Pre-requis

- Python 3.11+
- Node.js 20+
- Cles API (voir `.env.example`)

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend-vite
npm install
npm run dev
```

### Configuration

Copier `.env.example` vers `.env` et renseigner vos cles API :

```bash
cp .env.example .env
```

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Django 5, DRF, django-allauth, dj-rest-auth |
| Frontend | React 19, Vite, TypeScript, Zustand, Recharts |
| Auth | JWT (SimpleJWT), OAuth2 (Google, Microsoft) |
| IA | Anthropic Claude (Haiku + Sonnet) |
| Paiements | Stripe, PayPal, Mollie, GoCardless, etc. |
| Banque | Powens API, import CSV/OFX |

## Statut

Ce projet est un **work in progress**. Fonctionnalites en cours de developpement et d'optimisation :

- [ ] Stabilisation du pipeline IA
- [ ] Migration PostgreSQL
- [ ] Tests end-to-end
- [ ] Deploiement production
- [ ] Documentation API

## Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de details.
