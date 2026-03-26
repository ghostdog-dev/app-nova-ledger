"""
Generate fake emails matching real bank transaction data for correlation testing.

Creates ~80 emails with FULL BODY TEXT:
- ~40 matching bank transactions (receipts, confirmations)
- ~15 non-matching transactional emails (different payment method, gift cards)
- ~25 non-transactional (newsletters, marketing, notifications)
"""

import random
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.utils import timezone

from banking.models import BankTransaction
from emails.models import Email


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid():
    return f"fake_{uuid.uuid4().hex[:16]}"


def _make_email(user_id, *, from_address, from_name, subject, body,
                date, has_attachments=False, has_list_unsubscribe=False,
                status="new", labels=None):
    """Build an Email instance (not saved). Snippet auto-derived from body."""
    snippet = body[:200].replace("\n", " ").strip()
    return Email(
        user_id=user_id,
        provider="google",
        message_id=_uid(),
        from_address=from_address,
        from_name=from_name,
        subject=subject,
        snippet=snippet,
        body=body,
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


def _d(amount):
    """Format a Decimal as string with 2 decimal places and comma separator (French)."""
    return f"{abs(amount):.2f}".replace(".", ",")


def _compute_tax(ttc, rate):
    """Compute HT and TVA from TTC and rate. Returns (ht, tva) as Decimal."""
    ttc = Decimal(str(ttc))
    rate = Decimal(str(rate))
    ht = (ttc / (1 + rate / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tva = ttc - ht
    return ht, tva


def _generate_items(total, items_pool, min_items=3, max_items=7):
    """Generate random items that add up to total. Returns list of (name, price_str)."""
    n = random.randint(min_items, max_items)
    total = abs(float(total))
    # Generate n-1 random proportions, last item gets the remainder
    if n == 1:
        item = random.choice(items_pool)
        return [(item, f"{total:.2f}")]

    weights = [random.random() for _ in range(n - 1)]
    weight_sum = sum(weights)
    items = []
    running = 0.0
    chosen = random.sample(items_pool, min(n, len(items_pool)))
    if len(chosen) < n:
        chosen += random.choices(items_pool, k=n - len(chosen))

    for i in range(n - 1):
        price = round(total * weights[i] / weight_sum * 0.95, 2)  # leave room for last
        price = max(0.50, price)
        running += price
        items.append((chosen[i], f"{price:.2f}"))

    last_price = round(total - running, 2)
    if last_price < 0.01:
        last_price = 0.50
    items.append((chosen[-1], f"{last_price:.2f}"))
    return items


# ---------------------------------------------------------------------------
# Vendor email generators — each returns an Email with full body
# ---------------------------------------------------------------------------

def _sncf_email(user_id, tx):
    """SNCF train ticket confirmation."""
    amt = abs(tx.value)
    ref = f"QJ{_ref()}"
    destinations = ["Lyon Part-Dieu", "Marseille Saint-Charles", "Bordeaux Saint-Jean",
                    "Lille Flandres", "Strasbourg", "Nantes", "Toulouse Matabiau",
                    "Rennes", "Nice Ville", "Montpellier Saint-Roch"]
    dest = random.choice(destinations)
    dep_h = random.randint(6, 20)
    dep_m = random.randint(0, 59)
    arr_h = dep_h + random.randint(1, 3)
    arr_m = random.randint(0, 59)
    classe = random.choice(["1ere classe", "2nde classe"])
    ht, tva = _compute_tax(amt, 10)
    txn_ref = f"TXN-SNCF-{tx.date.strftime('%Y%m%d')}{random.randint(10, 99)}"

    date = _dt(tx.date, hour=random.randint(6, 9), minute=random.randint(0, 59))
    if random.random() < 0.3:
        date -= timedelta(days=1)

    subjects = [
        f"Confirmation de votre reservation - Trajet Paris > {dest.split()[0]}",
        f"e-billet - Votre voyage du {tx.date.strftime('%d/%m/%Y')}",
        f"Votre reservation SNCF - Ref {ref}",
    ]
    subject = random.choice(subjects)

    body = f"""Bonjour,

Votre reservation a ete confirmee.

Reference de reservation : {ref}
Trajet : Paris Gare de Lyon \u2192 {dest}
Date : {tx.date.strftime('%d/%m/%Y')}
Depart : {dep_h:02d}h{dep_m:02d} - Arrivee : {arr_h:02d}h{arr_m:02d}
Classe : {classe}

Detail du paiement :
  1 billet adulte : {_d(amt)} \u20ac
  Total TTC : {_d(amt)} \u20ac
  TVA (10%) : {_d(tva)} \u20ac
  Total HT : {_d(ht)} \u20ac

Moyen de paiement : Carte bancaire ****1234
Reference de transaction : {txn_ref}

Telechargez votre e-billet sur l'application SNCF Connect.

Merci de voyager avec nous.
L'equipe SNCF"""

    return _make_email(
        user_id, from_address="confirmation@oui.sncf", from_name="SNCF Connect",
        subject=subject, body=body, date=date, has_attachments=True,
    )


def _uber_eats_email(user_id, tx):
    """Uber Eats receipt."""
    amt = abs(tx.value)
    order_id = f"UE-{random.randint(1000, 9999)}-{tx.date.strftime('%Y')}"
    restaurants = ["Sushi Palace", "Big Fernand", "PNY Burger", "Bagelstein",
                   "Five Guys", "Pokawa", "Cojean", "Pitaya", "Clasico Argentino"]
    restaurant = random.choice(restaurants)
    date = _dt(tx.date, hour=random.randint(12, 21), minute=random.randint(0, 59))

    food_items = [
        "Plateau Sushi Deluxe", "Burger Classic", "Poke Bowl Saumon",
        "Pad Thai Poulet", "Burrito Chicken", "Salade Caesar",
        "Tacos XL", "Pizza Margherita", "Nems Porc x4",
        "Gyoza x6", "Edamame", "Mochi Matcha x3",
    ]
    drinks = ["Coca-Cola", "Sprite", "Eau minerale", "Jus de pomme", "Ice Tea"]

    # Build items
    delivery_fee = Decimal("3.99")
    service_pct = Decimal("0.07")
    subtotal_target = amt - delivery_fee
    service_fee = (subtotal_target * service_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    food_total = subtotal_target - service_fee
    if food_total < 5:
        food_total = amt * Decimal("0.85")
        delivery_fee = amt * Decimal("0.05")
        service_fee = amt - food_total - delivery_fee

    items = _generate_items(food_total, food_items + drinks, min_items=2, max_items=5)
    ht, tva = _compute_tax(amt, 10)

    items_text = ""
    for name, price in items:
        items_text += f"  - {name} : {price.replace('.', ',')} \u20ac\n"

    address = random.choice([
        "15 rue de la Paix, 75002 Paris",
        "42 rue du Faubourg Saint-Denis, 75010 Paris",
        "8 boulevard de Magenta, 75010 Paris",
        "23 rue des Martyrs, 75009 Paris",
    ])

    body = f"""Merci pour votre commande !

Commande #{order_id}
Restaurant : {restaurant}
Date : {tx.date.strftime('%d/%m/%Y')}

Articles :
{items_text.rstrip()}
  Sous-total : {_d(food_total)} \u20ac
  Frais de livraison : {_d(delivery_fee)} \u20ac
  Frais de service : {_d(service_fee)} \u20ac
  Total : {_d(amt)} \u20ac
  TVA (10%) : {_d(tva)} \u20ac

Paye par : Carte Mastercard ****1234
Adresse : {address}

Bon appetit !"""

    return _make_email(
        user_id, from_address="uber.eats@uber.com", from_name="Uber Eats",
        subject="Votre recu Uber Eats", body=body, date=date,
    )


def _monoprix_email(user_id, tx):
    """Monoprix receipt email (loyalty card)."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(10, 20), minute=random.randint(0, 59))
    ticket_no = f"{tx.date.strftime('%Y%m%d')}{random.randint(10000000, 99999999)}"

    grocery_items = [
        "Lait demi-ecreme 1L", "Pain de mie complet", "Bananes bio 1kg",
        "Jambon blanc x4", "Eau minerale 6x1.5L", "Fromage comte",
        "Salade verte", "Yaourts nature x12", "Gel douche",
        "Papier toilette x9", "Beurre doux 250g", "Oeufs x6 bio",
        "Pates penne 500g", "Sauce tomate basilic", "Cafe moulu 250g",
        "Jus d'orange 1L", "Poulet roti", "Camembert",
        "Tomates grappe 1kg", "Courgettes 1kg", "Creme fraiche 20cl",
        "Riz basmati 1kg", "Chocolat noir 70%", "Biscuits petit-beurre",
        "Sac congelation x50", "Lessive liquide 2L", "Mouchoirs x10",
    ]

    items = _generate_items(amt, grocery_items, min_items=5, max_items=12)
    store = random.choice([
        "MONOPRIX PARIS NATION\n42 cours de Vincennes, 75012 Paris",
        "MONOPRIX GARE DE L'EST\n1 place du 11 Novembre 1918, 75010 Paris",
        "MONOPRIX REPUBLIQUE\n31 boulevard du Temple, 75003 Paris",
    ])

    items_text = ""
    for name, price in items:
        items_text += f"  {name:<30s} {price.replace('.', ',')} \u20ac\n"

    body = f"""{store}
Tel : 01 {random.randint(40,49)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}

Date : {tx.date.strftime('%d/%m/%Y')} a {random.randint(9,20):02d}:{random.randint(0,59):02d}
Ticket n\u00b0 : {ticket_no}

Articles :
{items_text.rstrip()}
  ----------------------------------
  TOTAL                        {_d(amt)} \u20ac

Carte bancaire : ****1234
Transaction : CB-{ticket_no}

Merci de votre visite !"""

    return _make_email(
        user_id, from_address="fidelite@monoprix.fr", from_name="Monoprix",
        subject="Votre ticket de caisse Monoprix", body=body, date=date,
        has_attachments=True,
    )


def _google_budgea_email(user_id, tx):
    """Google Cloud / Budgea invoice."""
    amt = abs(tx.value)
    inv = f"GCP-{tx.date.strftime('%Y')}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
    date = _dt(tx.date, hour=3, minute=random.randint(0, 59))
    ht, tva = _compute_tax(amt, 20)

    # Compute period
    period_end = tx.date
    period_start = period_end - timedelta(days=28)

    services = [
        ("Google Cloud Platform services", None),
        ("Cloud Storage", None),
        ("Cloud Functions", None),
        ("Compute Engine", None),
        ("Cloud SQL", None),
        ("BigQuery", None),
    ]
    chosen_services = random.sample(services, k=random.randint(2, 4))
    # Main service gets most of the amount
    main_amt = (ht * Decimal("0.7")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    remaining = ht - main_amt
    service_lines = []
    service_lines.append(f"  {chosen_services[0][0]} ({period_start.strftime('%b %d')} - {period_end.strftime('%b %d')}): {_d(main_amt)} \u20ac")
    if len(chosen_services) > 1:
        for i, (svc, _) in enumerate(chosen_services[1:]):
            if i < len(chosen_services) - 2:
                svc_amt = (remaining / (len(chosen_services) - 1)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                svc_amt = remaining - sum(
                    Decimal(line.split(": ")[1].replace(",", ".").replace(" \u20ac", ""))
                    for line in service_lines[1:]
                ) if service_lines[1:] else remaining
            service_lines.append(f"  {svc}: {_d(svc_amt)} \u20ac")

    services_text = "\n".join(service_lines)

    body = f"""Google Cloud Platform
Invoice #{inv}

Bill to: Arthur Lassegue
Date: {tx.date.strftime('%B %d, %Y')}
Due: {tx.date.strftime('%B %d, %Y')}

Services:
{services_text}
  Subtotal: {_d(ht)} \u20ac

Tax (20% VAT): {_d(tva)} \u20ac
Total HT: {_d(ht)} \u20ac
Total TTC: {_d(amt)} \u20ac

Payment method: Mastercard ****1234
Transaction ID: GCP-TXN-{tx.date.strftime('%Y%m%d')}-{random.randint(100, 999)}

This invoice was paid automatically."""

    subjects = [
        f"Your Google Cloud invoice #{inv}",
        f"Votre facture Google - {inv}",
    ]
    return _make_email(
        user_id, from_address="payments-noreply@google.com",
        from_name="Google Payments", subject=random.choice(subjects), body=body,
        date=date, has_attachments=True,
    )


def _alloresto_email(user_id, tx):
    """Alloresto.fr (Just Eat) order confirmation."""
    amt = abs(tx.value)
    order = _ref()
    date = _dt(tx.date, hour=random.randint(11, 21), minute=random.randint(0, 59))
    if random.random() < 0.3:
        date -= timedelta(days=1)

    restaurants = ["Pizza Hut", "KFC", "Domino's Pizza", "Wok Street",
                   "Taco Bell", "Mezzo di Pasta", "Eat Sushi"]
    restaurant = random.choice(restaurants)

    food_items = [
        "Pizza Margherita", "Poulet frit x6", "Menu Bucket",
        "Wok nouilles poulet", "Salade Thai", "Nems x4",
        "Frites classiques", "Coca-Cola 33cl", "Tiramisu",
        "Burger double cheese", "Wings BBQ x8", "Riz cantonnais",
    ]

    delivery_fee = Decimal("2.99")
    food_total = amt - delivery_fee
    if food_total < 3:
        food_total = amt * Decimal("0.90")
        delivery_fee = amt - food_total
    items = _generate_items(food_total, food_items, min_items=2, max_items=5)
    ht, tva = _compute_tax(amt, 10)

    items_text = ""
    for name, price in items:
        items_text += f"  - {name} : {price.replace('.', ',')} \u20ac\n"

    address = random.choice([
        "42 rue du Faubourg Saint-Denis, 75010 Paris",
        "18 rue de Dunkerque, 75010 Paris",
        "7 avenue Parmentier, 75011 Paris",
    ])

    body = f"""Votre commande a ete confirmee !

Commande #{order}
Restaurant : {restaurant}
Date : {tx.date.strftime('%d/%m/%Y')}
Livraison estimee : 30-45 min

Articles :
{items_text.rstrip()}
  Sous-total : {_d(food_total)} \u20ac
  Frais de livraison : {_d(delivery_fee)} \u20ac
  ----------------------------------
  Total TTC : {_d(amt)} \u20ac
  TVA (10%) : {_d(tva)} \u20ac
  Total HT : {_d(ht)} \u20ac

Paye par : Carte bancaire ****1234
Reference : ALR-{order}

Adresse de livraison : {address}

Merci d'avoir commande sur Alloresto.fr !
Suivez votre livraison dans l'application."""

    return _make_email(
        user_id, from_address="confirmation@alloresto.fr",
        from_name="Alloresto.fr", subject=f"Commande confirmee - #{order}",
        body=body, date=date,
    )


def _mcdo_email(user_id, tx):
    """McDonald's order confirmation."""
    amt = abs(tx.value)
    ref = _ref()
    date = _dt(tx.date, hour=random.randint(11, 22), minute=random.randint(0, 59))

    menu_items = [
        "Big Mac", "McChicken", "Royal Deluxe", "Filet-O-Fish",
        "McNuggets x6", "McNuggets x9", "McFlurry Oreo",
        "Frites moyennes", "Frites grandes", "Coca-Cola moyen",
        "Sundae caramel", "Salade Caesar", "CBO",
        "Cheeseburger", "Double Cheeseburger", "Wrap poulet",
    ]
    items = _generate_items(amt, menu_items, min_items=2, max_items=5)
    ht, tva = _compute_tax(amt, 10)

    items_text = ""
    for name, price in items:
        items_text += f"  {name:<28s} {price.replace('.', ',')} \u20ac\n"

    store = random.choice([
        "McDonald's Paris Gare de l'Est",
        "McDonald's Paris Republique",
        "McDonald's Paris Nation",
        "McDonald's Paris Magenta",
    ])

    body = f"""{store}

Commande n\u00b0 {ref}
Date : {tx.date.strftime('%d/%m/%Y')} a {random.randint(11,22):02d}:{random.randint(0,59):02d}
Type : {random.choice(["A emporter", "Sur place"])}

Articles :
{items_text.rstrip()}
  ----------------------------------
  Total TTC : {_d(amt)} \u20ac
  TVA (10%) : {_d(tva)} \u20ac
  Total HT : {_d(ht)} \u20ac

Paiement : Carte bancaire ****1234
Reference : MCDO-{ref}

Merci de votre visite !
Telechargez l'app McDonald's pour des offres exclusives."""

    return _make_email(
        user_id, from_address="commande@mcdonalds.fr",
        from_name="McDonald's France", subject=f"Votre commande McDonald's #{ref}",
        body=body, date=date,
    )


def _halls_beer_email(user_id, tx):
    """Hall's Beer bar receipt."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(18, 23), minute=random.randint(0, 59))
    ticket = f"HB-{tx.date.strftime('%Y%m%d')}-{random.randint(100, 999)}"

    drink_items = [
        "Pinte IPA", "Pinte Lager", "Pinte Stout", "Pinte Pale Ale",
        "Demi Blonde", "Demi Ambree", "Cocktail Moscow Mule",
        "Cocktail Gin Tonic", "Planche charcuterie", "Planche fromages",
        "Nachos", "Fish & Chips", "Burger Hall's",
        "Frites truffe", "Wings BBQ x8",
    ]
    items = _generate_items(amt, drink_items, min_items=2, max_items=6)
    ht, tva = _compute_tax(amt, 20)

    items_text = ""
    for name, price in items:
        items_text += f"  {name:<28s} {price.replace('.', ',')} \u20ac\n"

    body = f"""Hall's Beer Paris
12 rue du Faubourg Saint-Martin, 75010 Paris

Date : {tx.date.strftime('%d/%m/%Y')} a {random.randint(18,23):02d}:{random.randint(0,59):02d}
Ticket n\u00b0 : {ticket}

Consommations :
{items_text.rstrip()}
  ----------------------------------
  Total TTC : {_d(amt)} \u20ac
  TVA (20%) : {_d(tva)} \u20ac
  Total HT : {_d(ht)} \u20ac

Carte bancaire : ****1234
Transaction : {ticket}

Merci pour votre visite chez Hall's Beer !
A bientot !"""

    return _make_email(
        user_id, from_address="contact@hallsbeer.fr",
        from_name="Hall's Beer Paris", subject="Votre addition - Hall's Beer",
        body=body, date=date,
    )


def _franprix_email(user_id, tx):
    """Franprix receipt email."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(8, 21), minute=random.randint(0, 59))
    ticket_no = f"{tx.date.strftime('%Y%m%d')}{random.randint(1000000, 9999999)}"

    grocery_items = [
        "Lait 1L", "Pain tradition", "Pommes 1kg", "Yaourts x4",
        "Jambon x4", "Eau 1.5L", "Fromage rape", "Tomates 500g",
        "Bananes 1kg", "Beurre 250g", "Oeufs x6", "Pates 500g",
        "Riz 1kg", "Huile olive 50cl", "Cafe capsules x10",
        "Biscuits", "Sopalin x2", "Mouchoirs x6",
        "Gel douche", "Dentifrice", "Shampooing",
    ]
    items = _generate_items(amt, grocery_items, min_items=3, max_items=8)

    items_text = ""
    for name, price in items:
        items_text += f"  {name:<28s} {price.replace('.', ',')} \u20ac\n"

    body = f"""FRANPRIX PARIS 10
85 rue du Faubourg Saint-Denis, 75010 Paris
Tel : 01 42 46 12 34

Date : {tx.date.strftime('%d/%m/%Y')} a {random.randint(8,21):02d}:{random.randint(0,59):02d}
Ticket n\u00b0 : {ticket_no}

Articles :
{items_text.rstrip()}
  ----------------------------------
  TOTAL                        {_d(amt)} \u20ac

Carte bancaire : ****1234
Transaction : CB-{ticket_no}

Points fidelite cumules : +{random.randint(5, 25)} points

Merci de votre visite !"""

    return _make_email(
        user_id, from_address="ticket@franprix.fr",
        from_name="Franprix", subject="Votre ticket Franprix",
        body=body, date=date, has_attachments=True,
    )


def _docteur_email(user_id, tx):
    """Doctor visit / Doctolib confirmation."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(8, 17), minute=random.randint(0, 59))
    if random.random() < 0.3:
        date -= timedelta(days=1)

    doctors = [
        ("Dr. Martin", "Medecine generale", "15 rue de Paradis, 75010 Paris"),
        ("Dr. Dubois", "Dermatologie", "8 boulevard Magenta, 75010 Paris"),
        ("Dr. Bernard", "ORL", "42 rue Lafayette, 75009 Paris"),
        ("Dr. Petit", "Ophtalmologie", "3 place de la Republique, 75003 Paris"),
    ]
    doctor, specialty, address = random.choice(doctors)
    consultation_ref = f"DOC-{tx.date.strftime('%Y%m%d')}-{random.randint(100, 999)}"
    ht, tva = _compute_tax(amt, 0)  # Medical is VAT exempt

    body = f"""Recapitulatif de votre consultation

{doctor} - {specialty}
{address}

Date de consultation : {tx.date.strftime('%d/%m/%Y')}
Heure : {random.randint(8,18):02d}h{random.choice(['00','15','30','45'])}

Detail des honoraires :
  Consultation : {_d(amt)} \u20ac
  Tiers payant : Non applicable
  Reste a charge : {_d(amt)} \u20ac

Moyen de paiement : Carte bancaire ****1234
Reference : {consultation_ref}

N'oubliez pas d'envoyer votre feuille de soins a votre mutuelle
pour obtenir un remboursement.

Cordialement,
{doctor}
Rendez-vous pris via Doctolib"""

    return _make_email(
        user_id, from_address="noreply@doctolib.fr",
        from_name="Doctolib", subject="Recapitulatif de votre consultation",
        body=body, date=date,
    )


def _bootlagers_email(user_id, tx):
    """The Bootlagers bar receipt."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(19, 23), minute=random.randint(0, 59))
    ticket = f"BLG-{tx.date.strftime('%Y%m%d')}-{random.randint(100, 999)}"

    drink_items = [
        "Pinte Chouffe", "Pinte Delirium", "Pinte Chimay Bleue",
        "Demi Leffe Blonde", "Demi Duvel", "Cocktail Old Fashioned",
        "Cocktail Mojito", "Planche mixte", "Burger Bootlagers",
        "Frites maison", "Onion rings", "Hot dog",
    ]
    items = _generate_items(amt, drink_items, min_items=2, max_items=5)
    ht, tva = _compute_tax(amt, 20)

    items_text = ""
    for name, price in items:
        items_text += f"  {name:<28s} {price.replace('.', ',')} \u20ac\n"

    body = f"""The Bootlagers Paris
25 rue de Dunkerque, 75010 Paris

Date : {tx.date.strftime('%d/%m/%Y')} a {random.randint(19,23):02d}:{random.randint(0,59):02d}
Note n\u00b0 : {ticket}

Consommations :
{items_text.rstrip()}
  ----------------------------------
  Total TTC : {_d(amt)} \u20ac
  TVA (20%) : {_d(tva)} \u20ac
  Total HT : {_d(ht)} \u20ac

Carte bancaire : ****1234
Ref. paiement : {ticket}

Merci pour votre visite !
The Bootlagers Paris - Craft Beer Bar"""

    return _make_email(
        user_id, from_address="hello@thebootlagers.com",
        from_name="The Bootlagers Paris",
        subject="Merci pour votre visite - The Bootlagers",
        body=body, date=date,
    )


def _tabac_email(user_id, tx):
    """Tabac de la Rey receipt email (PMU / lottery / tobacco shop)."""
    amt = abs(tx.value)
    date = _dt(tx.date, hour=random.randint(8, 20), minute=random.randint(0, 59))
    ticket_no = f"TAB-{tx.date.strftime('%Y%m%d')}-{random.randint(100, 999)}"

    tabac_items = [
        "Paquet Marlboro Gold", "Paquet Camel Blue", "Briquet BIC x2",
        "Grattage Astro", "Grattage Millionnaire", "Loto (grille simple)",
        "Euro Millions (grille)", "PMU Quinte", "Timbre fiscal",
        "Recharge telephone 20\u20ac", "Carte SIM prepayee",
        "Chewing-gum", "Bonbons", "Journal Le Monde",
    ]
    items = _generate_items(amt, tabac_items, min_items=1, max_items=4)

    items_text = ""
    for name, price in items:
        items_text += f"  {name:<28s} {price.replace('.', ',')} \u20ac\n"

    body = f"""TABAC DE LA REY
15 rue du Faubourg Saint-Denis, 75010 Paris

Date : {tx.date.strftime('%d/%m/%Y')} a {random.randint(8,20):02d}:{random.randint(0,59):02d}
Ticket n\u00b0 : {ticket_no}

Articles :
{items_text.rstrip()}
  ----------------------------------
  TOTAL                        {_d(amt)} \u20ac

Carte bancaire : ****1234
Transaction : {ticket_no}

Merci et a bientot !"""

    return _make_email(
        user_id, from_address="ticket@tabacdelarey.fr",
        from_name="Tabac de la Rey",
        subject="Votre ticket - Tabac de la Rey",
        body=body, date=date,
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
        body="""Bonjour,

Nous vous confirmons la reception de votre commande.

Commande #402-7291845-3928164
Date : 23/03/2026

Articles commandes :
  Clavier sans fil Logitech K380     39,99 \u20ac
  Tapis de souris XXL                10,00 \u20ac
  ----------------------------------
  Sous-total :                       49,99 \u20ac
  Livraison Prime :                   0,00 \u20ac
  Total :                            49,99 \u20ac

Paye par : Cheque-cadeau Amazon (solde restant : 12,45 \u20ac)

Livraison estimee : 28 mars 2026
Adresse : 42 rue du Faubourg Saint-Denis, 75010 Paris

Suivez votre colis sur amazon.fr/vos-commandes

Merci d'avoir commande sur Amazon.fr !""",
        date=base - timedelta(days=3, hours=2), has_attachments=False,
    ))

    # Netflix subscription on different card
    emails.append(_make_email(
        user_id, from_address="info@account.netflix.com", from_name="Netflix",
        subject="Votre facture Netflix - Mars 2026",
        body="""Netflix

Facture mensuelle

Compte : arthur.lassegue@gmail.com
Date de facturation : 20/03/2026
Periode : 20/03/2026 - 19/04/2026

Detail :
  Abonnement Netflix Standard     13,49 \u20ac
  TVA incluse (20%)                2,25 \u20ac

Total : 13,49 \u20ac

Moyen de paiement : Visa ****5678
Reference : NF-2026032001

Prochaine facturation : 20/04/2026

Gerez votre abonnement sur netflix.com/account""",
        date=base - timedelta(days=7, hours=5),
    ))

    # Spotify receipt not in bank data
    emails.append(_make_email(
        user_id, from_address="no-reply@spotify.com", from_name="Spotify",
        subject="Votre recu Spotify Premium",
        body="""Spotify

Recu de paiement

Compte : arthur.lassegue@gmail.com
Date : 15/03/2026

Detail :
  Spotify Premium (individuel)      9,99 \u20ac
  TVA incluse (20%)                 1,67 \u20ac

Total : 9,99 \u20ac

Moyen de paiement : PayPal (arthur@email.com)
Reference : SP-PMT-20260315-8742

Prochaine facturation : 15/04/2026

Merci d'utiliser Spotify !""",
        date=base - timedelta(days=12, hours=8),
    ))

    # Apple App Store purchase
    emails.append(_make_email(
        user_id, from_address="no_reply@email.apple.com", from_name="Apple",
        subject="Votre recu d'achat Apple",
        body="""Apple

Recu d'achat
Identifiant Apple : arthur@icloud.com
Date : 15/03/2026

Achats :
  iCloud+ 50 Go (abonnement mensuel)     0,99 \u20ac
  TVA (20%) incluse                       0,17 \u20ac

Total : 0,99 \u20ac

Moyen de paiement : Mastercard ****9012
Reference : APPLE-PMT-20260315

Gerez vos abonnements dans Reglages > Apple ID.

Apple Distribution International Ltd.""",
        date=base - timedelta(days=11, hours=3),
    ))

    # Fnac order (paid in store, email for order tracking)
    emails.append(_make_email(
        user_id, from_address="commande@fnac.com", from_name="Fnac",
        subject="Votre commande Fnac #CF2026031587",
        body="""Fnac

Confirmation de commande

Commande #CF2026031587
Date : 15/03/2026
Mode : Click & Collect - Fnac Forum des Halles

Articles :
  Ecouteurs Sony WH-1000XM5 Noir     279,99 \u20ac
  TVA (20%)                            46,67 \u20ac

Total TTC : 279,99 \u20ac

Paye en magasin : Carte bancaire ****3456

Statut : Pret a retirer
Presentez cet email en magasin avec une piece d'identite.

Magasin : Fnac Forum des Halles
1 rue Pierre Lescot, 75001 Paris
Horaires : Lun-Sam 10h-20h""",
        date=base - timedelta(days=5, hours=6), has_attachments=False,
    ))

    # Deliveroo receipt (not in bank - different card)
    emails.append(_make_email(
        user_id, from_address="no-reply@deliveroo.fr", from_name="Deliveroo",
        subject="Votre commande Deliveroo",
        body="""Merci pour votre commande !

Commande #DLV-892741
Restaurant : Pho Tai
Date : 18/03/2026

Articles :
  - Bo Bun Poulet x2 : 24,00 \u20ac
  - Nems Porc x4 : 8,50 \u20ac
  Sous-total : 32,50 \u20ac
  Frais de livraison : 1,99 \u20ac
  Frais de service : 2,51 \u20ac
  Reduction -10% : -3,50 \u20ac
  Total : 33,50 \u20ac
  TVA (10%) : 3,05 \u20ac

Paye par : Visa ****5678
Adresse : 42 rue du Faubourg Saint-Denis, 75010 Paris

Bon appetit !""",
        date=base - timedelta(days=8, hours=7),
    ))

    # IKEA online order (not in bank)
    emails.append(_make_email(
        user_id, from_address="noreply@ikea.com", from_name="IKEA",
        subject="Confirmation de commande IKEA #1089234567",
        body="""IKEA

Confirmation de commande

Commande n\u00b0 1089234567
Date : 24/03/2026

Articles commandes :
  KALLAX Etagere 4 cases, blanc       59,99 \u20ac
  MALM Commode 4 tiroirs              79,99 \u20ac
  SKADIS Panneau perfore              16,02 \u20ac
  ----------------------------------
  Sous-total :                        156,00 \u20ac
  Livraison :                          39,00 \u20ac
  Total TTC :                         195,00 \u20ac
  TVA (20%) :                          32,50 \u20ac

Paiement en 3x sans frais :
  1ere echeance (24/03) :             65,00 \u20ac
  2eme echeance (24/04) :             65,00 \u20ac
  3eme echeance (24/05) :             65,00 \u20ac

Carte : Visa ****5678
Livraison prevue : 01/04/2026

IKEA France SAS""",
        date=base - timedelta(days=2, hours=4),
    ))

    # Leroy Merlin receipt
    emails.append(_make_email(
        user_id, from_address="contact@leroymerlin.fr",
        from_name="Leroy Merlin",
        subject="Votre ticket de caisse Leroy Merlin",
        body="""Leroy Merlin Paris 19
42 avenue Jean Jaures, 75019 Paris

Date : 18/03/2026 a 11:42
Ticket : LM-20260318-4521

Articles :
  Peinture blanche satin 10L        45,90 \u20ac
  Rouleau peinture 180mm             8,50 \u20ac
  Bac a peinture                      4,90 \u20ac
  Scotch de masquage 50m x3          12,90 \u20ac
  Bache protection 4x5m              15,20 \u20ac
  ----------------------------------
  Total TTC :                        87,40 \u20ac
  TVA (20%) :                        14,57 \u20ac
  Total HT :                         72,83 \u20ac

Carte bancaire : ****3456
Reference : CB-LM-20260318

Merci pour votre achat !
Retour possible sous 90 jours avec ce ticket.""",
        date=base - timedelta(days=8, hours=2), has_attachments=True,
    ))

    # Darty (warranty email, no matching tx)
    emails.append(_make_email(
        user_id, from_address="service@darty.com", from_name="Darty",
        subject="Votre facture Darty - Lave-linge",
        body="""Darty

Facture #D20260315

Date : 15/03/2026
Magasin : Darty Republique, Paris

Articles :
  Samsung EcoBubble WW90T534DAW     499,00 \u20ac
  Livraison + installation           39,00 \u20ac
  Reprise ancien appareil             0,00 \u20ac
  ----------------------------------
  Total TTC :                       538,00 \u20ac
  TVA (20%) :                        89,67 \u20ac
  Total HT :                        448,33 \u20ac

Carte bancaire : ****3456
Reference : DARTY-PMT-20260315

Garantie constructeur : 2 ans (jusqu'au 15/03/2028)
Extension de garantie disponible : +3 ans pour 69,99 \u20ac

Livraison prevue : 22/03/2026 entre 8h et 13h""",
        date=base - timedelta(days=14, hours=5), has_attachments=True,
    ))

    # Booking.com hotel confirmation (no matching tx yet)
    emails.append(_make_email(
        user_id, from_address="noreply@booking.com", from_name="Booking.com",
        subject="Confirmation de reservation - Hotel Ibis Lyon Centre",
        body="""Booking.com

Confirmation de reservation

Reservation n\u00b0 : 4821093756
Hotel : Ibis Lyon Centre Part-Dieu
Adresse : 16 rue de Bonnel, 69003 Lyon

Check-in : 23/04/2026 a 14h00
Check-out : 24/04/2026 a 11h00
Duree : 1 nuit

Chambre :
  Chambre Standard Double            72,00 \u20ac
  Taxe de sejour                      2,48 \u20ac
  Total :                            74,48 \u20ac

Paye par : Mastercard ****1234
Reference : BKG-4821093756

Annulation gratuite jusqu'au 21/04/2026 a 18h00.
Passee cette date, 100% du montant sera facture.

Bon sejour !""",
        date=base - timedelta(days=1, hours=9),
    ))

    # Zalando order
    emails.append(_make_email(
        user_id, from_address="service@zalando.fr", from_name="Zalando",
        subject="Votre commande Zalando #ZL10029384",
        body="""Zalando

Confirmation de commande

Commande #ZL10029384
Date : 20/03/2026

Articles :
  Nike Air Max 90 - Blanc/Noir      139,95 \u20ac
  Taille : 43

  Sous-total :                       139,95 \u20ac
  Livraison :                          0,00 \u20ac
  Total TTC :                        139,95 \u20ac
  TVA (20%) :                         23,33 \u20ac

Paye par : Visa ****5678
Reference : ZAL-PMT-20260320

Livraison gratuite estimee : 25-28/03/2026
Retour gratuit sous 100 jours

Zalando SE""",
        date=base - timedelta(days=6, hours=3),
    ))

    # Pharmacie receipt
    emails.append(_make_email(
        user_id, from_address="ticket@pharmacie-lafayette.com",
        from_name="Pharmacie Lafayette",
        subject="Votre ticket - Pharmacie Lafayette",
        body="""Pharmacie Lafayette - Paris Gare du Nord
12 boulevard de Denain, 75010 Paris

Date : 22/03/2026 a 12:15
Ticket : PH-20260322-8841

Articles :
  Doliprane 1000mg x8               2,18 \u20ac
  Vitamine D3 1000UI                 8,90 \u20ac
  Spray nasal                        4,50 \u20ac
  Creme hydratante 50ml             12,92 \u20ac
  ----------------------------------
  Total :                           28,50 \u20ac
  Tiers payant Secu :              -12,30 \u20ac
  Reste a charge :                   16,20 \u20ac

Carte bancaire : ****1234
Reference : CB-PH-20260322

Pensez a envoyer votre feuille de soins a votre mutuelle.""",
        date=base - timedelta(days=4, hours=6),
    ))

    # Picard surgeles
    emails.append(_make_email(
        user_id, from_address="fidelite@picard.fr", from_name="Picard",
        subject="Votre ticket de caisse Picard",
        body="""PICARD SURGELES
Paris Gare de l'Est
18 rue du Faubourg Saint-Denis, 75010 Paris

Date : 17/03/2026 a 18:45
Ticket n\u00b0 : PIC-20260317-3291

Articles :
  Pizza 4 fromages                    4,50 \u20ac
  Croissants x6                       4,20 \u20ac
  Poelee de legumes Thai              4,95 \u20ac
  Glace vanille Madagascar 500ml      5,90 \u20ac
  Saumon fume x4                      8,95 \u20ac
  Soupes potiron x2                   4,30 \u20ac
  ----------------------------------
  Total :                            32,80 \u20ac

Carte bancaire : ****1234
Transaction : CB-PIC-20260317

Carte fidelite : 4 points ajoutes (total : 38 points)
Prochain bon de reduction a 50 points !""",
        date=base - timedelta(days=9, hours=1),
    ))

    # BlaBlaCar ride
    emails.append(_make_email(
        user_id, from_address="noreply@blablacar.fr", from_name="BlaBlaCar",
        subject="Confirmation de reservation BlaBlaCar",
        body="""BlaBlaCar

Reservation confirmee !

Trajet : Paris \u2192 Lyon
Date : 05/04/2026
Depart : 14h00 - Porte de Bercy
Arrivee estimee : 18h30 - Lyon Perrache

Conducteur : Marie L. (4.8/5 - 127 avis)
Vehicule : Renault Clio grise

Prix : 22,00 \u20ac
Frais de service : 3,30 \u20ac
Total : 25,30 \u20ac

Paye par : Carte Visa ****5678
Reference : BBC-2026040501

Retrouvez les details dans l'app BlaBlaCar.
En cas d'annulation, remboursement sous 48h.""",
        date=base - timedelta(days=1, hours=11),
    ))

    # Free Mobile facture
    emails.append(_make_email(
        user_id, from_address="facture@free-mobile.fr",
        from_name="Free Mobile",
        subject="Votre facture Free Mobile - Mars 2026",
        body="""Free Mobile

Facture n\u00b0 FM20260301
Ligne : 06 12 34 56 78
Periode : 01/03/2026 - 31/03/2026

Detail :
  Forfait Free 5G 150Go              19,99 \u20ac
  TVA (20%)                            3,33 \u20ac
  Total HT                           16,66 \u20ac
  Total TTC                          19,99 \u20ac

Mode de paiement : Prelevement bancaire
IBAN : FR76 **** **** **** **** ***2 34
Date de prelevement : 05/04/2026

Retrouvez le detail de votre consommation
sur votre Espace Abonne : mobile.free.fr

Free Mobile SAS""",
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
        body="""Offres de printemps SNCF !

Profitez de billets TGV des 29\u20ac pour voyager partout en France.

Destinations populaires :
  - Paris \u2192 Lyon : des 29\u20ac
  - Paris \u2192 Marseille : des 39\u20ac
  - Paris \u2192 Bordeaux : des 35\u20ac
  - Paris \u2192 Nice : des 45\u20ac
  - Paris \u2192 Strasbourg : des 25\u20ac

Offre valable du 01/04 au 30/04/2026.
Reservez maintenant sur sncf-connect.com

Conditions : prix TTC par personne, en 2nde classe.
Nombre de places limite.

Se desinscrire : https://newsletter.oui.sncf/unsubscribe""",
        date=base - timedelta(days=2, hours=8),
        has_list_unsubscribe=True,
    ))

    # Monoprix promo newsletter
    emails.append(_make_email(
        user_id, from_address="newsletter@monoprix.fr", from_name="Monoprix",
        subject="-30% sur tous les produits bio cette semaine!",
        body="""Monoprix

-30% sur toute la gamme Bio !

Cette semaine dans votre Monoprix :

Fruits et legumes bio :
  - Bananes bio : 1,99\u20ac/kg au lieu de 2,89\u20ac
  - Tomates bio : 2,49\u20ac/kg au lieu de 3,59\u20ac
  - Pommes Golden bio : 2,99\u20ac/kg au lieu de 4,29\u20ac

Epicerie bio :
  - Pates completes bio : 0,99\u20ac au lieu de 1,49\u20ac
  - Huile d'olive bio : 4,99\u20ac au lieu de 7,19\u20ac

Offre valable du 24 au 30 mars 2026 dans votre Monoprix.

Rendez-vous en magasin ou sur monoprix.fr

Se desinscrire : https://newsletter.monoprix.fr/unsubscribe""",
        date=base - timedelta(days=1, hours=6),
        has_list_unsubscribe=True,
    ))

    # Amazon deals newsletter
    emails.append(_make_email(
        user_id, from_address="vente-flash@amazon.fr", from_name="Amazon.fr",
        subject="Ventes Flash du jour - Jusqu'a -50%!",
        body="""Amazon.fr - Ventes Flash

Decouvrez les meilleures offres du jour !

  TV Samsung 55" OLED 4K     799\u20ac au lieu de 1 299\u20ac (-38%)
  AirPods Pro 2               229\u20ac au lieu de 279\u20ac (-18%)
  Robot Roomba i7+            399\u20ac au lieu de 599\u20ac (-33%)
  Kindle Paperwhite           109\u20ac au lieu de 149\u20ac (-27%)

Offres limitees, premiers arrives premiers servis !

Livraison gratuite pour les membres Prime.

Voir toutes les ventes flash : amazon.fr/ventes-flash

Se desinscrire : https://www.amazon.fr/unsubscribe""",
        date=base - timedelta(days=3, hours=7),
        has_list_unsubscribe=True,
    ))

    # LinkedIn notification
    emails.append(_make_email(
        user_id, from_address="notifications@linkedin.com", from_name="LinkedIn",
        subject="Arthur, vous avez 5 nouvelles notifications",
        body="""LinkedIn

Vos notifications de la semaine

- Marc D. a consulte votre profil
- Sophie L. et 2 autres ont aime votre publication
  "Retour d'experience sur la mise en place d'un pipeline AI..."
- Nouvelle offre d'emploi correspondant a votre profil :
  Developpeur Python Senior chez Doctolib - Paris
  Salaire : 55-70k\u20ac - CDI - Teletravail partiel

- Thomas R. vous a envoye un message
- 3 nouvelles connexions suggerees

Voir toutes vos notifications sur linkedin.com

Se desinscrire des emails LinkedIn : linkedin.com/settings""",
        date=base - timedelta(days=1, hours=4),
        has_list_unsubscribe=True,
    ))

    # Google account security
    emails.append(_make_email(
        user_id, from_address="no-reply@accounts.google.com",
        from_name="Google",
        subject="Alerte de securite - Nouvelle connexion detectee",
        body="""Google

Alerte de securite

Nouvelle connexion a votre compte Google

Appareil : MacBook Pro (macOS)
Lieu : Paris, France
Date : {date}
Navigateur : Chrome 123

Si c'etait bien vous, vous pouvez ignorer ce message.

Si vous ne reconnaissez pas cette activite, securisez
votre compte immediatement :
  https://myaccount.google.com/security

Cordialement,
L'equipe Google Accounts""".format(date=(base - timedelta(days=5)).strftime("%d/%m/%Y a %Hh%M")),
        date=base - timedelta(days=5, hours=2),
    ))

    # Doctolib appointment reminder
    emails.append(_make_email(
        user_id, from_address="rappel@doctolib.fr", from_name="Doctolib",
        subject="Rappel: RDV demain avec Dr. Martin",
        body="""Doctolib

Rappel de rendez-vous

Vous avez un rendez-vous demain :

Dr. Martin - Medecine generale
Date : {date} a 10h30
Adresse : 15 rue de Paradis, 75010 Paris
Duree estimee : 20 minutes

Documents a apporter :
  - Carte Vitale
  - Ordonnance en cours (si renouvellement)

Pour annuler ou reporter votre rendez-vous,
connectez-vous a Doctolib : doctolib.fr/mon-compte

En cas de retard de plus de 15 minutes,
votre rendez-vous pourra etre annule.

L'equipe Doctolib""".format(date=(base - timedelta(days=5)).strftime("%d/%m/%Y")),
        date=base - timedelta(days=6, hours=9),
    ))

    # Uber promo
    emails.append(_make_email(
        user_id, from_address="uber@uber.com", from_name="Uber",
        subject="5 EUR offerts sur votre prochaine course!",
        body="""Uber

Arthur, vous nous manquez !

Utilisez le code SPRING5 pour obtenir 5\u20ac de
reduction sur votre prochaine course Uber.

Comment ca marche :
  1. Ouvrez l'app Uber
  2. Allez dans Paiement > Ajouter un code promo
  3. Entrez SPRING5
  4. Commandez votre course !

Conditions :
  - Valable jusqu'au 31/03/2026
  - Course minimum : 10\u20ac
  - Non cumulable avec d'autres offres
  - 1 utilisation par compte

Bonne route !
L'equipe Uber

Se desinscrire : uber.com/unsubscribe""",
        date=base - timedelta(days=4, hours=3),
        has_list_unsubscribe=True,
    ))

    # Franprix newsletter
    emails.append(_make_email(
        user_id, from_address="newsletter@franprix.fr", from_name="Franprix",
        subject="Les bons plans de la semaine!",
        body="""Franprix

Les promotions de la semaine !

Du 24 au 30 mars dans votre Franprix :

  Coca-Cola 1.5L          1,29\u20ac au lieu de 1,79\u20ac
  Beurre President 250g   2,49\u20ac au lieu de 3,29\u20ac
  Jambon Herta x4         2,99\u20ac au lieu de 4,15\u20ac
  Lait UHT 1L             0,89\u20ac au lieu de 1,15\u20ac
  Nutella 750g             4,99\u20ac au lieu de 6,49\u20ac

Carte fidelite : doublez vos points cette semaine !

Franprix, le vrai bonheur est dans le frais.

Se desinscrire : franprix.fr/newsletter/unsubscribe""",
        date=base - timedelta(days=3, hours=5),
        has_list_unsubscribe=True,
    ))

    # GitHub notification
    emails.append(_make_email(
        user_id, from_address="notifications@github.com", from_name="GitHub",
        subject="[nova-ledger] New issue: Fix SNCF email parsing",
        body="""GitHub

ghostdog opened a new issue in nova-ledger/nova-ledger

Issue #42: Fix SNCF email parsing for multi-leg journeys

When an SNCF email contains multiple legs (e.g. Paris > Lyon > Marseille),
the extraction only captures the first leg and misses subsequent ones.

Steps to reproduce:
1. Sync emails with multi-leg SNCF bookings
2. Run classification pipeline
3. Check extracted transactions

Expected: One transaction per leg or one combined transaction
Actual: Only first leg extracted

Labels: bug, extraction
Assignees: none

Reply to this email or view on GitHub:
https://github.com/nova-ledger/nova-ledger/issues/42""",
        date=base - timedelta(days=2, hours=1),
        has_list_unsubscribe=True,
    ))

    # Slack notification
    emails.append(_make_email(
        user_id, from_address="notification@slack.com", from_name="Slack",
        subject="Nouveau message de Marie dans #general",
        body="""Slack - Nova Ledger Workspace

#general

Marie L. (10:42)
Hey l'equipe, on fait un point demain a 10h ?
J'ai des updates sur le projet banking.

Sophie D. (10:45)
Ca marche pour moi !

Thomas R. (10:47)
+1, j'ai aussi des questions sur l'API Powens

Cliquez pour repondre dans Slack :
https://nova-ledger.slack.com/archives/C01234567

Gerer vos notifications : slack.com/preferences""",
        date=base - timedelta(days=1, hours=2),
        has_list_unsubscribe=True,
    ))

    # BNP Paribas account notification (not transactional per se)
    emails.append(_make_email(
        user_id, from_address="information@bnpparibas.com",
        from_name="BNP Paribas",
        subject="Votre releve de compte est disponible",
        body="""BNP Paribas

Cher(e) Arthur Lassegue,

Votre releve de compte courant du mois de mars 2026
est desormais disponible dans votre Espace Client.

Compte : **** **** **** 1234
Periode : 01/03/2026 - 31/03/2026

Pour le consulter :
  1. Connectez-vous sur mabanque.bnpparibas
  2. Rubrique "Mes comptes" > "Releves"

Pensez a verifier vos operations regulierement.

Ce message est envoye automatiquement, merci de ne pas y repondre.

BNP Paribas SA""",
        date=base - timedelta(days=1, hours=8),
    ))

    # La Poste tracking
    emails.append(_make_email(
        user_id, from_address="noreply@notification.laposte.fr",
        from_name="La Poste",
        subject="Votre colis est en cours de livraison",
        body="""La Poste - Colissimo

Suivi de votre colis

Numero de suivi : 6A12345678901
Expediteur : Amazon Logistics

Historique :
  26/03/2026 06:12 - En cours de livraison
  25/03/2026 22:45 - Arrive au centre de tri Paris 10
  25/03/2026 14:30 - Pris en charge par La Poste
  24/03/2026 18:00 - Expedition par l'expediteur

Livraison prevue : Aujourd'hui avant 18h

Adresse de livraison : 42 rue du Faubourg Saint-Denis, 75010 Paris

Pas disponible ? Modifiez votre livraison sur laposte.fr/moncolis

La Poste - Colissimo""",
        date=base - timedelta(days=4, hours=7),
    ))

    # McDonald's app promo
    emails.append(_make_email(
        user_id, from_address="info@mcdonalds.fr",
        from_name="McDonald's France",
        subject="1 menu achete = 1 McFlurry offert!",
        body="""McDonald's

Offre exclusive application !

Pour 1 menu Best Of achete,
votre McFlurry est OFFERT !

Comment en profiter :
  1. Telechargez l'app McDonald's
  2. Activez l'offre dans "Mes offres"
  3. Presentez le QR code en caisse
  4. Savourez !

Offre valable du 25 au 31 mars 2026.
Dans tous les restaurants McDonald's participants.

Conditions : Offre limitee a 1 par personne et par jour.
Non cumulable avec d'autres offres.

Se desinscrire : mcdonalds.fr/preferences""",
        date=base - timedelta(days=2, hours=6),
        has_list_unsubscribe=True,
    ))

    # Hall's Beer event
    emails.append(_make_email(
        user_id, from_address="events@hallsbeer.fr",
        from_name="Hall's Beer Paris",
        subject="Ce week-end: soiree quiz + happy hour!",
        body="""Hall's Beer Paris

Ce week-end chez Hall's Beer !

SAMEDI 29 MARS

18h-20h : HAPPY HOUR
  Toutes les pintes a 5\u20ac !
  Cocktails classiques a 7\u20ac

20h30 : SOIREE QUIZ
  Equipes de 2 a 6 joueurs
  Themes : culture geek, musique, cinema
  A gagner : bons de consommation !

Reservez votre table :
  hallsbeer.fr/reservation
  ou au 01 42 46 78 90

Hall's Beer
12 rue du Faubourg Saint-Martin, 75010 Paris

Se desinscrire : hallsbeer.fr/unsubscribe""",
        date=base - timedelta(days=3, hours=4),
        has_list_unsubscribe=True,
    ))

    # Booking.com reminder
    emails.append(_make_email(
        user_id, from_address="noreply@booking.com", from_name="Booking.com",
        subject="Hotel Ibis Lyon - les prix baissent!",
        body="""Booking.com

Bonne nouvelle, Arthur !

L'Hotel Ibis Lyon Centre que vous avez consulte
a baisse ses prix !

Ibis Lyon Centre Part-Dieu
  Note : 8.1/10 (2 847 avis)
  A partir de : 65\u20ac/nuit (au lieu de 78\u20ac)
  Annulation gratuite

Autres suggestions a Lyon :
  - Premiere Classe Lyon Centre : des 42\u20ac
  - B&B Hotel Lyon Centre : des 55\u20ac
  - Mercure Lyon Centre Beaux-Arts : des 89\u20ac

Reserve vite, il ne reste que 3 chambres a ce prix !

Voir l'offre : booking.com/hotel/ibis-lyon

Se desinscrire : booking.com/mysettings""",
        date=base - timedelta(days=5, hours=6),
        has_list_unsubscribe=True,
    ))

    # EDF energy bill notification
    emails.append(_make_email(
        user_id, from_address="ne-pas-repondre@edf.fr", from_name="EDF",
        subject="Votre facture EDF est disponible",
        body="""EDF

Votre facture d'electricite

Numero client : 1234 5678 9012
Periode : 01/02/2026 - 28/02/2026
Reference facture : EDF-2026-03-8847

Consommation :
  Electricite (1 247 kWh)           62,35 \u20ac
  Abonnement                         8,95 \u20ac
  Taxes et contributions             -3,48 \u20ac
  ----------------------------------
  Total TTC :                        67,82 \u20ac
  TVA (5.5%) :                        3,54 \u20ac

Mode de paiement : Prelevement automatique
Date de prelevement : 05/04/2026
IBAN : FR76 **** **** **** **** ***2 34

Consultez votre facture detaillee dans votre espace client.
particulier.edf.fr

Ce message est informatif, ne pas repondre.""",
        date=base - timedelta(days=3, hours=9),
    ))

    # Picard welcome
    emails.append(_make_email(
        user_id, from_address="bienvenue@picard.fr", from_name="Picard",
        subject="Bienvenue dans le programme fidelite Picard!",
        body="""Picard

Felicitations Arthur !

Votre carte de fidelite Picard est desormais activee !

Votre numero fidelite : 9876 5432 1098
Points cumules : 0 point

Pour bien demarrer, profitez de -10% sur votre prochain achat
avec le code BIENVENUE10.

Comment ca marche :
  - 1\u20ac depense = 1 point
  - 50 points = bon de reduction de 5\u20ac
  - Points valables 12 mois

Presentez votre carte (ou l'app Picard) en caisse
pour cumuler vos points.

Code promo : BIENVENUE10
Valable 30 jours, a partir du 16/03/2026.

L'equipe Picard

Se desinscrire : picard.fr/preferences""",
        date=base - timedelta(days=10, hours=4),
        has_list_unsubscribe=True,
    ))

    # Twitter/X notification
    emails.append(_make_email(
        user_id, from_address="notify@x.com", from_name="X",
        subject="@elikihe a aime votre post",
        body="""X (formerly Twitter)

Nouvelles interactions sur votre post :

@elikihe a aime votre post
@dev_thomas a aime votre post
@sarah_code a aime votre post
@ml_enthusiast a retweete votre post

Votre post :
"Building an AI-powered accounting backend with Django + Claude.
The pipeline extracts transactions from emails with 95% accuracy.
Thread below..."

  12 likes | 3 retweets | 5 replies

Voir les interactions : x.com/arthurl/status/123456789

Se desinscrire : x.com/settings/notifications""",
        date=base - timedelta(days=1, hours=5),
        has_list_unsubscribe=True,
    ))

    # SFR newsletter
    emails.append(_make_email(
        user_id, from_address="offres@sfr.fr", from_name="SFR",
        subject="Fibre SFR: 1 Gb/s a 22.99 EUR/mois!",
        body="""SFR

Passez a la Fibre SFR !

Offre SFR Fibre Power :
  Debit : 1 Gb/s en download / 700 Mb/s en upload
  TV : 160+ chaines incluses (SFR TV)
  Telephonie : Appels illimites vers fixes et mobiles
  Prix : 22,99\u20ac/mois pendant 12 mois (puis 42,99\u20ac)

Engagement : 12 mois

Avantages :
  - Installation gratuite
  - Box SFR derniere generation incluse
  - Netflix Standard offert 3 mois

Tester mon eligibilite : sfr.fr/fibre

Se desinscrire : sfr.fr/gestion-abonnement""",
        date=base - timedelta(days=7, hours=3),
        has_list_unsubscribe=True,
    ))

    # Duolingo reminder
    emails.append(_make_email(
        user_id, from_address="hello@duolingo.com", from_name="Duolingo",
        subject="Arthur, tu n'as pas fait ta lecon aujourd'hui!",
        body="""Duolingo

Arthur, ton hibou est triste !

Tu as une serie de 42 jours en espagnol.
Ne la perds pas !

Ta progression :
  - Espagnol : Niveau A2 (42 jours)
  - Lecon du jour : Les verbes au passe
  - XP total : 12 450 XP
  - Classement : Ligue Rubis (#7)

Fais ta lecon maintenant :
  https://www.duolingo.com/learn

5 minutes suffisent !

Se desinscrire : duolingo.com/settings""",
        date=base - timedelta(days=1, hours=7),
        has_list_unsubscribe=True,
    ))

    # RATP info trafic
    emails.append(_make_email(
        user_id, from_address="info-trafic@ratp.fr", from_name="RATP",
        subject="Info trafic - Perturbations ligne 5 demain",
        body="""RATP - Info Trafic

Bonjour,

Perturbations prevues demain sur votre ligne habituelle :

Ligne 5 du metro :
  - Travaux entre Gare du Nord et Republique
  - Service interrompu de 21h30 a fin de service
  - Bus de remplacement disponibles

Alternatives suggerees :
  - Ligne 4 : Gare du Nord > Strasbourg Saint-Denis
  - Ligne 7 : Gare de l'Est > Republique
  - Bus 38 : Gare du Nord > Republique

Consultez l'etat du trafic en temps reel :
  ratp.fr/trafic ou sur l'app RATP

Se desinscrire : ratp.fr/alertes""",
        date=base - timedelta(days=2, hours=5),
        has_list_unsubscribe=True,
    ))

    # Medium weekly digest
    emails.append(_make_email(
        user_id, from_address="noreply@medium.com", from_name="Medium",
        subject="Your weekly reading list",
        body="""Medium - Weekly Digest

Hi Arthur, here are this week's top stories for you:

1. "Building Production-Ready AI Agents" by Sarah Chen
   How to design robust agentic systems that don't hallucinate.
   8 min read | 4.2K claps

2. "Django at Scale: Lessons from 10M Users" by Mike Torres
   Performance tips for large Django deployments.
   12 min read | 2.8K claps

3. "The Future of Accounting is AI" by Emma Davis
   Why manual bookkeeping will disappear by 2030.
   6 min read | 1.5K claps

Based on your interests: Python, AI, Startups

Read more: medium.com/feed

Unsubscribe: medium.com/me/settings""",
        date=base - timedelta(days=3, hours=10),
        has_list_unsubscribe=True,
    ))

    # Notion workspace update
    emails.append(_make_email(
        user_id, from_address="notify@makenotion.com", from_name="Notion",
        subject="Updates in your Nova Ledger workspace",
        body="""Notion

Activity in your workspace: Nova Ledger

Recent updates:

- Marie L. edited "Sprint 12 - Banking Integration"
  Changed status to "In Progress"
  Added 3 new tasks

- Thomas R. commented on "AI Pipeline Architecture"
  "Should we add a 5th pass for receipt matching?"

- Sophie D. completed "Setup Powens OAuth Flow"
  Moved to Done column

3 pages updated in the last 24 hours.

View workspace: notion.so/nova-ledger

Manage notifications: notion.so/settings""",
        date=base - timedelta(days=1, hours=3),
        has_list_unsubscribe=True,
    ))

    # Google Calendar reminder
    emails.append(_make_email(
        user_id, from_address="calendar-notification@google.com",
        from_name="Google Agenda",
        subject="Rappel : Dentiste demain a 14h30",
        body="""Google Agenda

Rappel d'evenement

Dentiste - Dr. Moreau
Quand : demain, 27/03/2026 a 14h30 - 15h30
Ou : Cabinet dentaire, 8 rue de Maubeuge, 75009 Paris

Notes : Detartrage annuel. Apporter carte mutuelle.

Evenement cree par : arthur.lassegue@gmail.com

Ouvrir dans Google Agenda :
  calendar.google.com/event/abc123

Ajouter une note | Modifier | Supprimer""",
        date=base - timedelta(days=1, hours=10),
    ))

    # Leetcode weekly
    emails.append(_make_email(
        user_id, from_address="no-reply@leetcode.com", from_name="LeetCode",
        subject="Weekly contest 389 results + new problems",
        body="""LeetCode

Hi Arthur,

Weekly Contest 389 Results:
  Your rank: #2,847 / 28,412 participants
  Problems solved: 3/4
  Rating change: +27 (new rating: 1,842)

New problems this week:
  - #3412 Merge K Sorted Bank Transactions (Medium)
  - #3413 Minimum Cost Email Pipeline (Hard)
  - #3414 Valid Receipt Parser (Easy)

Your streak: 15 days
Problems solved this month: 23

Keep coding!
The LeetCode Team

Unsubscribe: leetcode.com/settings""",
        date=base - timedelta(days=2, hours=4),
        has_list_unsubscribe=True,
    ))

    # Vinted notification
    emails.append(_make_email(
        user_id, from_address="noreply@vinted.fr", from_name="Vinted",
        subject="Quelqu'un a aime votre article!",
        body="""Vinted

Bonne nouvelle !

2 personnes ont ajoute votre article a leurs favoris :

Veste Zara Homme taille M
  Prix : 25,00\u20ac
  Etat : Tres bon etat
  Taille : M
  Marque : Zara
  Mise en ligne : il y a 3 jours
  Vues : 47 | Favoris : 2

Conseil : baissez le prix de 10% pour vendre plus vite !
Nouveau prix suggere : 22,50\u20ac

Voir votre article : vinted.fr/items/123456

Se desinscrire : vinted.fr/settings/notifications""",
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

        # Read bank transactions grouped by vendor (EUR only to avoid duplicates)
        bank_txs = BankTransaction.objects.filter(
            user_id=user_id, account__currency="EUR"
        ).order_by("date")
        vendors = {}
        for tx in bank_txs:
            key = tx.simplified_wording or tx.original_wording or "UNKNOWN"
            vendors.setdefault(key, []).append(tx)

        self.stdout.write(f"\nBank transactions (EUR): {bank_txs.count()} total")
        for k, v in sorted(vendors.items(), key=lambda x: -len(x[1])):
            self.stdout.write(f"  {len(v):>3}x {k}")

        emails = []

        # -------------------------------------------------------------------
        # 1. SNCF - email for most train tickets
        # -------------------------------------------------------------------
        for tx in vendors.get("SNCF", []):
            if random.random() < 0.80:
                emails.append(_sncf_email(user_id, tx))

        # -------------------------------------------------------------------
        # 2. UBER EATS - always sends receipts
        # -------------------------------------------------------------------
        for tx in vendors.get("UBER EATS", []):
            emails.append(_uber_eats_email(user_id, tx))

        # -------------------------------------------------------------------
        # 3. MONOPRIX - only ~30% get receipt emails
        # -------------------------------------------------------------------
        for tx in vendors.get("MONOPRIX", []):
            if random.random() < 0.30:
                emails.append(_monoprix_email(user_id, tx))

        # -------------------------------------------------------------------
        # 4. GOOGLE *BUDGEA - always sends invoices
        # -------------------------------------------------------------------
        for tx in vendors.get("GOOGLE *BUDGEA", []):
            emails.append(_google_budgea_email(user_id, tx))

        # -------------------------------------------------------------------
        # 5. ALLORESTO.FR PARIS - most orders get confirmations
        # -------------------------------------------------------------------
        for tx in vendors.get("ALLORESTO.FR PARIS", []):
            if random.random() < 0.75:
                emails.append(_alloresto_email(user_id, tx))

        # -------------------------------------------------------------------
        # 6. MCDO - only ~20% get emails (mostly card swipes)
        # -------------------------------------------------------------------
        for tx in vendors.get("MCDO", []):
            if random.random() < 0.20:
                emails.append(_mcdo_email(user_id, tx))

        # -------------------------------------------------------------------
        # 7. SALAIRE - NO emails (bank-only scenario)
        # -------------------------------------------------------------------
        # Intentionally skipped

        # -------------------------------------------------------------------
        # 8. HALL'S BEER - occasional receipt ~25%
        # -------------------------------------------------------------------
        for tx in vendors.get("HALL'S BEER", []):
            if random.random() < 0.25:
                emails.append(_halls_beer_email(user_id, tx))

        # -------------------------------------------------------------------
        # 9. FRANPRIX - ~20% receipt emails
        # -------------------------------------------------------------------
        for tx in vendors.get("FRANPRIX PARIS 10", []):
            if random.random() < 0.20:
                emails.append(_franprix_email(user_id, tx))

        # -------------------------------------------------------------------
        # 10. DOCTEUR - ~40% get Doctolib recap
        # -------------------------------------------------------------------
        for tx in vendors.get("DOCTEUR", []):
            if random.random() < 0.40:
                emails.append(_docteur_email(user_id, tx))

        # -------------------------------------------------------------------
        # 11. THE BOOTLAGERS - ~30% receipt
        # -------------------------------------------------------------------
        for tx in vendors.get("THE BOOTLAGERS PARIS", []):
            if random.random() < 0.30:
                emails.append(_bootlagers_email(user_id, tx))

        # -------------------------------------------------------------------
        # 12. TABAC DE LA REY - ~25% receipt
        # -------------------------------------------------------------------
        for tx in vendors.get("TABAC DE LA REY PARIS", []):
            if random.random() < 0.25:
                emails.append(_tabac_email(user_id, tx))

        # -------------------------------------------------------------------
        # Bank-only vendors (no emails): BNP PARIBAS (ATM),
        # SOCIETE GENERALE (ATM), LA BANQUE POSTALE (ATM),
        # DEBIT MENSUEL CARTE, CHEQUE, empty wording
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
