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
<html>
<head>
    <title>Nova Ledger - Email Test</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        h2 { margin: 20px 0 10px; }
        .actions { display: flex; gap: 10px; margin: 15px 0; }
        button { padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600; }
        .btn-sync { background: #4285f4; color: #fff; }
        .btn-classify { background: #34a853; color: #fff; }
        .btn-sync:disabled, .btn-classify:disabled { opacity: 0.5; cursor: wait; }
        #status { padding: 12px; margin: 10px 0; border-radius: 6px; background: #e8f0fe; display: none; }
        table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin: 10px 0; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 13px; }
        th { background: #f8f9fa; font-weight: 600; }
        .tabs { display: flex; gap: 0; margin: 20px 0 0; }
        .tab { padding: 10px 20px; cursor: pointer; background: #e0e0e0; border: none; font-size: 14px; }
        .tab.active { background: #fff; font-weight: 600; }
        .tab:first-child { border-radius: 8px 0 0 0; }
        .tab:last-child { border-radius: 0 8px 0 0; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .stats { display: flex; gap: 15px; margin: 10px 0; }
        .stat { background: #fff; padding: 12px 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .stat-num { font-size: 24px; font-weight: 700; }
        .stat-label { font-size: 12px; color: #666; }
        pre { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 12px; max-height: 200px; margin: 10px 0; }
    </style>
</head>
<body>
    <h1>Nova Ledger - Email Pipeline Test</h1>

    <div class="actions">
        <button class="btn-sync" onclick="syncEmails()">Sync Emails</button>
        <button class="btn-classify" onclick="classifyEmails()">Classify with AI</button>
    </div>
    <div id="status"></div>

    <div class="stats" id="stats"></div>

    <div class="tabs">
        <button class="tab active" onclick="showTab('emails')">Emails</button>
        <button class="tab" onclick="showTab('transactions')">Transactions</button>
        <button class="tab" onclick="showTab('log')">Agent Log</button>
    </div>

    <div id="emails" class="tab-content active">
        <table><thead><tr>
            <th>Date</th><th>From</th><th>Subject</th><th>Provider</th><th>Status</th>
        </tr></thead><tbody id="email-rows"></tbody></table>
    </div>

    <div id="transactions" class="tab-content">
        <table><thead><tr>
            <th>Date</th><th>Vendor</th><th>Type</th><th>Amount</th><th>Currency</th><th>Status</th><th>Confidence</th>
        </tr></thead><tbody id="tx-rows"></tbody></table>
    </div>

    <div id="log" class="tab-content">
        <pre id="agent-log">No classification run yet.</pre>
    </div>

    <script>
        function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

        function getCSRF() {
            return document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('csrftoken='))?.split('=')[1] || '';
        }

        function showStatus(msg, loading) {
            const el = document.getElementById('status');
            el.style.display = 'block';
            el.textContent = loading ? msg + ' ...' : msg;
        }

        function showTab(name) {
            document.querySelectorAll('.tab').forEach((t, i) => {
                t.classList.toggle('active', ['emails','transactions','log'][i] === name);
            });
            document.querySelectorAll('.tab-content').forEach(c => {
                c.classList.toggle('active', c.id === name);
            });
        }

        async function syncEmails() {
            const btn = document.querySelector('.btn-sync');
            btn.disabled = true;
            showStatus('Syncing emails from providers', true);
            try {
                const resp = await fetch('/api/emails/sync/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json'},
                });
                const data = await resp.json();
                showStatus('Synced! Google: ' + data.google + ', Microsoft: ' + data.microsoft + ', Total new: ' + data.total_new);
                loadEmails();
                loadStats();
            } catch(e) {
                showStatus('Error: ' + e.message);
            }
            btn.disabled = false;
        }

        async function classifyEmails() {
            const btn = document.querySelector('.btn-classify');
            btn.disabled = true;
            showStatus('AI is classifying emails (this may take a minute)', true);
            try {
                const resp = await fetch('/api/emails/classify/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json'},
                });
                const data = await resp.json();
                showStatus('Done! Created: ' + (data.transactions_created||0) + ', Updated: ' + (data.transactions_updated||0) + ', Processed: ' + (data.emails_processed||0) + ', Ignored: ' + (data.emails_ignored||0));
                document.getElementById('agent-log').textContent = JSON.stringify(data, null, 2);
                loadEmails();
                loadTransactions();
                loadStats();
            } catch(e) {
                showStatus('Error: ' + e.message);
            }
            btn.disabled = false;
        }

        function buildEmailRow(e) {
            const tr = document.createElement('tr');
            const cells = [
                new Date(e.date).toLocaleDateString(),
                e.from_name || e.from_address,
                e.subject.substring(0, 60),
                e.provider,
                e.status,
            ];
            cells.forEach(text => { const td = document.createElement('td'); td.textContent = text; tr.appendChild(td); });
            return tr;
        }

        function buildTxRow(t) {
            const tr = document.createElement('tr');
            const cells = [
                t.transaction_date || '-',
                t.vendor_name,
                t.type,
                t.amount || '-',
                t.currency,
                t.status,
                (t.confidence * 100).toFixed(0) + '%',
            ];
            cells.forEach(text => { const td = document.createElement('td'); td.textContent = text; tr.appendChild(td); });
            return tr;
        }

        async function loadEmails() {
            const resp = await fetch('/api/emails/');
            const data = await resp.json();
            const tbody = document.getElementById('email-rows');
            tbody.replaceChildren();
            const list = data.results || data;
            if (!list.length) {
                const tr = document.createElement('tr');
                const td = document.createElement('td'); td.colSpan = 5; td.textContent = 'No emails yet. Click Sync.';
                tr.appendChild(td); tbody.appendChild(tr);
            } else {
                list.forEach(e => tbody.appendChild(buildEmailRow(e)));
            }
        }

        async function loadTransactions() {
            const resp = await fetch('/api/emails/transactions/');
            const data = await resp.json();
            const tbody = document.getElementById('tx-rows');
            tbody.replaceChildren();
            const list = data.results || data;
            if (!list.length) {
                const tr = document.createElement('tr');
                const td = document.createElement('td'); td.colSpan = 7; td.textContent = 'No transactions yet. Classify first.';
                tr.appendChild(td); tbody.appendChild(tr);
            } else {
                list.forEach(t => tbody.appendChild(buildTxRow(t)));
            }
        }

        function buildStatEl(num, label) {
            const div = document.createElement('div'); div.className = 'stat';
            const n = document.createElement('div'); n.className = 'stat-num'; n.textContent = num;
            const l = document.createElement('div'); l.className = 'stat-label'; l.textContent = label;
            div.appendChild(n); div.appendChild(l);
            return div;
        }

        async function loadStats() {
            try {
                const [emailResp, txResp] = await Promise.all([fetch('/api/emails/'), fetch('/api/emails/transactions/')]);
                const emails = await emailResp.json();
                const txs = await txResp.json();
                const emailList = emails.results || emails;
                const txList = txs.results || txs;
                const container = document.getElementById('stats');
                container.replaceChildren();
                container.appendChild(buildStatEl(emailList.length, 'Emails'));
                container.appendChild(buildStatEl(emailList.filter(e => e.status==='new').length, 'New'));
                container.appendChild(buildStatEl(emailList.filter(e => e.status==='processed').length, 'Processed'));
                container.appendChild(buildStatEl(txList.length, 'Transactions'));
                container.appendChild(buildStatEl(txList.filter(t => t.status==='complete').length, 'Complete'));
                container.appendChild(buildStatEl(txList.filter(t => t.status==='partial').length, 'Partial'));
            } catch(e) {}
        }

        loadEmails();
        loadTransactions();
        loadStats();
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
        from .services.agent import classify_emails
        result = classify_emails(request.user)
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
