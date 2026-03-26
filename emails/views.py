import logging

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Email, Transaction
from .serializers import EmailSerializer, TransactionSerializer
from .services import gmail_fetcher, microsoft_fetcher

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def test_page(request):
    """Simple HTML test page for email sync & classification.
    Note: This is a dev-only test page, not user-facing.
    """
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nova Ledger - Email Test</title>
    <style>
        :root {
            --bg: #f3f4f6;
            --surface: #ffffff;
            --border: #e5e7eb;
            --text: #111827;
            --text-secondary: #6b7280;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --success: #10b981;
            --success-hover: #059669;
            --warning: #f59e0b;
            --danger: #ef4444;
            --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
            --shadow-md: 0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06);
            --radius: 8px;
            --badge-invoice: #3b82f6;
            --badge-receipt: #10b981;
            --badge-order: #8b5cf6;
            --badge-payment: #14b8a6;
            --badge-shipping: #f97316;
            --badge-refund: #ef4444;
            --badge-cancellation: #6b7280;
            --badge-subscription: #6366f1;
            --badge-other: #9ca3af;
            --status-new: #3b82f6;
            --status-processed: #10b981;
            --status-ignored: #9ca3af;
            --status-triage_passed: #f59e0b;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px; margin: 0 auto; padding: 16px;
            background: var(--bg); color: var(--text);
            -webkit-text-size-adjust: 100%;
        }
        h1 { font-size: 20px; font-weight: 700; margin-bottom: 16px; }

        /* Top bar */
        .top-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
        button {
            padding: 9px 18px; border: none; border-radius: var(--radius);
            cursor: pointer; font-size: 13px; font-weight: 600;
            transition: background 0.15s, opacity 0.15s;
        }
        .btn-sync { background: var(--primary); color: #fff; }
        .btn-sync:hover { background: var(--primary-hover); }
        .btn-classify { background: var(--success); color: #fff; }
        .btn-classify:hover { background: var(--success-hover); }
        .btn-bank { background: #7c3aed; color: #fff; }
        .btn-bank:hover { background: #6d28d9; }
        .btn-bank-sync { background: #8b5cf6; color: #fff; }
        .btn-bank-sync:hover { background: #7c3aed; }
        button:disabled { opacity: 0.5; cursor: wait; }
        #status {
            flex: 1; min-width: 200px; padding: 10px 14px; border-radius: var(--radius);
            background: #eff6ff; color: #1e40af; font-size: 13px;
            display: none; border: 1px solid #bfdbfe;
        }

        /* Stats */
        .stats { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
        .stat {
            flex: 1; min-width: 90px; background: var(--surface); padding: 12px 14px;
            border-radius: var(--radius); box-shadow: var(--shadow); text-align: center;
        }
        .stat-num { font-size: 22px; font-weight: 700; line-height: 1.2; }
        .stat-label { font-size: 11px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }

        /* Tabs */
        .tabs { display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 0; }
        .tab {
            padding: 10px 20px; cursor: pointer; background: none; border: none;
            font-size: 13px; font-weight: 500; color: var(--text-secondary);
            border-bottom: 2px solid transparent; margin-bottom: -2px;
            transition: color 0.15s, border-color 0.15s;
        }
        .tab:hover { color: var(--text); }
        .tab.active { color: var(--primary); border-bottom-color: var(--primary); font-weight: 600; }
        .tab-content { display: none; background: var(--surface); border-radius: 0 0 var(--radius) var(--radius); box-shadow: var(--shadow); }
        .tab-content.active { display: block; }

        /* Badges */
        .badge {
            display: inline-block; padding: 2px 8px; border-radius: 10px;
            font-size: 11px; font-weight: 600; color: #fff; text-transform: capitalize;
        }
        .badge-invoice { background: var(--badge-invoice); }
        .badge-receipt { background: var(--badge-receipt); }
        .badge-order { background: var(--badge-order); }
        .badge-payment { background: var(--badge-payment); }
        .badge-shipping { background: var(--badge-shipping); }
        .badge-refund { background: var(--badge-refund); }
        .badge-cancellation { background: var(--badge-cancellation); }
        .badge-subscription { background: var(--badge-subscription); }
        .badge-other { background: var(--badge-other); }
        .badge-complete { background: var(--success); }
        .badge-partial { background: var(--warning); color: #000; }

        /* Transaction cards */
        .tx-list { padding: 12px; }
        .tx-empty { padding: 40px 20px; text-align: center; color: var(--text-secondary); font-size: 14px; }
        .tx-card {
            border: 1px solid var(--border); border-radius: var(--radius);
            margin-bottom: 8px; overflow: hidden; transition: box-shadow 0.15s;
        }
        .tx-card:hover { box-shadow: var(--shadow-md); }
        .tx-header {
            display: flex; align-items: center; gap: 10px; padding: 12px 14px;
            cursor: pointer; flex-wrap: wrap; user-select: none;
            background: var(--surface);
        }
        .tx-header:active { background: #f9fafb; }
        .tx-date { font-size: 12px; color: var(--text-secondary); min-width: 80px; }
        .tx-vendor { font-weight: 600; font-size: 14px; flex: 1; min-width: 100px; }
        .tx-amount { font-weight: 700; font-size: 14px; white-space: nowrap; }
        .tx-chevron {
            width: 20px; height: 20px; transition: transform 0.2s;
            color: var(--text-secondary); flex-shrink: 0;
        }
        .tx-card.open .tx-chevron { transform: rotate(180deg); }
        .tx-details { display: none; padding: 0 14px 14px; border-top: 1px solid var(--border); }
        .tx-card.open .tx-details { display: block; }
        .tx-grid {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 10px; margin-top: 12px;
        }
        .tx-field label { display: block; font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
        .tx-field span { font-size: 13px; font-weight: 500; }
        .tx-desc { margin-top: 10px; }
        .tx-desc label { display: block; font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
        .tx-desc p { font-size: 13px; line-height: 1.5; color: var(--text); }

        /* Items mini table */
        .items-section { margin-top: 10px; }
        .items-section label { display: block; font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .items-table { width: 100%; border-collapse: collapse; font-size: 12px; }
        .items-table th { text-align: left; padding: 4px 8px; background: #f9fafb; font-weight: 600; border-bottom: 1px solid var(--border); }
        .items-table td { padding: 4px 8px; border-bottom: 1px solid var(--border); }

        /* Confidence bar */
        .confidence-section { margin-top: 10px; }
        .confidence-section label { display: block; font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .confidence-bar-bg { background: #e5e7eb; border-radius: 4px; height: 8px; overflow: hidden; max-width: 300px; }
        .confidence-bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
        .confidence-val { font-size: 12px; font-weight: 600; margin-top: 2px; }

        /* Source email link */
        .source-email { margin-top: 10px; }
        .source-email label { display: block; font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
        .source-email a {
            font-size: 13px; color: var(--primary); text-decoration: none; cursor: pointer;
        }
        .source-email a:hover { text-decoration: underline; }

        /* Raw data collapsible */
        .raw-toggle {
            margin-top: 10px; background: none; border: 1px solid var(--border);
            padding: 4px 10px; font-size: 11px; color: var(--text-secondary);
            border-radius: 4px; cursor: pointer;
        }
        .raw-toggle:hover { background: #f9fafb; }
        .raw-content { display: none; margin-top: 6px; }
        .raw-content.open { display: block; }
        .raw-content pre {
            background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 6px;
            overflow-x: auto; font-size: 11px; max-height: 200px; white-space: pre-wrap;
            word-break: break-word;
        }

        /* Emails table */
        .email-table-wrap { overflow-x: auto; }
        table.email-table { width: 100%; border-collapse: collapse; }
        table.email-table th, table.email-table td {
            padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px;
        }
        table.email-table th { font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); background: #f9fafb; }
        table.email-table tr:hover { background: #f9fafb; }
        .email-status {
            display: inline-block; padding: 2px 8px; border-radius: 10px;
            font-size: 11px; font-weight: 600; color: #fff;
        }
        .email-status-new { background: var(--status-new); }
        .email-status-processed { background: var(--status-processed); }
        .email-status-ignored { background: var(--status-ignored); }
        .email-status-triage_passed { background: var(--status-triage_passed); color: #000; }
        .email-highlight { animation: highlightFade 2s ease-out; }
        @keyframes highlightFade {
            0% { background: #fef3c7; }
            100% { background: transparent; }
        }

        /* Log */
        .log-wrap { padding: 14px; }
        .log-wrap pre {
            background: #1e1e1e; color: #d4d4d4; padding: 14px; border-radius: 6px;
            overflow-x: auto; font-size: 12px; max-height: 500px; white-space: pre-wrap;
            word-break: break-word;
        }

        /* Mobile tweaks */
        @media (max-width: 640px) {
            body { padding: 10px; }
            h1 { font-size: 17px; }
            .stats { gap: 6px; }
            .stat { padding: 8px 6px; min-width: 70px; }
            .stat-num { font-size: 18px; }
            .tx-header { gap: 6px; padding: 10px; }
            .tx-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
            .tab { padding: 8px 12px; font-size: 12px; }
        }
    </style>
</head>
<body>
    <h1>Nova Ledger - Email Pipeline</h1>

    <div class="top-bar">
        <button class="btn-sync" id="btn-sync">Sync Emails</button>
        <button class="btn-classify" id="btn-classify">Classify with AI</button>
        <button class="btn-bank" id="btn-bank-connect">Connect Bank</button>
        <button class="btn-bank-sync" id="btn-bank-sync">Sync Bank</button>
        <div id="status"></div>
    </div>

    <div class="stats" id="stats"></div>

    <div class="tabs">
        <button class="tab active" data-tab="transactions">Transactions</button>
        <button class="tab" data-tab="bank-transactions">Bank</button>
        <button class="tab" data-tab="emails">Emails</button>
        <button class="tab" data-tab="log">Agent Log</button>
    </div>

    <div id="transactions" class="tab-content active">
        <div class="tx-list" id="tx-list"></div>
    </div>

    <div id="bank-transactions" class="tab-content">
        <div class="email-table-wrap">
            <table class="email-table">
                <thead><tr>
                    <th>Date</th><th>Label</th><th>Amount</th><th>Type</th><th>Account</th><th>Card</th>
                </tr></thead>
                <tbody id="bank-tx-rows"></tbody>
            </table>
        </div>
    </div>

    <div id="emails" class="tab-content">
        <div class="email-table-wrap">
            <table class="email-table">
                <thead><tr>
                    <th>Date</th><th>From</th><th>Subject</th><th>Provider</th><th>Status</th>
                </tr></thead>
                <tbody id="email-rows"></tbody>
            </table>
        </div>
    </div>

    <div id="log" class="tab-content">
        <div class="log-wrap">
            <pre id="agent-log">No classification run yet.</pre>
        </div>
    </div>

    <script>
        /* --- Helpers --- */
        function getCSRF() {
            return document.cookie.split(';').map(function(c){return c.trim();}).filter(function(c){return c.startsWith('csrftoken=');})[0]?.split('=')[1] || '';
        }

        function showStatus(msg, loading) {
            var el = document.getElementById('status');
            el.style.display = 'block';
            el.textContent = loading ? msg + ' ...' : msg;
        }

        function el(tag, cls, text) {
            var node = document.createElement(tag);
            if (cls) node.className = cls;
            if (text !== undefined && text !== null) node.textContent = String(text);
            return node;
        }

        /* --- Tabs --- */
        var tabNames = ['transactions', 'bank-transactions', 'emails', 'log'];
        document.querySelectorAll('.tab').forEach(function(tabBtn) {
            tabBtn.addEventListener('click', function() {
                var name = tabBtn.getAttribute('data-tab');
                document.querySelectorAll('.tab').forEach(function(t) {
                    t.classList.toggle('active', t.getAttribute('data-tab') === name);
                });
                document.querySelectorAll('.tab-content').forEach(function(c) {
                    c.classList.toggle('active', c.id === name);
                });
            });
        });

        function showTab(name) {
            document.querySelectorAll('.tab').forEach(function(t) {
                t.classList.toggle('active', t.getAttribute('data-tab') === name);
            });
            document.querySelectorAll('.tab-content').forEach(function(c) {
                c.classList.toggle('active', c.id === name);
            });
        }

        /* --- Sync --- */
        document.getElementById('btn-sync').addEventListener('click', async function() {
            var btn = this;
            btn.disabled = true;
            showStatus('Syncing emails from providers', true);
            try {
                var resp = await fetch('/api/emails/sync/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json'},
                });
                var data = await resp.json();
                showStatus('Synced! Google: ' + data.google + ', Microsoft: ' + data.microsoft + ', Total new: ' + data.total_new);
                loadEmails();
                loadStats();
            } catch(e) {
                showStatus('Error: ' + e.message);
            }
            btn.disabled = false;
        });

        /* --- Classify --- */
        document.getElementById('btn-classify').addEventListener('click', async function() {
            var btn = this;
            btn.disabled = true;
            showStatus('AI is classifying emails (this may take a minute)', true);
            try {
                var resp = await fetch('/api/emails/classify/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json'},
                });
                var data = await resp.json();
                showStatus('Done! Created: ' + (data.transactions_created||0) + ', Updated: ' + (data.transactions_updated||0) + ', Processed: ' + (data.emails_processed||0) + ', Ignored: ' + (data.emails_ignored||0));
                document.getElementById('agent-log').textContent = JSON.stringify(data, null, 2);
                loadEmails();
                loadTransactions();
                loadStats();
            } catch(e) {
                showStatus('Error: ' + e.message);
            }
            btn.disabled = false;
        });

        /* --- Stats --- */
        function buildStatEl(num, label) {
            var div = el('div', 'stat');
            div.appendChild(el('div', 'stat-num', num));
            div.appendChild(el('div', 'stat-label', label));
            return div;
        }

        var cachedEmails = [];
        var cachedTxs = [];

        async function loadStats() {
            try {
                var container = document.getElementById('stats');
                container.replaceChildren();
                var emailCount = cachedEmails.length;
                var processed = cachedEmails.filter(function(e){return e.status==='processed';}).length;
                var ignored = cachedEmails.filter(function(e){return e.status==='ignored';}).length;
                var txCount = cachedTxs.length;
                var complete = cachedTxs.filter(function(t){return t.status==='complete';}).length;
                var partial = cachedTxs.filter(function(t){return t.status==='partial';}).length;
                container.appendChild(buildStatEl(emailCount, 'Emails'));
                container.appendChild(buildStatEl(processed, 'Processed'));
                container.appendChild(buildStatEl(ignored, 'Ignored'));
                container.appendChild(buildStatEl(txCount, 'Transactions'));
                container.appendChild(buildStatEl(complete, 'Complete'));
                container.appendChild(buildStatEl(partial, 'Partial'));
            } catch(e) {}
        }

        /* --- Emails --- */
        function buildEmailRow(e) {
            var tr = document.createElement('tr');
            tr.id = 'email-' + e.id;

            var tdDate = el('td', null, new Date(e.date).toLocaleDateString());
            var tdFrom = el('td', null, e.from_name || e.from_address);
            var tdSubj = el('td', null, e.subject ? e.subject.substring(0, 80) : '');
            var tdProv = el('td', null, e.provider);

            var tdStatus = document.createElement('td');
            var statusBadge = el('span', 'email-status email-status-' + e.status, e.status.replace('_', ' '));
            tdStatus.appendChild(statusBadge);

            tr.appendChild(tdDate);
            tr.appendChild(tdFrom);
            tr.appendChild(tdSubj);
            tr.appendChild(tdProv);
            tr.appendChild(tdStatus);
            return tr;
        }

        async function loadEmails() {
            try {
                var resp = await fetch('/api/emails/');
                var data = await resp.json();
                var list = data.results || data;
                cachedEmails = list;
                var tbody = document.getElementById('email-rows');
                tbody.replaceChildren();
                if (!list.length) {
                    var tr = document.createElement('tr');
                    var td = el('td', null, 'No emails yet. Click Sync.');
                    td.colSpan = 5;
                    td.style.textAlign = 'center';
                    td.style.padding = '40px 20px';
                    td.style.color = 'var(--text-secondary)';
                    tr.appendChild(td);
                    tbody.appendChild(tr);
                } else {
                    list.forEach(function(e) { tbody.appendChild(buildEmailRow(e)); });
                }
                loadStats();
            } catch(e) {}
        }

        /* --- Transactions --- */
        function scrollToEmail(emailId) {
            showTab('emails');
            var row = document.getElementById('email-' + emailId);
            if (row) {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                row.classList.remove('email-highlight');
                void row.offsetWidth;
                row.classList.add('email-highlight');
            }
        }

        function buildTxCard(t) {
            var card = el('div', 'tx-card');

            /* Header */
            var header = el('div', 'tx-header');
            header.addEventListener('click', function() {
                card.classList.toggle('open');
            });

            var dateStr = t.transaction_date || '-';
            header.appendChild(el('span', 'tx-date', dateStr));
            header.appendChild(el('span', 'tx-vendor', t.vendor_name));

            var typeBadge = el('span', 'badge badge-' + (t.type || 'other'), t.type || 'other');
            header.appendChild(typeBadge);

            var amountStr = (t.amount !== null && t.amount !== undefined) ? t.amount + ' ' + t.currency : '-';
            header.appendChild(el('span', 'tx-amount', amountStr));

            var statusBadge = el('span', 'badge badge-' + t.status, t.status);
            header.appendChild(statusBadge);

            /* Chevron SVG */
            var chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            chevron.setAttribute('class', 'tx-chevron');
            chevron.setAttribute('viewBox', '0 0 20 20');
            chevron.setAttribute('fill', 'currentColor');
            var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('fill-rule', 'evenodd');
            path.setAttribute('d', 'M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z');
            path.setAttribute('clip-rule', 'evenodd');
            chevron.appendChild(path);
            header.appendChild(chevron);

            card.appendChild(header);

            /* Details */
            var details = el('div', 'tx-details');

            /* Row 1: Amounts */
            var grid1 = el('div', 'tx-grid');
            var fields1 = [
                ['Total (incl. tax)', t.amount !== null ? t.amount + ' ' + t.currency : '-'],
                ['Amount (excl. tax)', t.amount_tax_excl !== null ? t.amount_tax_excl + ' ' + t.currency : '-'],
                ['Tax Amount', t.tax_amount !== null ? t.tax_amount + ' ' + t.currency : '-'],
                ['Tax Rate', t.tax_rate !== null ? t.tax_rate + '%' : '-'],
            ];
            fields1.forEach(function(f) {
                var d = el('div', 'tx-field');
                d.appendChild(el('label', null, f[0]));
                d.appendChild(el('span', null, f[1]));
                grid1.appendChild(d);
            });
            details.appendChild(grid1);

            /* Row 2: Payment & refs */
            var grid2 = el('div', 'tx-grid');
            var fields2 = [
                ['Payment Method', t.payment_method || '-'],
                ['Payment Reference', t.payment_reference || '-'],
                ['Invoice #', t.invoice_number || '-'],
                ['Order #', t.order_number || '-'],
            ];
            fields2.forEach(function(f) {
                var d = el('div', 'tx-field');
                d.appendChild(el('label', null, f[0]));
                d.appendChild(el('span', null, f[1]));
                grid2.appendChild(d);
            });
            details.appendChild(grid2);

            /* Row 3: Description */
            if (t.description) {
                var descDiv = el('div', 'tx-desc');
                descDiv.appendChild(el('label', null, 'Description'));
                descDiv.appendChild(el('p', null, t.description));
                details.appendChild(descDiv);
            }

            /* Row 4: Items */
            if (t.items && t.items.length > 0) {
                var itemSec = el('div', 'items-section');
                itemSec.appendChild(el('label', null, 'Items'));
                var tbl = el('table', 'items-table');
                var thead = document.createElement('thead');
                var headRow = document.createElement('tr');
                ['Item', 'Qty', 'Unit Price'].forEach(function(h) {
                    headRow.appendChild(el('th', null, h));
                });
                thead.appendChild(headRow);
                tbl.appendChild(thead);
                var tbody = document.createElement('tbody');
                t.items.forEach(function(item) {
                    var row = document.createElement('tr');
                    row.appendChild(el('td', null, item.name || '-'));
                    row.appendChild(el('td', null, item.quantity !== undefined ? item.quantity : '-'));
                    row.appendChild(el('td', null, item.unit_price !== undefined ? item.unit_price : '-'));
                    tbody.appendChild(row);
                });
                tbl.appendChild(tbody);
                itemSec.appendChild(tbl);
                details.appendChild(itemSec);
            }

            /* Row 5: Confidence */
            var confSec = el('div', 'confidence-section');
            confSec.appendChild(el('label', null, 'Confidence'));
            var pct = Math.round((t.confidence || 0) * 100);
            var barBg = el('div', 'confidence-bar-bg');
            var barFill = el('div', 'confidence-bar-fill');
            var confColor = pct >= 80 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)';
            barFill.style.width = pct + '%';
            barFill.style.background = confColor;
            barBg.appendChild(barFill);
            confSec.appendChild(barBg);
            confSec.appendChild(el('span', 'confidence-val', pct + '%'));
            details.appendChild(confSec);

            /* Row 6: Source email */
            if (t.email_id) {
                var srcDiv = el('div', 'source-email');
                srcDiv.appendChild(el('label', null, 'Source Email'));
                var link = document.createElement('a');
                var linkText = (t.email_from || 'unknown') + ' — ' + (t.email_subject || 'no subject');
                link.textContent = linkText;
                link.href = '#';
                link.addEventListener('click', function(ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    scrollToEmail(t.email_id);
                });
                srcDiv.appendChild(link);
                details.appendChild(srcDiv);
            }

            /* Row 7: Attachments */
            var attachDiv = el('div', 'source-email');
            attachDiv.appendChild(el('label', null, 'Attachments'));
            if (t.email_has_attachments) {
                attachDiv.appendChild(el('span', null, String.fromCodePoint(0x1F4CE) + ' PDF available'));
            } else {
                attachDiv.appendChild(el('span', null, 'No attachments'));
            }
            details.appendChild(attachDiv);

            /* Row 8: Raw data */
            if (t.raw_data && Object.keys(t.raw_data).length > 0) {
                var rawBtn = el('button', 'raw-toggle', 'Show raw data');
                var rawWrap = el('div', 'raw-content');
                var rawPre = el('pre', null, JSON.stringify(t.raw_data, null, 2));
                rawWrap.appendChild(rawPre);
                rawBtn.addEventListener('click', function(ev) {
                    ev.stopPropagation();
                    rawWrap.classList.toggle('open');
                    rawBtn.textContent = rawWrap.classList.contains('open') ? 'Hide raw data' : 'Show raw data';
                });
                details.appendChild(rawBtn);
                details.appendChild(rawWrap);
            }

            card.appendChild(details);
            return card;
        }

        async function loadTransactions() {
            try {
                var resp = await fetch('/api/emails/transactions/');
                var data = await resp.json();
                var list = data.results || data;
                cachedTxs = list;
                var container = document.getElementById('tx-list');
                container.replaceChildren();
                if (!list.length) {
                    container.appendChild(el('div', 'tx-empty', 'No transactions yet. Classify emails first.'));
                } else {
                    list.forEach(function(t) { container.appendChild(buildTxCard(t)); });
                }
                loadStats();
            } catch(e) {}
        }

        /* --- Bank Connect --- */
        document.getElementById('btn-bank-connect').addEventListener('click', async function() {
            var btn = this; btn.disabled = true;
            showStatus('Connecting to bank...', true);
            try {
                var resp = await fetch('/api/banking/connect/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json'},
                });
                var data = await resp.json();
                if (data.webview_url) {
                    showStatus('Redirecting to bank login...');
                    window.location.href = data.webview_url;
                } else {
                    showStatus('Error: ' + JSON.stringify(data));
                }
            } catch(e) { showStatus('Error: ' + e.message); }
            btn.disabled = false;
        });

        /* --- Bank Sync --- */
        document.getElementById('btn-bank-sync').addEventListener('click', async function() {
            var btn = this; btn.disabled = true;
            showStatus('Syncing bank data...', true);
            try {
                var resp = await fetch('/api/banking/sync/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json'},
                });
                var data = await resp.json();
                showStatus('Bank sync done! Accounts: ' + (data.accounts_synced||0) + ', Transactions: ' + (data.transactions_synced||0));
                loadBankTransactions();
            } catch(e) { showStatus('Error: ' + e.message); }
            btn.disabled = false;
        });

        /* --- Load Bank Transactions --- */
        async function loadBankTransactions() {
            try {
                var resp = await fetch('/api/banking/transactions/');
                var data = await resp.json();
                var rows = document.getElementById('bank-tx-rows');
                rows.innerHTML = '';
                if (!data.length) {
                    var tr = document.createElement('tr');
                    var td = document.createElement('td');
                    td.colSpan = 6;
                    td.textContent = 'No bank transactions. Click "Connect Bank" to link your account.';
                    td.style.textAlign = 'center';
                    td.style.padding = '20px';
                    td.style.color = '#9ca3af';
                    tr.appendChild(td);
                    rows.appendChild(tr);
                    return;
                }
                data.forEach(function(t) {
                    var tr = document.createElement('tr');
                    var vals = [
                        t.date || '?',
                        t.simplified_wording || t.original_wording || '-',
                        (t.value != null ? t.value + ' ' + (t.currency || '') : '-'),
                        t.transaction_type || '-',
                        t.account_name || '-',
                        t.card || '-',
                    ];
                    vals.forEach(function(v) {
                        var td = document.createElement('td');
                        td.textContent = v;
                        if (v && v.toString().startsWith('-') && vals.indexOf(v) === 2) td.style.color = '#ef4444';
                        if (v && !v.toString().startsWith('-') && vals.indexOf(v) === 2 && v !== '-') td.style.color = '#10b981';
                        tr.appendChild(td);
                    });
                    rows.appendChild(tr);
                });
            } catch(e) { console.error('Bank tx load error:', e); }
        }

        /* --- Init --- */
        loadEmails();
        loadTransactions();
        loadBankTransactions();
    </script>
</body>
</html>"""
    return HttpResponse(html)


@method_decorator(csrf_exempt, name='dispatch')
class EmailSyncView(APIView):
    """POST /api/emails/sync/ — fetch emails from all linked providers."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        since_date = request.data.get('since_date')  # Optional YYYY-MM-DD, defaults to 30 days
        google_count = gmail_fetcher.fetch_emails(user, since_date=since_date)
        microsoft_count = microsoft_fetcher.fetch_emails(user, since_date=since_date)
        return Response({
            'google': google_count,
            'microsoft': microsoft_count,
            'total_new': google_count + microsoft_count,
        })


@method_decorator(csrf_exempt, name='dispatch')
class EmailClassifyView(APIView):
    """POST /api/emails/classify/ — run Claude agent on unprocessed emails."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services.pipeline import run_pipeline
        result = run_pipeline(request.user)
        return Response(result)


class EmailListView(ListAPIView):
    """GET /api/emails/ — list fetched emails with filters."""
    serializer_class = EmailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Email.objects.filter(user=self.request.user)
        # Filters
        provider = self.request.query_params.get('provider')
        email_status = self.request.query_params.get('status')
        if provider:
            qs = qs.filter(provider=provider)
        if email_status:
            qs = qs.filter(status=email_status)
        return qs


@method_decorator(csrf_exempt, name='dispatch')
class TransactionMergeView(APIView):
    """POST /api/emails/merge/ — run post-processing merge on transactions."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services.merge import merge_related_transactions
        result = merge_related_transactions(request.user)
        return Response(result)


class TransactionListView(ListAPIView):
    """GET /api/emails/transactions/ — list extracted transactions."""
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Transaction.objects.filter(user=self.request.user)
        tx_type = self.request.query_params.get('type')
        tx_status = self.request.query_params.get('status')
        vendor = self.request.query_params.get('vendor')
        if tx_type:
            qs = qs.filter(type=tx_type)
        if tx_status:
            qs = qs.filter(status=tx_status)
        if vendor:
            qs = qs.filter(vendor_name__icontains=vendor)
        return qs
