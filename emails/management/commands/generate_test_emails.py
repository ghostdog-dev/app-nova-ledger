"""
Generate fake emails matching real bank transaction data for correlation testing.

Creates ~80 emails:
- ~40 matching bank transactions (receipts, confirmations)
- ~15 non-matching transactional emails (different payment method, gift cards)
- ~25 non-transactional (newsletters, marketing, notifications)
"""

import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from banking.models import BankTransaction
from emails.models import Email


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid():
    return f"fake_{uuid.uuid4().hex[:16]}"


def _make_email(user_id, *, from_address, from_name, subject, snippet,
                date, has_attachments=False, has_list_unsubscribe=False,
                status="new", labels=None):
    """Build an Email instance (not saved)."""
    return Email(
        user_id=user_id,
        provider="google",
        message_id=_uid(),
        from_address=from_address,
        from_name=from_name,
        subject=subject,
        snippet=snippet,
        date=date,
        labels=labels or ["INBOX"],
        has_attachments=has_attachments,
        has_list_unsubscribe=has_list_unsubscribe,
        status=status,
    )


def _dt(date, hour=10, minute=0):
    """Convert a date to a timezone-aware datetime."""
    return timezone.make_aware(
        timezone.datetime(date.year, date.month, date.day, hour, minute)
    )


def _ref():
    """Random reference / order number."""
    return f"{random.randint(100000, 999999)}"


# ---------------------------------------------------------------------------
# Vendor email generators
# ---------------------------------------------------------------------------

def _sncf_email(user_id, tx):
    """SNCF train ticket confirmation."""
    amt = abs(tx.value)
    ref = f"QJ{_ref()}"
    destinations = ["Lyon", "Marseille", "Bordeaux", "Lille", "Strasbourg",
                    "Nantes", "Toulouse", "Rennes", "Nice", "Montpellier"]
    dest = random.choice(destinations)
    date = _dt(tx.date, hour=random.randint(6, 9), minute=random.randint(0, 59))
    # Some emails arrive 1 day before bank debit (processing delay)
    if random.random() < 0.3:
        date -= timedelta(days=1)

    subjects = [
        f"Confirmation de votre reservation - Trajet Paris > {dest}",
        f"e-billet - Votre voyage du {tx.date.strftime('%d/%m/%Y')}",
        f"Votre reservation SNCF - Ref {ref}",
    ]
    subject = random.choice(subjects)
    snippet = (
        f"Bonjour, Votre reservation a bien ete enregistree. "
        f"Ref: {ref} - Paris Gare de Lyon > {dest} - "
        f"Depart le {tx.date.strftime('%d/%m/%Y')} - "
        f"Montant: {amt:.2f} EUR. Retrouvez votre e-billet dans l'application SNCF Connect."
    )
    return _make_email(
        user_id, from_address="confirmation@oui.sncf", from_name="SNCF Connect",
        subject=subject, snippet=snippet, date=date, has_attachments=True,
    )


def _uber_eats_email(user_id, tx):
    """Uber Eats receipt."""
    amt = abs(tx.value)
    restaurants = ["Sushi Shop", "Big Fernand", "PNY Burger", "Bagelstein",
                   "Five Guys", "Pokawa", "Cojean"]
    restaurant = random.choice(restaurants)
    date = _dt(tx.date, hour=random.randint(12, 21), minute=random.randint(0, 59))

    subject = "Votre recu Uber Eats"
    snippet = (
        f"Total: {amt:.2f} EUR - Livraison depuis {restaurant}. "
        f"Commande livree le {tx.date.strftime('%d/%m/%Y')}. "
        f"Frais de livraison: 2.99 EUR. Merci d'avoir commande avec Uber Eats."
    )
    return _make_email(
        user_id, from_address="uber.eats@uber.com", from_name="Uber Eats",
        subject=subject, snippet=snippet, date=date,
    )


def _monoprix_email(user_id, tx):
    """Monoprix receipt email (loyalty card)."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(10, 20), minute=random.randint(0, 59))

    subject = "Votre ticket de caisse Monoprix"
    snippet = (
        f"Montant: {amt:.2f} EUR - Carte ****1234 - "
        f"Magasin Monoprix Paris 10eme - "
        f"Date: {tx.date.strftime('%d/%m/%Y')}. "
        f"Vous avez cumule 12 points fidelite sur cet achat."
    )
    return _make_email(
        user_id, from_address="fidelite@monoprix.fr", from_name="Monoprix",
        subject=subject, snippet=snippet, date=date, has_attachments=True,
    )


def _google_budgea_email(user_id, tx):
    """Google Cloud / Budgea invoice."""
    amt = abs(tx.value)
    inv = f"INV-{random.randint(2026000, 2026999)}"
    date = _dt(tx.date, hour=3, minute=random.randint(0, 59))

    subjects = [
        f"Your Google Cloud invoice #{inv}",
        f"Votre facture Google - {inv}",
    ]
    subject = random.choice(subjects)
    snippet = (
        f"Invoice #{inv} - Amount: {amt:.2f} EUR - "
        f"Google Cloud Platform / Budgea API - "
        f"Period: {tx.date.strftime('%m/%Y')}. "
        f"Payment processed via card ending 1234."
    )
    return _make_email(
        user_id, from_address="payments-noreply@google.com",
        from_name="Google Payments", subject=subject, snippet=snippet,
        date=date, has_attachments=True,
    )


def _alloresto_email(user_id, tx):
    """Alloresto.fr (Just Eat) order confirmation."""
    amt = abs(tx.value)
    order = _ref()
    date = _dt(tx.date, hour=random.randint(11, 21), minute=random.randint(0, 59))
    # Email from "Alloresto" but bank shows "ALLORESTO.FR PARIS" -> fuzzy match
    if random.random() < 0.3:
        date -= timedelta(days=1)

    subject = f"Commande confirmee - #{order}"
    snippet = (
        f"Votre commande #{order} a ete confirmee. "
        f"Total: {amt:.2f} EUR. "
        f"Livraison estimee: 30-45 min. "
        f"Restaurant: {random.choice(['Pizza Hut', 'KFC', 'Dominos', 'Wok Street'])} - "
        f"Adresse: 42 rue du Faubourg Saint-Denis, Paris 10."
    )
    return _make_email(
        user_id, from_address="confirmation@alloresto.fr",
        from_name="Alloresto.fr", subject=subject, snippet=snippet, date=date,
    )


def _mcdo_email(user_id, tx):
    """McDonald's order confirmation (rare — most card swipes don't generate emails)."""
    amt = abs(tx.value)
    ref = _ref()
    date = _dt(tx.date, hour=random.randint(11, 22), minute=random.randint(0, 59))

    subject = f"Votre commande McDonald's #{ref}"
    snippet = (
        f"Commande #{ref} - Total: {amt:.2f} EUR - "
        f"McDonald's Paris Gare de l'Est - "
        f"Commande a emporter. Merci de votre visite!"
    )
    return _make_email(
        user_id, from_address="commande@mcdonalds.fr",
        from_name="McDonald's France", subject=subject, snippet=snippet, date=date,
    )


def _halls_beer_email(user_id, tx):
    """Hall's Beer bar receipt (occasional email if loyalty program)."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(18, 23), minute=random.randint(0, 59))

    subject = "Votre addition - Hall's Beer"
    snippet = (
        f"Merci pour votre visite chez Hall's Beer! "
        f"Montant: {amt:.2f} EUR - CB ****1234 - "
        f"Le {tx.date.strftime('%d/%m/%Y')}. "
        f"A bientot!"
    )
    return _make_email(
        user_id, from_address="contact@hallsbeer.fr",
        from_name="Hall's Beer Paris", subject=subject, snippet=snippet, date=date,
    )


def _franprix_email(user_id, tx):
    """Franprix receipt email."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(8, 21), minute=random.randint(0, 59))

    subject = "Votre ticket Franprix"
    snippet = (
        f"Montant: {amt:.2f} EUR - Franprix Paris 10 - "
        f"Le {tx.date.strftime('%d/%m/%Y')}. "
        f"Points fidelite: +8 points."
    )
    return _make_email(
        user_id, from_address="ticket@franprix.fr",
        from_name="Franprix", subject=subject, snippet=snippet, date=date,
    )


def _docteur_email(user_id, tx):
    """Doctor visit / Doctolib confirmation."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(8, 17), minute=random.randint(0, 59))
    if random.random() < 0.3:
        date -= timedelta(days=1)

    subject = "Recapitulatif de votre consultation"
    snippet = (
        f"Consultation du {tx.date.strftime('%d/%m/%Y')} - "
        f"Dr. Martin - Medecine generale - "
        f"Honoraires: {amt:.2f} EUR - "
        f"Tiers payant applique. Pensez a envoyer votre feuille de soins."
    )
    return _make_email(
        user_id, from_address="noreply@doctolib.fr",
        from_name="Doctolib", subject=subject, snippet=snippet, date=date,
    )


def _bootlagers_email(user_id, tx):
    """The Bootlagers bar receipt."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(19, 23), minute=random.randint(0, 59))

    subject = "Merci pour votre visite - The Bootlagers"
    snippet = (
        f"The Bootlagers Paris vous remercie! "
        f"Addition: {amt:.2f} EUR - "
        f"Le {tx.date.strftime('%d/%m/%Y')}. A tres bientot!"
    )
    return _make_email(
        user_id, from_address="hello@thebootlagers.com",
        from_name="The Bootlagers Paris", subject=subject, snippet=snippet, date=date,
    )


# ---------------------------------------------------------------------------
# Non-matching transactional emails (no bank tx counterpart)
# ---------------------------------------------------------------------------

def _nonmatching_transactional(user_id):
    """Emails for purchases paid via gift cards, other cards, etc."""
    base = timezone.now()
    emails = []

    # Amazon order paid with gift card
    emails.append(_make_email(
        user_id, from_address="auto-confirm@amazon.fr", from_name="Amazon.fr",
        subject="Confirmation de commande #402-7291845-3928164",
        snippet=(
            "Bonjour, Nous vous confirmons la reception de votre commande "
            "#402-7291845-3928164. Montant: 49.99 EUR (cheque-cadeau). "
            "Livraison estimee: 28 mars 2026. Articles: Clavier sans fil Logitech K380."
        ),
        date=base - timedelta(days=3, hours=2), has_attachments=False,
    ))

    # Netflix subscription on different card
    emails.append(_make_email(
        user_id, from_address="info@account.netflix.com", from_name="Netflix",
        subject="Votre facture Netflix - Mars 2026",
        snippet=(
            "Votre abonnement Netflix Standard a ete renouvele. "
            "Montant: 13.49 EUR. Prochaine facturation: 20/04/2026. "
            "Carte Visa ****5678."
        ),
        date=base - timedelta(days=7, hours=5),
    ))

    # Spotify receipt not in bank data
    emails.append(_make_email(
        user_id, from_address="no-reply@spotify.com", from_name="Spotify",
        subject="Votre recu Spotify Premium",
        snippet=(
            "Merci pour votre paiement. Spotify Premium - 9.99 EUR/mois. "
            "Prochaine facturation: 15/04/2026. "
            "Moyen de paiement: PayPal (jean@email.com)."
        ),
        date=base - timedelta(days=12, hours=8),
    ))

    # Apple App Store purchase
    emails.append(_make_email(
        user_id, from_address="no_reply@email.apple.com", from_name="Apple",
        subject="Votre recu d'achat Apple",
        snippet=(
            "Recu d'achat - iCloud+ 50 Go: 0.99 EUR/mois. "
            "Identifiant Apple: jean@icloud.com. "
            "Date de facturation: 15/03/2026."
        ),
        date=base - timedelta(days=11, hours=3),
    ))

    # Fnac order (paid in store, email for order tracking)
    emails.append(_make_email(
        user_id, from_address="commande@fnac.com", from_name="Fnac",
        subject="Votre commande Fnac #CF2026031587",
        snippet=(
            "Commande #CF2026031587 - Click & Collect Fnac Forum des Halles. "
            "Ecouteurs Sony WH-1000XM5: 279.99 EUR. "
            "Statut: Pret a retirer. Presentez ce mail en magasin."
        ),
        date=base - timedelta(days=5, hours=6), has_attachments=False,
    ))

    # Deliveroo receipt (not in bank - different card)
    emails.append(_make_email(
        user_id, from_address="no-reply@deliveroo.fr", from_name="Deliveroo",
        subject="Votre commande Deliveroo",
        snippet=(
            "Merci pour votre commande! Total: 24.50 EUR. "
            "Livraison depuis Pho Tai - 2 Bo Bun, 1 Nem. "
            "Frais de livraison: 1.99 EUR."
        ),
        date=base - timedelta(days=8, hours=7),
    ))

    # IKEA online order (not in bank)
    emails.append(_make_email(
        user_id, from_address="noreply@ikea.com", from_name="IKEA",
        subject="Confirmation de commande IKEA #1089234567",
        snippet=(
            "Votre commande #1089234567 a ete confirmee. "
            "Montant total: 156.00 EUR - Paiement en 3x sans frais. "
            "Livraison prevue: 01/04/2026."
        ),
        date=base - timedelta(days=2, hours=4),
    ))

    # Leroy Merlin receipt
    emails.append(_make_email(
        user_id, from_address="contact@leroymerlin.fr",
        from_name="Leroy Merlin",
        subject="Votre ticket de caisse Leroy Merlin",
        snippet=(
            "Montant: 87.40 EUR - Magasin Leroy Merlin Paris 19 - "
            "Peinture blanche 10L, rouleau, scotch. "
            "Date: 18/03/2026."
        ),
        date=base - timedelta(days=8, hours=2), has_attachments=True,
    ))

    # Darty (warranty email, no matching tx)
    emails.append(_make_email(
        user_id, from_address="service@darty.com", from_name="Darty",
        subject="Votre facture Darty - Lave-linge",
        snippet=(
            "Facture #D20260315 - Lave-linge Samsung EcoBubble: 499.00 EUR. "
            "Garantie 2 ans incluse. Extension de garantie disponible. "
            "Livraison le 22/03/2026."
        ),
        date=base - timedelta(days=14, hours=5), has_attachments=True,
    ))

    # Booking.com hotel confirmation (no matching tx yet)
    emails.append(_make_email(
        user_id, from_address="noreply@booking.com", from_name="Booking.com",
        subject="Confirmation de reservation - Hotel Ibis Lyon Centre",
        snippet=(
            "Reservation #4821093756 confirmee. Hotel Ibis Lyon Centre - "
            "1 nuit, 23/04/2026. Prix: 72.00 EUR. "
            "Annulation gratuite jusqu'au 21/04/2026."
        ),
        date=base - timedelta(days=1, hours=9),
    ))

    # Zalando order
    emails.append(_make_email(
        user_id, from_address="service@zalando.fr", from_name="Zalando",
        subject="Votre commande Zalando #ZL10029384",
        snippet=(
            "Commande #ZL10029384 confirmee! "
            "Nike Air Max 90: 139.95 EUR. "
            "Livraison gratuite estimee: 25-28/03/2026. "
            "Retour gratuit sous 100 jours."
        ),
        date=base - timedelta(days=6, hours=3),
    ))

    # Pharmacie receipt
    emails.append(_make_email(
        user_id, from_address="ticket@pharmacie-lafayette.com",
        from_name="Pharmacie Lafayette",
        subject="Votre ticket - Pharmacie Lafayette",
        snippet=(
            "Montant: 18.50 EUR - Pharmacie Lafayette Paris Gare du Nord. "
            "Doliprane 1000mg, Vitamine D3. "
            "Tiers payant: 12.30 EUR rembourse."
        ),
        date=base - timedelta(days=4, hours=6),
    ))

    # Picard surgelés
    emails.append(_make_email(
        user_id, from_address="fidelite@picard.fr", from_name="Picard",
        subject="Votre ticket de caisse Picard",
        snippet=(
            "Montant: 32.80 EUR - Picard Paris Gare de l'Est. "
            "Carte fidelite: 4 points ajoutes. "
            "Prochain bon de reduction a 50 points."
        ),
        date=base - timedelta(days=9, hours=1),
    ))

    # BlaBlaCar ride
    emails.append(_make_email(
        user_id, from_address="noreply@blablacar.fr", from_name="BlaBlaCar",
        subject="Confirmation de reservation BlaBlaCar",
        snippet=(
            "Trajet Paris > Lyon le 05/04/2026 a 14h00. "
            "Prix: 22.00 EUR. Conducteur: Marie L. "
            "Depart: Porte de Bercy."
        ),
        date=base - timedelta(days=1, hours=11),
    ))

    # Free Mobile facture
    emails.append(_make_email(
        user_id, from_address="facture@free-mobile.fr",
        from_name="Free Mobile",
        subject="Votre facture Free Mobile - Mars 2026",
        snippet=(
            "Facture Free Mobile #FM20260301. "
            "Forfait 5G 150Go: 19.99 EUR. "
            "Prelevement le 05/04/2026 sur votre compte bancaire."
        ),
        date=base - timedelta(days=2, hours=7), has_attachments=True,
    ))

    return emails


# ---------------------------------------------------------------------------
# Non-transactional emails (newsletters, promos, notifications)
# ---------------------------------------------------------------------------

def _nontransactional_emails(user_id):
    """Marketing, newsletters, notifications - not purchases."""
    base = timezone.now()
    emails = []

    # SNCF marketing newsletter
    emails.append(_make_email(
        user_id, from_address="newsletter@oui.sncf", from_name="SNCF Connect",
        subject="Offres de printemps - TGV des 29 EUR!",
        snippet=(
            "Profitez de nos offres de printemps! TGV INOUI des 29 EUR. "
            "Paris-Lyon, Paris-Marseille, Paris-Bordeaux. "
            "Offre valable du 01/04 au 30/04/2026. Reservez maintenant!"
        ),
        date=base - timedelta(days=2, hours=8),
        has_list_unsubscribe=True,
    ))

    # Monoprix promo newsletter
    emails.append(_make_email(
        user_id, from_address="newsletter@monoprix.fr", from_name="Monoprix",
        subject="-30% sur tous les produits bio cette semaine!",
        snippet=(
            "Cette semaine chez Monoprix: -30% sur toute la gamme bio! "
            "Fruits, legumes, epicerie. Offre valable du 24 au 30 mars 2026. "
            "Rendez-vous dans votre magasin Monoprix."
        ),
        date=base - timedelta(days=1, hours=6),
        has_list_unsubscribe=True,
    ))

    # Amazon deals newsletter
    emails.append(_make_email(
        user_id, from_address="vente-flash@amazon.fr", from_name="Amazon.fr",
        subject="Ventes Flash du jour - Jusqu'a -50%!",
        snippet=(
            "Decouvrez les ventes flash du jour! TV Samsung 55\" OLED: 799 EUR "
            "au lieu de 1299 EUR. AirPods Pro 2: 229 EUR. "
            "Offres limitees, depechez-vous!"
        ),
        date=base - timedelta(days=3, hours=7),
        has_list_unsubscribe=True,
    ))

    # LinkedIn notification
    emails.append(_make_email(
        user_id, from_address="notifications@linkedin.com", from_name="LinkedIn",
        subject="Jean, vous avez 5 nouvelles notifications",
        snippet=(
            "Marc D. a consulte votre profil. 3 personnes ont aime votre publication. "
            "Nouvelle offre d'emploi: Developpeur Python chez Doctolib."
        ),
        date=base - timedelta(days=1, hours=4),
        has_list_unsubscribe=True,
    ))

    # Google account security
    emails.append(_make_email(
        user_id, from_address="no-reply@accounts.google.com",
        from_name="Google",
        subject="Alerte de securite - Nouvelle connexion detectee",
        snippet=(
            "Nouvelle connexion a votre compte Google depuis un appareil Mac "
            "a Paris, France. Si c'etait bien vous, ignorez ce message. "
            "Sinon, securisez votre compte immediatement."
        ),
        date=base - timedelta(days=5, hours=2),
    ))

    # Doctolib appointment reminder
    emails.append(_make_email(
        user_id, from_address="rappel@doctolib.fr", from_name="Doctolib",
        subject="Rappel: RDV demain avec Dr. Martin",
        snippet=(
            "Rappel de votre rendez-vous. Dr. Martin - Medecine generale. "
            "Demain a 10h30. 15 rue de Paradis, Paris 10. "
            "Pour annuler ou reporter: connectez-vous a Doctolib."
        ),
        date=base - timedelta(days=6, hours=9),
    ))

    # Uber promo
    emails.append(_make_email(
        user_id, from_address="uber@uber.com", from_name="Uber",
        subject="5 EUR offerts sur votre prochaine course!",
        snippet=(
            "Jean, utilisez le code SPRING5 pour obtenir 5 EUR de reduction "
            "sur votre prochaine course Uber. "
            "Valable jusqu'au 31/03/2026. Conditions: course min. 10 EUR."
        ),
        date=base - timedelta(days=4, hours=3),
        has_list_unsubscribe=True,
    ))

    # Franprix newsletter
    emails.append(_make_email(
        user_id, from_address="newsletter@franprix.fr", from_name="Franprix",
        subject="Les bons plans de la semaine!",
        snippet=(
            "Decouvrez les promotions de la semaine dans votre Franprix: "
            "Coca-Cola 1.5L: 1.29 EUR, Beurre President: 2.49 EUR. "
            "Offres valables du 24 au 30 mars."
        ),
        date=base - timedelta(days=3, hours=5),
        has_list_unsubscribe=True,
    ))

    # GitHub notification
    emails.append(_make_email(
        user_id, from_address="notifications@github.com", from_name="GitHub",
        subject="[nova-ledger] New issue: Fix SNCF email parsing",
        snippet=(
            "ghostdog opened a new issue #42 in nova-ledger/nova-ledger. "
            "Title: Fix SNCF email parsing for multi-leg journeys. "
            "Labels: bug, extraction."
        ),
        date=base - timedelta(days=2, hours=1),
        has_list_unsubscribe=True,
    ))

    # Slack notification
    emails.append(_make_email(
        user_id, from_address="notification@slack.com", from_name="Slack",
        subject="Nouveau message de Marie dans #general",
        snippet=(
            "Marie: Hey l'equipe, on fait un point demain a 10h? "
            "J'ai des updates sur le projet banking. "
            "Cliquez pour repondre dans Slack."
        ),
        date=base - timedelta(days=1, hours=2),
        has_list_unsubscribe=True,
    ))

    # BNP Paribas account notification (not transactional per se)
    emails.append(_make_email(
        user_id, from_address="information@bnpparibas.com",
        from_name="BNP Paribas",
        subject="Votre releve de compte est disponible",
        snippet=(
            "Votre releve de compte courant du mois de mars 2026 est disponible "
            "dans votre espace client. Connectez-vous sur mabanque.bnpparibas "
            "pour le consulter."
        ),
        date=base - timedelta(days=1, hours=8),
    ))

    # La Poste tracking
    emails.append(_make_email(
        user_id, from_address="noreply@notification.laposte.fr",
        from_name="La Poste",
        subject="Votre colis est en cours de livraison",
        snippet=(
            "Colis 6A12345678901 - En cours de livraison. "
            "Livraison prevue aujourd'hui avant 18h. "
            "Expediteur: Amazon Logistics."
        ),
        date=base - timedelta(days=4, hours=7),
    ))

    # McDonald's app promo
    emails.append(_make_email(
        user_id, from_address="info@mcdonalds.fr",
        from_name="McDonald's France",
        subject="1 menu achete = 1 McFlurry offert!",
        snippet=(
            "Offre exclusive app McDonald's! Pour 1 menu Best Of achete, "
            "votre McFlurry est offert. Valable du 25 au 31 mars 2026. "
            "Commandez depuis l'app."
        ),
        date=base - timedelta(days=2, hours=6),
        has_list_unsubscribe=True,
    ))

    # Bienvenue newsletter from Hall's Beer
    emails.append(_make_email(
        user_id, from_address="events@hallsbeer.fr",
        from_name="Hall's Beer Paris",
        subject="Ce week-end: soiree quiz + happy hour!",
        snippet=(
            "Rejoignez-nous ce samedi pour notre soiree quiz! "
            "Happy hour de 18h a 20h: toutes les pintes a 5 EUR. "
            "Reservez votre table sur hallsbeer.fr."
        ),
        date=base - timedelta(days=3, hours=4),
        has_list_unsubscribe=True,
    ))

    # Booking.com "you looked at" reminder
    emails.append(_make_email(
        user_id, from_address="noreply@booking.com", from_name="Booking.com",
        subject="Hotel Ibis Lyon - les prix baissent!",
        snippet=(
            "Bonne nouvelle! L'Hotel Ibis Lyon Centre que vous avez consulte "
            "a baisse ses prix. A partir de 65 EUR/nuit. "
            "Reserve vite, il ne reste que 3 chambres!"
        ),
        date=base - timedelta(days=5, hours=6),
        has_list_unsubscribe=True,
    ))

    # EDF energy bill notification (no matching tx)
    emails.append(_make_email(
        user_id, from_address="ne-pas-repondre@edf.fr", from_name="EDF",
        subject="Votre facture EDF est disponible",
        snippet=(
            "Votre facture d'electricite de mars 2026 est disponible. "
            "Montant: 67.82 EUR. Prelevement le 05/04/2026. "
            "Consultez-la dans votre espace client."
        ),
        date=base - timedelta(days=3, hours=9),
    ))

    # Welcome email from Picard
    emails.append(_make_email(
        user_id, from_address="bienvenue@picard.fr", from_name="Picard",
        subject="Bienvenue dans le programme fidelite Picard!",
        snippet=(
            "Felicitations Jean! Votre carte de fidelite Picard est activee. "
            "Beneficiez de -10% sur votre prochain achat avec le code BIENVENUE10. "
            "Valable 30 jours."
        ),
        date=base - timedelta(days=10, hours=4),
        has_list_unsubscribe=True,
    ))

    # Twitter/X notification
    emails.append(_make_email(
        user_id, from_address="notify@x.com", from_name="X",
        subject="@elikihe a aime votre post",
        snippet=(
            "@elikihe et 3 autres personnes ont aime votre post: "
            "'Building an AI-powered accounting backend...' "
            "Voir les interactions."
        ),
        date=base - timedelta(days=1, hours=5),
        has_list_unsubscribe=True,
    ))

    # SFR newsletter
    emails.append(_make_email(
        user_id, from_address="offres@sfr.fr", from_name="SFR",
        subject="Fibre SFR: 1 Gb/s a 22.99 EUR/mois!",
        snippet=(
            "Passez a la Fibre SFR! 1 Gb/s partage, TV incluse, "
            "appels illimites. 22.99 EUR/mois pendant 12 mois. "
            "Engagement 12 mois."
        ),
        date=base - timedelta(days=7, hours=3),
        has_list_unsubscribe=True,
    ))

    # Vinted notification
    emails.append(_make_email(
        user_id, from_address="noreply@vinted.fr", from_name="Vinted",
        subject="Quelqu'un a aime votre article!",
        snippet=(
            "Bonne nouvelle! 2 personnes ont ajoute votre 'Veste Zara taille M' "
            "a leurs favoris. Prix: 25.00 EUR. "
            "Pensez a baisser le prix pour vendre plus vite."
        ),
        date=base - timedelta(days=2, hours=8),
        has_list_unsubscribe=True,
    ))

    return emails


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Generate test emails matching bank transaction data for correlation testing"

    def handle(self, *args, **options):
        random.seed(42)  # Reproducible output
        user_id = 13

        # Delete existing emails for user 13
        deleted = Email.objects.filter(user_id=user_id).delete()
        self.stdout.write(f"Deleted {deleted} existing emails")

        # Read bank transactions grouped by vendor
        bank_txs = BankTransaction.objects.filter(user_id=user_id).order_by("date")
        vendors = {}
        for tx in bank_txs:
            key = tx.simplified_wording or tx.original_wording or "UNKNOWN"
            vendors.setdefault(key, []).append(tx)

        self.stdout.write(f"\nBank transactions: {bank_txs.count()} total")
        for k, v in sorted(vendors.items(), key=lambda x: -len(x[1])):
            self.stdout.write(f"  {len(v):>3}x {k}")

        emails = []

        # -------------------------------------------------------------------
        # 1. SNCF — email for most train tickets
        # -------------------------------------------------------------------
        for tx in vendors.get("SNCF", []):
            if random.random() < 0.80:  # 80% get emails
                emails.append(_sncf_email(user_id, tx))

        # -------------------------------------------------------------------
        # 2. UBER EATS — always sends receipts
        # -------------------------------------------------------------------
        for tx in vendors.get("UBER EATS", []):
            emails.append(_uber_eats_email(user_id, tx))

        # -------------------------------------------------------------------
        # 3. MONOPRIX — only ~30% get receipt emails
        # -------------------------------------------------------------------
        for tx in vendors.get("MONOPRIX", []):
            if random.random() < 0.30:
                emails.append(_monoprix_email(user_id, tx))

        # -------------------------------------------------------------------
        # 4. GOOGLE *BUDGEA — always sends invoices
        # -------------------------------------------------------------------
        for tx in vendors.get("GOOGLE *BUDGEA", []):
            emails.append(_google_budgea_email(user_id, tx))

        # -------------------------------------------------------------------
        # 5. ALLORESTO.FR PARIS — most orders get confirmations
        # -------------------------------------------------------------------
        for tx in vendors.get("ALLORESTO.FR PARIS", []):
            if random.random() < 0.75:
                emails.append(_alloresto_email(user_id, tx))

        # -------------------------------------------------------------------
        # 6. MCDO — only ~20% get emails (mostly card swipes)
        # -------------------------------------------------------------------
        for tx in vendors.get("MCDO", []):
            if random.random() < 0.20:
                emails.append(_mcdo_email(user_id, tx))

        # -------------------------------------------------------------------
        # 7. SALAIRE — NO emails (bank-only scenario)
        # -------------------------------------------------------------------
        # Intentionally skipped

        # -------------------------------------------------------------------
        # 8. HALL'S BEER — occasional receipt ~25%
        # -------------------------------------------------------------------
        for tx in vendors.get("HALL'S BEER", []):
            if random.random() < 0.25:
                emails.append(_halls_beer_email(user_id, tx))

        # -------------------------------------------------------------------
        # 9. FRANPRIX — ~20% receipt emails
        # -------------------------------------------------------------------
        for tx in vendors.get("FRANPRIX PARIS 10", []):
            if random.random() < 0.20:
                emails.append(_franprix_email(user_id, tx))

        # -------------------------------------------------------------------
        # 10. DOCTEUR — ~40% get Doctolib recap
        # -------------------------------------------------------------------
        for tx in vendors.get("DOCTEUR", []):
            if random.random() < 0.40:
                emails.append(_docteur_email(user_id, tx))

        # -------------------------------------------------------------------
        # 11. THE BOOTLAGERS — ~30% receipt
        # -------------------------------------------------------------------
        for tx in vendors.get("THE BOOTLAGERS PARIS", []):
            if random.random() < 0.30:
                emails.append(_bootlagers_email(user_id, tx))

        # -------------------------------------------------------------------
        # Bank-only vendors (no emails): BNP PARIBAS (ATM),
        # SOCIETE GENERALE (ATM), LA BANQUE POSTALE (ATM),
        # DEBIT MENSUEL CARTE, CHEQUE, TABAC, empty wording
        # -------------------------------------------------------------------

        matching_count = len(emails)
        self.stdout.write(f"\nMatching emails created: {matching_count}")

        # -------------------------------------------------------------------
        # Non-matching transactional emails
        # -------------------------------------------------------------------
        nonmatching = _nonmatching_transactional(user_id)
        emails.extend(nonmatching)
        self.stdout.write(f"Non-matching transactional emails: {len(nonmatching)}")

        # -------------------------------------------------------------------
        # Non-transactional emails (newsletters, marketing, notifications)
        # -------------------------------------------------------------------
        nontransactional = _nontransactional_emails(user_id)
        emails.extend(nontransactional)
        self.stdout.write(f"Non-transactional emails: {len(nontransactional)}")

        # -------------------------------------------------------------------
        # Bulk create
        # -------------------------------------------------------------------
        Email.objects.bulk_create(emails)

        self.stdout.write(self.style.SUCCESS(
            f"\nTotal: {len(emails)} test emails created "
            f"({matching_count} matching, {len(nonmatching)} non-matching tx, "
            f"{len(nontransactional)} non-transactional)"
        ))
