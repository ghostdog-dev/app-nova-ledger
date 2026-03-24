# Auth System Design -- Nova Ledger

**Date :** 2026-03-24
**Statut :** Draft
**Etape :** 1 -- Systeme d'authentification

---

## 1. Overview

Nova Ledger est une application Django backend only exposant une API REST. Il n'y a pas de frontend : l'API est consommee par des clients externes.

Cette specification couvre la premiere etape du projet : la mise en place du systeme d'authentification. Le systeme supporte l'inscription par email/mot de passe ainsi que l'authentification via providers OAuth (Google, Microsoft).

---

## 2. Tech Stack

| Composant | Technologie |
|---|---|
| Langage | Python 3.13+ |
| Framework | Django 5.2+ |
| API | Django REST Framework |
| Auth OAuth | django-allauth (providers Google + Microsoft) |
| Auth REST | dj-rest-auth (endpoints REST pour allauth) |
| JWT | djangorestframework-simplejwt (SimpleJWT) |
| Configuration | python-dotenv |

---

## 3. Custom User Model

L'application `accounts` definit un modele utilisateur personnalise `CustomUser` qui herite de `AbstractUser`.

**Decisions de conception :**

- Le champ `username` est supprime (`username = None`).
- Le champ `email` est utilise comme identifiant unique (`USERNAME_FIELD = "email"`).
- `REQUIRED_FIELDS = []` (aucun champ supplementaire requis a la creation).
- Un `CustomUserManager` personnalise surcharge les methodes `create_user` et `create_superuser` pour gerer la creation d'utilisateurs sans username.
- Le setting `AUTH_USER_MODEL = "accounts.CustomUser"` doit etre defini avant la premiere migration.

---

## 4. Authentication Endpoints

Tous les endpoints sont exposes sous le prefixe `/api/auth/`.

| Endpoint | Methode | Description |
|---|---|---|
| `/api/auth/registration/` | POST | Inscription par email et mot de passe |
| `/api/auth/login/` | POST | Connexion par email et mot de passe, retourne un JWT |
| `/api/auth/token/refresh/` | POST | Rafraichissement du access token via le refresh token |
| `/api/auth/logout/` | POST | Deconnexion (invalidation du token) |
| `/api/auth/password/set/` | POST | Definir un mot de passe (pour les utilisateurs OAuth sans mot de passe) |
| `/api/auth/google/` | POST | Connexion ou inscription via Google OAuth |
| `/api/auth/microsoft/` | POST | Connexion ou inscription via Microsoft OAuth |

---

## 5. OAuth Configuration

### Google

- **Scopes demandes :** `email`, `profile`, `gmail.readonly`
- **Parametre supplementaire :** `access_type: offline` pour obtenir un refresh token des le premier login.

### Microsoft

- **Scopes demandes :** `email`, `profile`, `openid`, `Mail.Read`, `offline_access`
- Le scope `offline_access` garantit l'obtention d'un refresh token des le premier login.

### Stockage des tokens

Les tokens OAuth (access et refresh) sont stockes via les modeles `SocialAccount` et `SocialToken` fournis par django-allauth. Cela permet de reutiliser les tokens pour acceder aux API tierces (lecture d'emails notamment) sans redemander l'autorisation a l'utilisateur.

---

## 6. Account Linking Strategy

La strategie de liaison de comptes repose sur l'email verifie comme cle de rapprochement.

**Configuration :**

- `SOCIALACCOUNT_EMAIL_AUTHENTICATION = True` : auto-liaison par email verifie.
- `SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True` : connexion automatique sans confirmation manuelle.
- Verification d'email obligatoire (`ACCOUNT_EMAIL_VERIFICATION = "mandatory"`).

**Scenarios :**

1. **Email/mdp existant + login provider avec le meme email** : le provider est automatiquement lie au compte existant.
2. **Compte cree via provider, sans mot de passe** : l'utilisateur peut definir un mot de passe via `/api/auth/password/set/`.
3. **Google + Microsoft avec le meme email** : les deux providers sont lies au meme compte utilisateur.
4. **Email different** : un compte distinct est cree. Chaque email correspond a un compte unique.

---

## 7. JWT Configuration

L'authentification est entierement stateless, basee sur des tokens JWT.

- **Access token** : courte duree de vie.
- **Refresh token** : longue duree de vie, permet de renouveler l'access token.
- **Pas de session Django** : aucune session cote serveur, tout passe par les tokens JWT.
- **`JWT_AUTH_HTTPONLY = True`** : les cookies JWT sont marques HttpOnly pour empecher l'acces via JavaScript.

---

## 8. Project Structure

```
nova-ledger/
  manage.py
  requirements.txt
  .env.example
  nova_ledger/
    __init__.py
    settings.py
    urls.py
    wsgi.py
    asgi.py
  accounts/
    __init__.py
    models.py
    managers.py
    admin.py
    serializers.py
    urls.py
```

- **`nova_ledger/`** : package de configuration du projet Django (settings, urls racine, wsgi/asgi).
- **`accounts/`** : application dediee a l'authentification (modele utilisateur, manager, serializers, endpoints).

---

## 9. Security

- **Secrets dans `.env`** : toutes les cles sensibles (SECRET_KEY, credentials OAuth, etc.) sont stockees dans un fichier `.env` qui n'est jamais commite.
- **Verification d'email obligatoire** : un email doit etre verifie avant qu'un compte OAuth puisse y etre lie. Cela empeche un attaquant de lier un provider a un compte dont il ne controle pas l'email.
- **HTTPS en production** : toutes les communications sont chiffrees en production. Les cookies JWT (HttpOnly) ne sont transmis que sur des connexions securisees.
