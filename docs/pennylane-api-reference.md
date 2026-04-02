# Pennylane API v2 - Complete Technical Reference

> Source: https://pennylane.readme.io/ (OpenAPI spec version 2.0)
> Contact: tech@pennylane.com
> Last researched: 2026-03-27

---

## 1. Base URL

```
https://app.pennylane.com
```

All endpoints are prefixed with `/api/external/v2/`.

---

## 2. Authentication

### 2.1 Company API Token (Bearer Token)

**Header format:**
```
Authorization: Bearer <YOUR_COMPANY_API_TOKEN>
```

**Requirements:**
- Pennylane Essential plan or higher
- Admin access (Executive, Internal Accountant, or External Accountant roles)

**Generation:**
1. Navigate to **Management > Settings > Connectivity > Developers**
2. Click "Generate an API Token"
3. Enter a descriptive name (e.g. "nova-ledger-sync")
4. Select permission level under API V2:
   - **Read only** -- retrieve data only
   - **Read and write** -- create or update data
5. Choose expiration: **1 month**, **6 months**, **12 months**, or **Unlimited**
6. Click "Generate Token"
7. Copy immediately -- **tokens are shown only once and cannot be retrieved later**

**Token management:**
- One token per company link; companies may have multiple tokens
- View token name, scopes, creation/expiration dates, last usage
- Deletion is irreversible and immediately revokes API access

**Error responses:**
- `401 Unauthorized` -- invalid or missing token
- `403 Forbidden` -- insufficient scope permissions
- `404 Not Found` -- incorrect endpoint

### 2.2 OAuth 2.0 (for Integration Partners)

**Grant type:** Authorization Code

**Authorization endpoint:**
```
GET https://app.pennylane.com/oauth/authorize
```
Parameters:
- `client_id` (required) -- from app registration
- `redirect_uri` (required) -- callback URL
- `response_type` (required) -- must be `code`
- `scope` (required) -- space-separated scope list
- `state` (optional) -- CSRF prevention token

**Token exchange endpoint:**
```
POST https://app.pennylane.com/oauth/token
```
Parameters:
- `client_id`, `client_secret` -- credentials from registration
- `code` -- authorization code from step 1
- `redirect_uri` -- must match authorization request
- `grant_type` -- must be `authorization_code`

**Token response:**
```json
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "refresh_token": "..."
}
```

**Token refresh:**
```
POST https://app.pennylane.com/oauth/token
```
Parameters:
- `grant_type`: `refresh_token`
- `refresh_token`: token from initial exchange
- `client_id`, `client_secret`

**Token lifecycle:**
- Access tokens: **24 hours** (86400 seconds)
- Refresh tokens: **90 days**; revoked upon use and replaced with new token

**Token revocation:**
```
POST https://app.pennylane.com/oauth/revoke
```
Parameters: `client_id`, `client_secret`, `token`
Response: HTTP 200 with empty body

**Registration:** Contact Pennylane Partnerships team to receive Client ID and Client Secret.

### 2.3 All OAuth Scopes

| Scope | Description |
|-------|-------------|
| `customer_invoices:readonly` | Read customer invoices |
| `customer_invoices:all` | Read + write customer invoices |
| `supplier_invoices:readonly` | Read supplier invoices |
| `supplier_invoices:all` | Read + write supplier invoices |
| `customers:readonly` | Read customers |
| `customers:all` | Read + write customers |
| `suppliers:readonly` | Read suppliers |
| `suppliers:all` | Read + write suppliers |
| `products:readonly` | Read products |
| `products:all` | Read + write products |
| `transactions:readonly` | Read bank transactions |
| `transactions:all` | Read + write bank transactions |
| `bank_accounts:readonly` | Read bank accounts |
| `bank_accounts:all` | Read + write bank accounts |
| `bank_establishments:readonly` | Read bank establishments |
| `ledger_entries:readonly` | Read ledger entries |
| `ledger_entries:all` | Read + write ledger entries |
| `ledger_accounts:readonly` | Read ledger accounts |
| `ledger_accounts:all` | Read + write ledger accounts |
| `journals:readonly` | Read journals |
| `journals:all` | Read + write journals |
| `quotes:readonly` | Read quotes |
| `quotes:all` | Read + write quotes |
| `categories:readonly` | Read categories |
| `categories:all` | Read + write categories |
| `billing_subscriptions:readonly` | Read billing subscriptions |
| `billing_subscriptions:all` | Read + write billing subscriptions |
| `customer_invoice_templates:readonly` | Read invoice templates |
| `customer_mandates:readonly` | Read mandates |
| `customer_mandates:all` | Read + write mandates |
| `commercial_documents:readonly` | Read commercial documents |
| `commercial_documents:all` | Read + write commercial documents |
| `purchase_requests:readonly` | Read purchase requests |
| `purchase_requests:all` | Read + write purchase requests |
| `file_attachments:readonly` | Read file attachments |
| `file_attachments:all` | Read + write file attachments |
| `e_invoices:all` | E-invoicing imports |
| `fiscal_years:readonly` | Read fiscal years |
| `trial_balance:readonly` | Read trial balance |
| `exports:fec` | FEC exports |
| `exports:agl` | Analytical general ledger exports |
| `ledger` | (DEPRECATED) Legacy ledger scope |

---

## 3. Rate Limiting

**Global limit:** 25 requests per 5-second window (applies to all endpoints).

Enforced at the **token level**:
- OAuth apps: applied per generated token independently
- Developer tokens: applied directly to the token

**Response headers on ALL requests:**
| Header | Description | Example |
|--------|-------------|---------|
| `ratelimit-limit` | Max requests per window | `25` |
| `ratelimit-remaining` | Requests remaining in window | `22` |
| `ratelimit-reset` | Unix timestamp of window reset | `1770379510` |

**Additional header on 429 errors:**
| Header | Description |
|--------|-------------|
| `retry-after` | Seconds to wait before retrying |

**429 response example:**
```
HTTP/2 429 Too Many Requests
retry-after: 2
ratelimit-limit: 25
ratelimit-remaining: 0
ratelimit-reset: 1770379510

Rate limit exceeded. Please retry in 2 seconds.
```

---

## 4. Pagination

### 4.1 Cursor-Based Pagination (Current)

All list endpoints support cursor-based pagination.

**Request parameters:**
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `cursor` | string | - | - | Opaque cursor from previous response |
| `limit` | integer | 20 | 1-100 (1-1000 for some) | Items per request |

**Response fields:**
```json
{
  "has_more": true,
  "next_cursor": "eyJpZCI6MTAwfQ==",
  "total_pages": null,
  "current_page": null,
  "per_page": null,
  "total_items": null,
  "items": [...]
}
```

**End of list detection:** `has_more` is `false` AND/OR `next_cursor` is `null`.

### 4.2 Legacy Offset Pagination (Deprecated)

| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `page` | integer | 1 | starts at 1 |
| `per_page` | integer | 20 | 1-100 |

Legacy response:
```json
{
  "total_pages": 5,
  "current_page": 1,
  "total_items": 98,
  "per_page": 20,
  "has_more": null,
  "next_cursor": null,
  "items": [...]
}
```

### 4.3 Migration Parameter

`use_2026_api_changes` (boolean, default: `true`) -- controls pagination system. Can also be set via header `X-Use-2026-API-Changes`.

---

## 5. Filtering & Sorting

### 5.1 Filter Syntax

Filters are passed as a **JSON-encoded array** in the `filter` query parameter.

Each filter object:
```json
{"field": "<field_name>", "operator": "<operator>", "value": "<value>"}
```

**Operators:**
| Operator | Description | Value type |
|----------|-------------|------------|
| `eq` | Equals | single value |
| `not_eq` | Not equals | single value |
| `lt` | Less than | single value |
| `gt` | Greater than | single value |
| `lteq` | Less than or equal | single value |
| `gteq` | Greater than or equal | single value |
| `in` | In array | array |
| `not_in` | Not in array | array |
| `start_with` | Prefix match | single value |

**Example -- date range + customer filter:**
```
GET /api/external/v2/customer_invoices?filter=[
  {"field":"date","operator":"gteq","value":"2024-01-01"},
  {"field":"date","operator":"lteq","value":"2024-03-31"},
  {"field":"customer_id","operator":"eq","value":"42"}
]
```

(The JSON array must be URL-encoded in practice.)

### 5.2 Sort Syntax

Pass `sort` query parameter. Prefix with `-` for descending.

```
GET /api/external/v2/customer_invoices?sort=-date
GET /api/external/v2/customer_invoices?sort=invoice_number
```

### 5.3 Filterable Fields Per Resource

**Customer Invoices:**
| Field | Operators |
|-------|-----------|
| `id` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `customer_id` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `date` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `invoice_number` | eq, not_eq, in, not_in |
| `billing_subscription_id` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `estimate_id` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `category_id` | in |

**Supplier Invoices:**
| Field | Operators |
|-------|-----------|
| `id` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `supplier_id` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `invoice_number` | eq, not_eq, in, not_in |
| `date` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `category_id` | in |
| `external_reference` | eq, not_eq, in, not_in |

**Customers:**
| Field | Operators |
|-------|-----------|
| `id` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `customer_type` | eq, not_eq |
| `ledger_account_id` | eq, not_eq |
| `name` | start_with |
| `external_reference` | eq, not_eq, in, not_in |
| `reg_no` | eq, not_eq, in, not_in |

**Suppliers:**
| Field | Operators |
|-------|-----------|
| `id` | eq, not_eq, lt, gt, lteq, gteq, in, not_in |
| `ledger_account_id` | eq, not_eq |
| `name` | start_with |
| `external_reference` | eq, not_eq, in, not_in |

---

## 6. Data Formats

| Data type | Format | Example |
|-----------|--------|---------|
| **Amounts** | String (decimal, NOT cents) | `"230.32"`, `"50.4"` |
| **Currency** | ISO 4217 string | `"EUR"`, `"USD"`, `"GBP"` |
| **Dates** | ISO 8601 date | `"2023-08-30"` |
| **Datetimes** | ISO 8601 datetime | `"2023-08-30T10:08:08.146343Z"` |
| **IDs** | Integer (int64) | `42` |
| **VAT rates** | Country-prefixed string | `"FR_200"` (= 20.0% France) |
| **Booleans** | JSON boolean | `true`, `false` |

**Amount convention:**
- `amount` = total in EUR (always converted to euros)
- `currency_amount` = total in invoice/transaction currency
- `currency_amount_before_tax` = pre-tax amount in currency
- `currency_tax` / `tax` = tax amount (currency / EUR)
- If currency is EUR, `amount` == `currency_amount`
- `exchange_rate` = conversion rate to EUR (1.0 if already EUR)

---

## 7. All Endpoints for Financial Data

### 7.1 Customer Invoices

#### List Customer Invoices
```
GET /api/external/v2/customer_invoices
```
**Scopes:** `customer_invoices:all` | `customer_invoices:readonly`

**Query parameters:** `cursor`, `limit`, `filter`, `sort`, `include` (experimental: `invoice_lines`)

**Response:**
```json
{
  "has_more": true,
  "next_cursor": "eyJpZCI6MTAwfQ==",
  "total_pages": null,
  "current_page": null,
  "per_page": null,
  "total_items": null,
  "items": [
    {
      "id": 42,
      "label": "Invoice label",
      "invoice_number": "F20230001",
      "currency": "EUR",
      "amount": "230.32",
      "currency_amount": "230.32",
      "currency_amount_before_tax": "196.32",
      "exchange_rate": "1.0",
      "date": "2023-08-30",
      "deadline": "2023-09-30",
      "currency_tax": "34.0",
      "tax": "34.0",
      "language": "fr_FR",
      "paid": false,
      "status": "upcoming",
      "discount": {
        "type": "relative",
        "value": "25"
      },
      "ledger_entry": {
        "id": 42002
      },
      "public_file_url": "https://app.pennylane.com/public/invoice/pdf?encrypted_id=...",
      "filename": "my_file.pdf",
      "remaining_amount_with_tax": "20.0",
      "remaining_amount_without_tax": "16.0",
      "draft": false,
      "special_mention": "Additional details",
      "customer": {
        "id": 42,
        "url": "https://app.pennylane.com/api/external/v2/customers/42"
      },
      "invoice_line_sections": {
        "url": "https://app.pennylane.com/api/external/v2/customer_invoices/42/invoice_line_sections"
      },
      "invoice_lines": {
        "url": "https://app.pennylane.com/api/external/v2/customer_invoices/42/invoice_lines"
      },
      "custom_header_fields": {
        "url": "https://app.pennylane.com/api/external/v2/customer_invoices/42/custom_header_fields"
      },
      "categories": {
        "url": "https://app.pennylane.com/api/external/v2/customer_invoices/42/categories"
      },
      "pdf_invoice_free_text": "Thanks for paying this invoice",
      "pdf_invoice_subject": "Invoice subject",
      "pdf_description": "Invoice description",
      "billing_subscription": null,
      "credited_invoice": null,
      "customer_invoice_template": null,
      "transaction_reference": null,
      "payments": {
        "url": "https://app.pennylane.com/api/external/v2/customer_invoices/42/payments"
      },
      "matched_transactions": {
        "url": "https://app.pennylane.com/api/external/v2/customer_invoices/42/matched_transactions"
      },
      "appendices": {
        "url": "https://app.pennylane.com/api/external/v2/customer_invoices/42/appendices"
      },
      "quote": null,
      "external_reference": "FR123",
      "e_invoicing": null,
      "archived_at": null,
      "created_at": "2023-08-30T10:08:08.146343Z",
      "updated_at": "2023-08-30T10:08:08.146343Z"
    }
  ]
}
```

**Customer invoice `status` values:**
- `draft` -- not finalized
- `upcoming` -- finalized, not yet due
- `late` -- past deadline, unpaid
- `paid` -- fully paid
- `partially_paid` -- partial payment received
- `cancelled` -- cancelled
- `partially_cancelled` -- partially cancelled
- `archived` -- archived
- `incomplete` -- incomplete data
- `credit_note` -- credit note
- `proforma` -- proforma invoice
- `shipping_order` -- shipping order
- `purchasing_order` -- purchasing order
- `estimate_pending` / `estimate_accepted` / `estimate_invoiced` / `estimate_denied` -- quote-related

#### Retrieve a Customer Invoice
```
GET /api/external/v2/customer_invoices/{id}
```
**Scopes:** `customer_invoices:all` | `customer_invoices:readonly`

Returns the same object structure as a single item from the list above.

#### List Invoice Lines for a Customer Invoice
```
GET /api/external/v2/customer_invoices/{customer_invoice_id}/invoice_lines
```
**Scopes:** `customer_invoices:all` | `customer_invoices:readonly`

**Response item:**
```json
{
  "id": 444,
  "label": "Demo label",
  "unit": "piece",
  "quantity": "12",
  "amount": "50.4",
  "currency_amount": "50.4",
  "description": "Lorem ipsum dolor sit amet...",
  "product": {
    "id": 3049,
    "url": "https://app.pennylane.com/api/external/v2/products/42"
  },
  "vat_rate": "FR_200",
  "currency_amount_before_tax": "30",
  "currency_tax": "10",
  "tax": "10",
  "raw_currency_unit_price": "5",
  "discount": {
    "type": "relative",
    "value": "25"
  },
  "section_rank": 1,
  "imputation_dates": {
    "start_date": "2020-06-30",
    "end_date": "2021-06-30"
  },
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z"
}
```

#### List Payments for a Customer Invoice
```
GET /api/external/v2/customer_invoices/{customer_invoice_id}/payments
```
**Scopes:** `customer_invoices:all` | `customer_invoices:readonly`

**Response item:**
```json
{
  "id": 444,
  "label": "Demo label",
  "currency": "EUR",
  "currency_amount": "230.32",
  "status": "found",
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z"
}
```

**Payment `status` values:**
`draft`, `initiated`, `pending`, `emitted`, `found`, `not_found`, `aborted`, `error`, `refunded`, `prepared`, `pending_customer_approval`, `pending_submission`, `submitted`, `confirmed`, `paid_out`, `cancelled`, `customer_approval_denied`, `failed`, `charged_back`, `resubmission_requested`

#### List Matched Transactions for a Customer Invoice
```
GET /api/external/v2/customer_invoices/{customer_invoice_id}/matched_transactions
```

#### Other Customer Invoice Endpoints
```
POST   /api/external/v2/customer_invoices                              -- Create
POST   /api/external/v2/customer_invoices/import                       -- Import
PUT    /api/external/v2/customer_invoices/{id}                         -- Update
DELETE /api/external/v2/customer_invoices/{id}                         -- Delete
PUT    /api/external/v2/customer_invoices/{id}/finalize                -- Finalize
PUT    /api/external/v2/customer_invoices/{id}/mark_as_paid            -- Mark as paid
POST   /api/external/v2/customer_invoices/{id}/send_by_email           -- Send by email
POST   /api/external/v2/customer_invoices/create_from_quote            -- Create from quote
```

---

### 7.2 Supplier Invoices

#### List Supplier Invoices
```
GET /api/external/v2/supplier_invoices
```
**Scopes:** `supplier_invoices:all` | `supplier_invoices:readonly`

**Query parameters:** `cursor`, `limit`, `filter`, `sort`

**Response item:**
```json
{
  "id": 123,
  "label": "Demo label",
  "invoice_number": "F20230001",
  "currency": "EUR",
  "amount": "230.32",
  "currency_amount": "230.32",
  "currency_amount_before_tax": "196.32",
  "exchange_rate": "1.0",
  "date": "2023-08-30",
  "deadline": "2023-09-30",
  "currency_tax": "34.0",
  "tax": "34.0",
  "reconciled": false,
  "accounting_status": "entry",
  "filename": "my_file.pdf",
  "public_file_url": "https://app.pennylane.com/public/invoice/pdf?encrypted_id=...",
  "remaining_amount_with_tax": "20.0",
  "remaining_amount_without_tax": "16.0",
  "ledger_entry": {
    "id": 42003
  },
  "supplier": {
    "id": 456,
    "url": "https://app.pennylane.com/api/external/v2/suppliers/42"
  },
  "invoice_lines": {
    "url": "https://app.pennylane.com/api/external/v2/supplier_invoices/42/invoice_lines"
  },
  "categories": {
    "url": "https://app.pennylane.com/api/external/v2/supplier_invoices/42/categories"
  },
  "transaction_reference": null,
  "payment_status": "to_be_paid",
  "payments": {
    "url": "https://app.pennylane.com/api/external/v2/supplier_invoices/42/payments"
  },
  "matched_transactions": {
    "url": "https://app.pennylane.com/api/external/v2/supplier_invoices/42/matched_transactions"
  },
  "external_reference": "FR123",
  "e_invoicing": null,
  "archived_at": null,
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z"
}
```

**Supplier invoice `accounting_status` values:**
- `draft` -- not yet sent to accounting
- `archived` -- archived
- `entry` -- ledger entry created
- `validation_needed` -- needs accountant validation
- `complete` -- fully processed

**Supplier invoice `payment_status` values:**
`to_be_processed`, `to_be_paid`, `partially_paid`, `payment_error`, `payment_scheduled`, `payment_in_progress`, `payment_emitted`, `payment_found`, `paid_offline`, `fully_paid`

#### Retrieve a Supplier Invoice
```
GET /api/external/v2/supplier_invoices/{id}
```

#### List Supplier Invoice Lines
```
GET /api/external/v2/supplier_invoices/{supplier_invoice_id}/invoice_lines
```

**Response item:**
```json
{
  "id": 444,
  "label": "Demo label",
  "amount": "50.4",
  "currency_amount": "50.4",
  "description": "Lorem ipsum dolor sit amet...",
  "vat_rate": "FR_200",
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z"
}
```

#### List Supplier Invoice Payments
```
GET /api/external/v2/supplier_invoices/{supplier_invoice_id}/payments
```

#### Other Supplier Invoice Endpoints
```
POST   /api/external/v2/supplier_invoices/import                           -- Import
PUT    /api/external/v2/supplier_invoices/{id}                             -- Update
PUT    /api/external/v2/supplier_invoices/{id}/validate_accounting         -- Validate
PUT    /api/external/v2/supplier_invoices/{supplier_invoice_id}/payment_status -- Update payment status
```

---

### 7.3 Customers

#### List Customers
```
GET /api/external/v2/customers
```
**Scopes:** `customers:all` | `customers:readonly`

**Response item (company type):**
```json
{
  "id": 42,
  "name": "My Company SAS",
  "customer_type": "company",
  "billing_iban": "FR1420041010050500013M02606",
  "payment_conditions": "30_days",
  "recipient": "John Doe",
  "phone": "+33612345678",
  "reference": "REF-1234",
  "notes": "Some notes",
  "vat_number": "FR12345678901",
  "reg_no": "123456789",
  "ledger_account": {
    "id": 100
  },
  "emails": ["hello@example.org"],
  "billing_address": {
    "address": "10 rue de Paris",
    "postal_code": "75001",
    "city": "Paris",
    "country_alpha2": "FR"
  },
  "delivery_address": {
    "address": "10 rue de Paris",
    "postal_code": "75001",
    "city": "Paris",
    "country_alpha2": "FR"
  },
  "external_reference": "0e67fc3c-c632-4feb-ad34-e18ed5fbf66a",
  "billing_language": "fr_FR",
  "mandates": {
    "url": "https://app.pennylane.com/api/external/v2/gocardless_mandates?filter=..."
  },
  "pro_account_mandates": {
    "url": "https://app.pennylane.com/api/external/v2/pro_account/mandates?filter=..."
  },
  "contacts": {
    "url": "https://app.pennylane.com/api/external/v2/customers/42/contacts"
  },
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z"
}
```

**Response item (individual type) -- additional fields:**
```json
{
  "customer_type": "individual",
  "first_name": "John",
  "last_name": "Doe"
}
```

**`payment_conditions` values:**
`upon_receipt`, `custom`, `7_days`, `15_days`, `30_days`, `30_days_end_of_month`, `45_days`, `45_days_end_of_month`, `60_days`

#### Retrieve a Customer
```
GET /api/external/v2/customers/{id}
```

#### List Customer Contacts
```
GET /api/external/v2/customers/{customer_id}/contacts
```

---

### 7.4 Suppliers

#### List Suppliers
```
GET /api/external/v2/suppliers
```
**Scopes:** `suppliers:all` | `suppliers:readonly`

**Response item:**
```json
{
  "id": 42,
  "name": "Pennylane",
  "establishment_no": "82762938500014",
  "reg_no": "827629385",
  "vat_number": "FR32123456789",
  "ledger_account": {
    "id": 200
  },
  "emails": ["hello@example.org"],
  "iban": "FRXXXXXXXXXXXXXXXXXXXXXXXXX",
  "postal_address": {
    "address": "10 rue de Paris",
    "postal_code": "75001",
    "city": "Paris",
    "country_alpha2": "FR"
  },
  "supplier_payment_method": "automatic_transfer",
  "supplier_due_date_delay": 30,
  "supplier_due_date_rule": "days",
  "external_reference": "FR123",
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z"
}
```

**`supplier_payment_method` values:**
`automatic_transfer`, `manual_transfer`, `automatic_debiting`, `bill_of_exchange`, `check`, `cash`, `card`, `other`

**`supplier_due_date_rule` values:** `days`, `days_or_end_of_month`

#### Retrieve a Supplier
```
GET /api/external/v2/suppliers/{id}
```

---

### 7.5 Products

#### List Products
```
GET /api/external/v2/products
```
**Scopes:** `products:all` | `products:readonly`

**Response item:**
```json
{
  "id": 1,
  "label": "Product 1",
  "description": "This is product 1",
  "external_reference": "0e67fc3c-c632-4feb-ad34-e18ed5fbf66a",
  "price_before_tax": "12.5",
  "vat_rate": "FR_200",
  "price": "13.6",
  "unit": "piece",
  "currency": "EUR",
  "reference": "REF-123",
  "ledger_account": {
    "id": 300
  },
  "archived_at": null,
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z"
}
```

#### Retrieve a Product
```
GET /api/external/v2/products/{id}
```

---

### 7.6 Transactions (Bank Transactions)

#### List Transactions
```
GET /api/external/v2/transactions
```
**Scopes:** `transactions:all` | `transactions:readonly`

**Response item:**
```json
{
  "id": 42,
  "label": "VIR SEPA MY SUPPLIER SAS",
  "attachment_required": true,
  "date": "2023-08-30",
  "outstanding_balance": "49.3",
  "currency": "EUR",
  "currency_amount": "120.00",
  "amount": "120.00",
  "currency_fee": "0.00",
  "fee": "0.00",
  "journal": {
    "id": 234,
    "url": "https://app.pennylane.com/api/external/v2/journals/67"
  },
  "bank_account": {
    "id": 53,
    "url": "https://app.pennylane.com/api/external/v2/bank_accounts/53"
  },
  "pro_account_expense": null,
  "customer": null,
  "supplier": {
    "id": 42,
    "url": "https://app.pennylane.com/api/external/v2/supplier/42"
  },
  "categories": [
    {
      "id": 421,
      "label": "HR - Salaries",
      "weight": "0.25",
      "category_group": {
        "id": 229
      },
      "analytical_code": "CODE123",
      "created_at": "2023-08-30T10:08:08.146343Z",
      "updated_at": "2023-08-30T10:08:08.146343Z"
    }
  ],
  "matched_invoices": {
    "url": "https://app.pennylane.com/api/external/v2/transactions/42/matched_invoices"
  },
  "interbank_code": "B1D",
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z",
  "archived_at": null
}
```

#### Retrieve a Transaction
```
GET /api/external/v2/transactions/{id}
```

#### List Matched Invoices for a Transaction
```
GET /api/external/v2/transactions/{transaction_id}/matched_invoices
```

#### Other Transaction Endpoints
```
POST /api/external/v2/transactions            -- Create
PUT  /api/external/v2/transactions/{id}        -- Update
GET  /api/external/v2/transactions/{transaction_id}/categories     -- Get categories
PUT  /api/external/v2/transactions/{transaction_id}/categories     -- Update categories
```

---

### 7.7 Bank Accounts

#### List Bank Accounts
```
GET /api/external/v2/bank_accounts
```
**Scopes:** `bank_accounts:all` | `bank_accounts:readonly`

**Response item:**
```json
{
  "id": 42,
  "name": "Main account",
  "currency": "EUR",
  "bank_establishment": {
    "id": 42
  },
  "journal": {
    "id": 42,
    "url": "https://app.pennylane.com/api/external/v2/journals/7"
  },
  "ledger_account": {
    "id": 42,
    "url": "https://app.pennylane.com/api/external/v2/ledger_accounts/8"
  },
  "created_at": "2023-08-30T10:08:08.146343Z",
  "updated_at": "2023-08-30T10:08:08.146343Z"
}
```

#### Retrieve a Bank Account
```
GET /api/external/v2/bank_accounts/{id}
```

---

### 7.8 Additional Endpoints

#### Current User & Company Info
```
GET /api/external/v2/me
```
**Response:**
```json
{
  "user": {
    "id": 12345,
    "first_name": "John",
    "last_name": "Doe",
    "email": "jdoe@pennylane.com",
    "locale": "fr"
  },
  "company": {
    "id": 123456,
    "name": "Pennylane",
    "reg_no": "123456789"
  },
  "scopes": ["customer_invoices", "suppliers"]
}
```

#### Ledger Entries
```
GET  /api/external/v2/ledger_entries           -- List
GET  /api/external/v2/ledger_entries/{id}       -- Retrieve
POST /api/external/v2/ledger_entries           -- Create
PUT  /api/external/v2/ledger_entries/{id}       -- Update
```
**Scopes:** `ledger_entries:all` | `ledger_entries:readonly`

#### Ledger Entry Lines
```
GET /api/external/v2/ledger_entry_lines                                                  -- List all
GET /api/external/v2/ledger_entries/{ledger_entry_id}/ledger_entry_lines                  -- List for entry
GET /api/external/v2/ledger_entry_lines/{id}                                              -- Retrieve
```

#### Ledger Accounts
```
GET  /api/external/v2/ledger_accounts           -- List
GET  /api/external/v2/ledger_accounts/{id}       -- Retrieve
POST /api/external/v2/ledger_accounts           -- Create
PUT  /api/external/v2/ledger_accounts/{id}       -- Update
```

#### Journals
```
GET  /api/external/v2/journals                  -- List
GET  /api/external/v2/journals/{id}              -- Retrieve
POST /api/external/v2/journals                  -- Create
```

#### Trial Balance
```
GET /api/external/v2/trial_balance
```
**Scopes:** `trial_balance:readonly`

#### Fiscal Years
```
GET /api/external/v2/fiscal_years
```

#### Quotes
```
GET  /api/external/v2/quotes                    -- List
GET  /api/external/v2/quotes/{id}                -- Retrieve
POST /api/external/v2/quotes                    -- Create
PUT  /api/external/v2/quotes/{id}                -- Update
```

#### Categories & Category Groups
```
GET  /api/external/v2/categories                 -- List
GET  /api/external/v2/categories/{id}             -- Retrieve
POST /api/external/v2/categories                 -- Create
PUT  /api/external/v2/categories/{id}             -- Update
GET  /api/external/v2/category_groups             -- List groups
GET  /api/external/v2/category_groups/{id}         -- Retrieve group
```

#### Billing Subscriptions
```
GET  /api/external/v2/billing_subscriptions       -- List
GET  /api/external/v2/billing_subscriptions/{id}   -- Retrieve
POST /api/external/v2/billing_subscriptions       -- Create
PUT  /api/external/v2/billing_subscriptions/{id}   -- Update
```

#### Changelogs (Change Tracking)
```
GET /api/external/v2/changelogs/customer_invoices
GET /api/external/v2/changelogs/supplier_invoices
GET /api/external/v2/changelogs/customers
GET /api/external/v2/changelogs/suppliers
GET /api/external/v2/changelogs/products
GET /api/external/v2/changelogs/quotes
GET /api/external/v2/changelogs/ledger_entry_lines
GET /api/external/v2/changelogs/transactions
```

#### Webhooks
```
GET    /api/external/v2/webhook_subscription     -- Get subscription
POST   /api/external/v2/webhook_subscription     -- Create
PUT    /api/external/v2/webhook_subscription     -- Update
DELETE /api/external/v2/webhook_subscription     -- Delete
```
**Supported events:** `customer_invoice.created`, `quote.created`, `dms_file.created`

---

## 8. SDK Availability

**No official SDK exists.** Pennylane provides a REST API with an OpenAPI 3.0.1 specification. Integration is done via direct HTTP requests.

The OpenAPI spec can be used to auto-generate a client using tools like `openapi-generator`.

---

## 9. Django Integration Notes

### Recommended approach for nova-ledger

```python
# settings.py
PENNYLANE_API_TOKEN = env("PENNYLANE_API_TOKEN")
PENNYLANE_BASE_URL = "https://app.pennylane.com"
PENNYLANE_API_PREFIX = "/api/external/v2"

# Rate limit: 25 requests per 5 seconds = 5 req/s average
# Implement token bucket or simple sleep(0.2) between requests
```

### Client skeleton

```python
import requests
import time
from django.conf import settings


class PennylaneClient:
    BASE_URL = "https://app.pennylane.com/api/external/v2"

    def __init__(self, api_token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        })
        self._last_request_time = 0

    def _throttle(self):
        """Enforce rate limit: 25 req / 5s = 200ms between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 0.2:
            time.sleep(0.2 - elapsed)
        self._last_request_time = time.time()

    def _get(self, path: str, params: dict = None) -> dict:
        self._throttle()
        url = f"{self.BASE_URL}{path}"
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, params: dict = None, limit: int = 100):
        """Cursor-based pagination iterator."""
        params = params or {}
        params["limit"] = limit
        while True:
            data = self._get(path, params)
            yield from data.get("items", [])
            if not data.get("has_more"):
                break
            params["cursor"] = data["next_cursor"]

    # --- Customer Invoices ---

    def list_customer_invoices(self, **filters):
        return self._paginate("/customer_invoices", self._build_params(filters))

    def get_customer_invoice(self, invoice_id: int):
        return self._get(f"/customer_invoices/{invoice_id}")

    def get_customer_invoice_lines(self, invoice_id: int):
        return self._paginate(f"/customer_invoices/{invoice_id}/invoice_lines")

    def get_customer_invoice_payments(self, invoice_id: int):
        return self._paginate(f"/customer_invoices/{invoice_id}/payments")

    # --- Supplier Invoices ---

    def list_supplier_invoices(self, **filters):
        return self._paginate("/supplier_invoices", self._build_params(filters))

    def get_supplier_invoice(self, invoice_id: int):
        return self._get(f"/supplier_invoices/{invoice_id}")

    # --- Customers ---

    def list_customers(self, **filters):
        return self._paginate("/customers", self._build_params(filters))

    def get_customer(self, customer_id: int):
        return self._get(f"/customers/{customer_id}")

    # --- Suppliers ---

    def list_suppliers(self, **filters):
        return self._paginate("/suppliers", self._build_params(filters))

    def get_supplier(self, supplier_id: int):
        return self._get(f"/suppliers/{supplier_id}")

    # --- Products ---

    def list_products(self):
        return self._paginate("/products")

    def get_product(self, product_id: int):
        return self._get(f"/products/{product_id}")

    # --- Transactions ---

    def list_transactions(self, **filters):
        return self._paginate("/transactions", self._build_params(filters))

    def get_transaction(self, transaction_id: int):
        return self._get(f"/transactions/{transaction_id}")

    # --- Bank Accounts ---

    def list_bank_accounts(self):
        return self._paginate("/bank_accounts")

    # --- Utility ---

    def get_me(self):
        return self._get("/me")

    @staticmethod
    def _build_params(filters: dict) -> dict:
        """Convert filter kwargs to Pennylane filter format."""
        import json
        if not filters:
            return {}
        filter_list = []
        for key, value in filters.items():
            # Support "date__gteq" syntax
            if "__" in key:
                field, operator = key.rsplit("__", 1)
            else:
                field, operator = key, "eq"
            filter_list.append({
                "field": field,
                "operator": operator,
                "value": value,
            })
        return {"filter": json.dumps(filter_list)}
```

### Usage example

```python
client = PennylaneClient(api_token=settings.PENNYLANE_API_TOKEN)

# Fetch all invoices from 2024
for invoice in client.list_customer_invoices(date__gteq="2024-01-01"):
    print(f"#{invoice['invoice_number']} - {invoice['currency_amount']} {invoice['currency']} - {invoice['status']}")

# Get a specific supplier invoice with its lines
inv = client.get_supplier_invoice(123)
lines = list(client.get_customer_invoice_lines(123))
```

---

## 10. Complete Endpoint Index

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/external/v2/me` | Current user & company |
| **Customer Invoices** | | |
| GET | `/api/external/v2/customer_invoices` | List |
| POST | `/api/external/v2/customer_invoices` | Create |
| GET | `/api/external/v2/customer_invoices/{id}` | Retrieve |
| PUT | `/api/external/v2/customer_invoices/{id}` | Update |
| DELETE | `/api/external/v2/customer_invoices/{id}` | Delete |
| PUT | `/api/external/v2/customer_invoices/{id}/finalize` | Finalize |
| PUT | `/api/external/v2/customer_invoices/{id}/mark_as_paid` | Mark paid |
| POST | `/api/external/v2/customer_invoices/{id}/send_by_email` | Send email |
| POST | `/api/external/v2/customer_invoices/import` | Import |
| POST | `/api/external/v2/customer_invoices/create_from_quote` | From quote |
| GET | `/api/external/v2/customer_invoices/{id}/invoice_lines` | Invoice lines |
| GET | `/api/external/v2/customer_invoices/{id}/invoice_line_sections` | Line sections |
| GET | `/api/external/v2/customer_invoices/{id}/payments` | Payments |
| GET/POST | `/api/external/v2/customer_invoices/{id}/matched_transactions` | Matched txns |
| GET/POST | `/api/external/v2/customer_invoices/{id}/appendices` | Appendices |
| GET | `/api/external/v2/customer_invoices/{id}/custom_header_fields` | Custom fields |
| GET/PUT | `/api/external/v2/customer_invoices/{id}/categories` | Categories |
| **Supplier Invoices** | | |
| GET | `/api/external/v2/supplier_invoices` | List |
| POST | `/api/external/v2/supplier_invoices/import` | Import |
| GET | `/api/external/v2/supplier_invoices/{id}` | Retrieve |
| PUT | `/api/external/v2/supplier_invoices/{id}` | Update |
| PUT | `/api/external/v2/supplier_invoices/{id}/validate_accounting` | Validate |
| PUT | `/api/external/v2/supplier_invoices/{id}/payment_status` | Payment status |
| GET | `/api/external/v2/supplier_invoices/{id}/invoice_lines` | Invoice lines |
| GET | `/api/external/v2/supplier_invoices/{id}/payments` | Payments |
| GET/POST | `/api/external/v2/supplier_invoices/{id}/matched_transactions` | Matched txns |
| GET/PUT | `/api/external/v2/supplier_invoices/{id}/categories` | Categories |
| **Customers** | | |
| GET | `/api/external/v2/customers` | List |
| GET | `/api/external/v2/customers/{id}` | Retrieve |
| GET/PUT | `/api/external/v2/customers/{id}/categories` | Categories |
| GET | `/api/external/v2/customers/{id}/contacts` | Contacts |
| POST | `/api/external/v2/company_customers` | Create company |
| GET/PUT | `/api/external/v2/company_customers/{id}` | Get/update company |
| POST | `/api/external/v2/individual_customers` | Create individual |
| GET/PUT | `/api/external/v2/individual_customers/{id}` | Get/update individual |
| **Suppliers** | | |
| GET | `/api/external/v2/suppliers` | List |
| POST | `/api/external/v2/suppliers` | Create |
| GET | `/api/external/v2/suppliers/{id}` | Retrieve |
| PUT | `/api/external/v2/suppliers/{id}` | Update |
| GET/PUT | `/api/external/v2/suppliers/{id}/categories` | Categories |
| **Products** | | |
| GET | `/api/external/v2/products` | List |
| POST | `/api/external/v2/products` | Create |
| GET | `/api/external/v2/products/{id}` | Retrieve |
| PUT | `/api/external/v2/products/{id}` | Update |
| **Transactions** | | |
| GET | `/api/external/v2/transactions` | List |
| POST | `/api/external/v2/transactions` | Create |
| GET | `/api/external/v2/transactions/{id}` | Retrieve |
| PUT | `/api/external/v2/transactions/{id}` | Update |
| GET/PUT | `/api/external/v2/transactions/{id}/categories` | Categories |
| GET | `/api/external/v2/transactions/{id}/matched_invoices` | Matched invoices |
| **Bank Accounts** | | |
| GET | `/api/external/v2/bank_accounts` | List |
| POST | `/api/external/v2/bank_accounts` | Create |
| GET | `/api/external/v2/bank_accounts/{id}` | Retrieve |
| **Accounting** | | |
| GET/POST | `/api/external/v2/ledger_entries` | List/Create |
| GET/PUT | `/api/external/v2/ledger_entries/{id}` | Retrieve/Update |
| GET | `/api/external/v2/ledger_entry_lines` | List lines |
| GET | `/api/external/v2/ledger_entry_lines/{id}` | Retrieve line |
| GET/POST | `/api/external/v2/ledger_accounts` | List/Create |
| GET/PUT | `/api/external/v2/ledger_accounts/{id}` | Retrieve/Update |
| GET/POST | `/api/external/v2/journals` | List/Create |
| GET | `/api/external/v2/journals/{id}` | Retrieve |
| GET | `/api/external/v2/trial_balance` | Trial balance |
| GET | `/api/external/v2/fiscal_years` | Fiscal years |
| **Quotes** | | |
| GET/POST | `/api/external/v2/quotes` | List/Create |
| GET/PUT | `/api/external/v2/quotes/{id}` | Retrieve/Update |
| **Other** | | |
| GET/POST | `/api/external/v2/categories` | List/Create |
| GET/PUT | `/api/external/v2/categories/{id}` | Retrieve/Update |
| GET | `/api/external/v2/category_groups` | List groups |
| GET/POST | `/api/external/v2/billing_subscriptions` | List/Create |
| GET | `/api/external/v2/changelogs/{resource}` | Change tracking |
| GET/POST/PUT/DELETE | `/api/external/v2/webhook_subscription` | Webhooks |
