import re  # <--- ADD THIS LINE at the very top
import random
from django.core.mail import send_mail
from django.conf import settings
import csv
import decimal
import calendar
from .forms import ClientRegistrationForm
from datetime import datetime, timedelta
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib.auth.decorators import login_required

# Import models
from .models import (
    Account, JournalVoucher, JournalVoucherLine, 
    PurchaseOrder, PurchaseOrderLine, Vendor, 
    Expense, ExpenseLine, Customer, Invoice, InvoiceLine,
    BankAccount, BankStatementLine,
    Product, Warehouse, Category, StockItem, FixedAsset,
    Budget, BudgetItem, Project, CompanySettings, Company
)

# --- HELPER: GET USER'S COMPANY ---
def get_company(request):
    # 1. If user is not logged in, return None
    if not request.user.is_authenticated:
        return None
    
    # 2. Try to get their company
    try:
        return request.user.company_profile
    except Company.DoesNotExist:
        # 3. EMERGENCY FIX: If logged-in user has no company (like the Superuser),
        # create one for them right now so the system works.
        return Company.objects.create(name=f"{request.user.username}'s Company", owner=request.user)

# --- AUTHENTICATION ---
# In accounting/views.py

def register(request):
    if request.method == 'POST':
        form = ClientRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Create the Company
            phone = form.cleaned_data.get('phone')
            Company.objects.create(
                name=f"{user.username}'s Company", 
                owner=user,
                email=user.email,
                phone=phone
            )
            
            login(request, user)
            messages.success(request, f"Welcome, {user.first_name}!")
            return redirect('dashboard')
    else:
        form = ClientRegistrationForm()
    
    return render(request, 'registration/register.html', {'form': form})

def verify_email(request):
    # Get user from session
    user_id = request.session.get('verification_user_id')
    if not user_id:
        return redirect('login') # Security check
        
    if request.method == 'POST':
        entered_code = request.POST.get('code')
        
        # Find the user's company
        from django.contrib.auth.models import User
        user = User.objects.get(pk=user_id)
        company = user.company_profile
        
        if entered_code == company.verification_code:
            # Success!
            company.is_verified = True
            company.save()
            
            # Log them in
            login(request, user)
            del request.session['verification_user_id'] # Cleanup
            messages.success(request, "Email verified successfully!")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid code. Please try again.")

    return render(request, 'registration/verify_email.html')

@login_required
def profile_view(request):
    user = request.user
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name')
        user.last_name = request.POST.get('last_name')
        user.email = request.POST.get('email')
        user.save()
        messages.success(request, "Profile updated.")
        return redirect('profile_view')
    return render(request, 'accounting/profile.html', {'user': user})

@login_required
def settings_view(request):
    # Only load the company belonging to this user
    company = get_company(request)
    
    if request.method == 'POST':
        company.name = request.POST.get('company_name')
        company.address = request.POST.get('address')
        company.email = request.POST.get('email')
        company.phone = request.POST.get('phone')
        company.website = request.POST.get('website')
        if 'logo' in request.FILES:
            company.logo = request.FILES['logo']
        company.save()
        messages.success(request, "Settings updated.")
        return redirect('settings_view')
    return render(request, 'accounting/settings.html', {'company': company})

# --- DASHBOARD ---
@login_required
def dashboard(request):
    company = get_company(request)
    
    # Filter ALL queries by company
    total_assets = Account.objects.filter(company=company, account_type='Asset').aggregate(Sum('current_balance'))['current_balance__sum'] or decimal.Decimal(0)
    total_ar = Invoice.objects.filter(company=company).exclude(status__in=['Paid', 'Void', 'Refunded']).aggregate(Sum('total_amount'))['total_amount__sum'] or decimal.Decimal(0)
    total_ap = PurchaseOrder.objects.filter(company=company, status__in=['Issued', 'Received']).aggregate(Sum('total_amount'))['total_amount__sum'] or decimal.Decimal(0)
    
    total_revenue = Account.objects.filter(company=company, account_type__in=['Revenue', 'Income', 'Other Income']).aggregate(Sum('current_balance'))['current_balance__sum'] or decimal.Decimal(0)
    total_expenses = Account.objects.filter(company=company, account_type__in=['Expense', 'Expenses', 'Cost of Goods Sold']).aggregate(Sum('current_balance'))['current_balance__sum'] or decimal.Decimal(0)
    net_income = total_revenue - total_expenses

    recent_invoices = Invoice.objects.filter(company=company).order_by('-created_at')[:5]
    recent_expenses = Expense.objects.filter(company=company).order_by('-created_at')[:5]

    # Chart Data
    today = timezone.now().date()
    chart_labels = []
    income_data = []
    expense_data = []

    for i in range(5, -1, -1):
        d = today - timedelta(days=i*30)
        chart_labels.append(f"{calendar.month_name[d.month][:3]}")
        
        monthly_income = Invoice.objects.filter(company=company, invoice_date__year=d.year, invoice_date__month=d.month).exclude(status='Void').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        monthly_expense = Expense.objects.filter(company=company, expense_date__year=d.year, expense_date__month=d.month).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        income_data.append(float(monthly_income))
        expense_data.append(float(monthly_expense))

    if len(income_data) >= 3:
        avg_income = sum(income_data[-3:]) / 3
        avg_expense = sum(expense_data[-3:]) / 3
    else:
        avg_income = sum(income_data) / (len(income_data) or 1)
        avg_expense = sum(expense_data) / (len(expense_data) or 1)

    chart_labels.append("FORECAST")
    income_data.append(round(avg_income, 2))
    expense_data.append(round(avg_expense, 2))

    expense_breakdown = ExpenseLine.objects.filter(expense__company=company).values('expense_account__account_name').annotate(total=Sum('amount')).order_by('-total')[:5]
    category_labels = [i['expense_account__account_name'] for i in expense_breakdown]
    category_data = [float(i['total']) for i in expense_breakdown]

    ai_insights = []
    if total_ar > total_assets:
        ai_insights.append({'type': 'warning', 'msg': f"Cash Flow Warning: Unpaid invoices (${total_ar:,.2f}) exceed cash assets."})

    context = {
        'total_assets': total_assets, 'total_ar': total_ar, 'total_ap': total_ap, 'net_income': net_income,
        'recent_invoices': recent_invoices, 'recent_expenses': recent_expenses,
        'chart_labels': chart_labels, 'income_data': income_data, 'expense_data': expense_data,
        'category_labels': category_labels, 'category_data': category_data, 'ai_insights': ai_insights,
    }
    return render(request, 'accounting/dashboard.html', context)

# --- ACCOUNTS ---
@login_required
def account_list(request):
    company = get_company(request)
    query = request.GET.get('search', '')
    if query:
        accounts = Account.objects.filter(company=company).filter(Q(account_number__icontains=query) | Q(account_name__icontains=query))
    else:
        accounts = Account.objects.filter(company=company)
    return render(request, 'accounting/account_list.html', {'accounts': accounts, 'search_query': query})

@login_required
def add_account(request):
    company = get_company(request)
    if request.method == 'POST':
        try:
            # NEW QBO LOGIC
            debit_types = [
                'Accounts Receivable', 'Other Current Assets', 'Bank', 
                'Fixed Assets', 'Other Assets', 
                'Cost of Goods Sold', 'Expenses', 'Other Expense'
            ]
            # If it's in the list above, it's DEBIT. Otherwise (Liabilities, Equity, Income), it's CREDIT.
            bal = 'Debit' if request.POST['account_type'] in debit_types else 'Credit'
            
            Account.objects.create(
                company=company,
                account_number=request.POST['account_number'], 
                account_name=request.POST['account_name'],
                account_type=request.POST['account_type'], 
                normal_balance=bal
            )
            return redirect('account_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render(request, 'accounting/add_account.html', {'account_types': Account.ACCOUNT_TYPES})

@login_required
def edit_account(request, account_id):
    company = get_company(request)
    # Security: Ensure user owns this account
    account = Account.objects.get(pk=account_id, company=company)
    
    if request.method == 'POST':
        account.account_number = request.POST['account_number']
        account.account_name = request.POST['account_name']
        account.account_type = request.POST['account_type']
        dtype = ['Bank', 'Accounts Receivable', 'Other Current Assets', 'Fixed Assets', 'Other Assets', 'Cost of Goods Sold', 'Expenses', 'Other Expense']
        account.normal_balance = 'Debit' if account.account_type in dtype else 'Credit'
        account.save()
        return redirect('account_list')
    return render(request, 'accounting/edit_account.html', {'account': account, 'account_types': Account.ACCOUNT_TYPES})

@login_required
def toggle_account_activity(request, account_id):
    company = get_company(request)
    acc = Account.objects.get(pk=account_id, company=company)
    acc.is_active = not acc.is_active
    acc.save()
    return redirect('account_list')

@login_required
def recalculate_balances(request):
    company = get_company(request)
    dtype = ['Bank', 'Accounts Receivable', 'Other Current Assets', 'Fixed Assets', 'Other Assets', 'Cost of Goods Sold', 'Expenses', 'Other Expense']
    
    for acc in Account.objects.filter(company=company):
        acc.normal_balance = 'Debit' if acc.account_type in dtype else 'Credit'
        lines = JournalVoucherLine.objects.filter(account=acc, journal_voucher__status='Posted')
        d = lines.aggregate(Sum('debit_amount'))['debit_amount__sum'] or decimal.Decimal(0)
        c = lines.aggregate(Sum('credit_amount'))['credit_amount__sum'] or decimal.Decimal(0)
        acc.current_balance = (d - c) if acc.normal_balance == 'Debit' else (c - d)
        acc.save()
    messages.success(request, "Balances recalculated.")
    return redirect('account_list')

@login_required
def account_ledger(request, account_id):
    company = get_company(request)
    account = Account.objects.get(pk=account_id, company=company)
    lines = JournalVoucherLine.objects.filter(account=account, journal_voucher__status='Posted').order_by('journal_voucher__jv_date')
    
    bal = decimal.Decimal(0)
    for l in lines:
        if account.normal_balance == 'Debit': bal += (l.debit_amount - l.credit_amount)
        else: bal += (l.credit_amount - l.debit_amount)
    return render(request, 'accounting/account_ledger.html', {'account': account, 'transaction_lines': lines, 'calculated_balance': bal})

# --- VENDORS ---
@login_required
def vendor_list(request):
    company = get_company(request)
    vendors = Vendor.objects.filter(company=company)
    return render(request, 'accounting/vendor_list.html', {'vendors': vendors})

@login_required
@login_required
def add_vendor(request):
    company = get_company(request)
    if request.method == 'POST':
        # --- PHONE FORMATTING LOGIC ---
        raw_phone = request.POST.get('phone', '')
        digits = re.sub(r'\D', '', raw_phone)
        formatted_phone = raw_phone
        if len(digits) == 10:
            formatted_phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        # ------------------------------

        Vendor.objects.create(
            company=company,
            name=request.POST['name'],
            email=request.POST.get('email', ''),
            phone=formatted_phone,
            address=request.POST.get('address', ''),
        )
        return redirect('vendor_list')
    return render(request, 'accounting/add_vendor.html')

@login_required
def edit_vendor(request, vendor_id):
    company = get_company(request)
    vendor = Vendor.objects.get(pk=vendor_id, company=company)
    if request.method == 'POST':
        vendor.name = request.POST['name']
        vendor.save()
        return redirect('vendor_list')
    return render(request, 'accounting/edit_vendor.html', {'vendor': vendor})

@login_required
def toggle_vendor_activity(request, vendor_id):
    company = get_company(request)
    v = Vendor.objects.get(pk=vendor_id, company=company)
    v.is_active = not v.is_active
    v.save()
    return redirect('vendor_list')

@login_required
def vendor_detail(request, vendor_id):
    company = get_company(request)
    v = Vendor.objects.get(pk=vendor_id, company=company)
    pos = PurchaseOrder.objects.filter(vendor=v)
    exps = Expense.objects.filter(vendor=v)
    return render(request, 'accounting/vendor_detail.html', {'vendor': v, 'purchase_orders': pos, 'expenses': exps})

# --- CUSTOMERS ---
@login_required
def customer_list(request):
    company = get_company(request)
    c = Customer.objects.filter(company=company)
    return render(request, 'accounting/customer_list.html', {'customers': c})

@login_required
def add_customer(request):
    company = get_company(request)
    if request.method == 'POST':
        # --- PHONE FORMATTING LOGIC ---
        raw_phone = request.POST.get('phone', '')
        digits = re.sub(r'\D', '', raw_phone)
        formatted_phone = raw_phone
        if len(digits) == 10:
            formatted_phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        # ------------------------------

        Customer.objects.create(
            company=company,
            name=request.POST['name'],
            email=request.POST.get('email', ''),
            phone=formatted_phone,  # <--- Save the formatted version
            address=request.POST.get('address', '')
        )
        return redirect('customer_list')
    return render(request, 'accounting/add_customer.html')

@login_required
def edit_customer(request, customer_id):
    company = get_company(request)
    cust = Customer.objects.get(pk=customer_id, company=company)
    if request.method == 'POST':
        cust.name = request.POST['name']
        cust.save()
        return redirect('customer_list')
    return render(request, 'accounting/edit_customer.html', {'customer': cust})

@login_required
def toggle_customer_activity(request, customer_id):
    company = get_company(request)
    c = Customer.objects.get(pk=customer_id, company=company)
    c.is_active = not c.is_active
    c.save()
    return redirect('customer_list')

@login_required
def customer_detail(request, customer_id):
    company = get_company(request)
    cust = Customer.objects.get(pk=customer_id, company=company)
    invoices = Invoice.objects.filter(customer=cust).order_by('-invoice_date')
    return render(request, 'accounting/customer_detail.html', {'customer': cust, 'invoices': invoices})

# --- INVOICES ---
@login_required
@transaction.atomic
def create_invoice(request):
    company = get_company(request)
    customers = Customer.objects.filter(company=company, is_active=True)
    products = Product.objects.filter(company=company, is_active=True)
    projects = Project.objects.filter(company=company, status='In Progress')
    revenue_accounts = Account.objects.filter(company=company, account_type__in=['Revenue', 'Income', 'Other Income'], is_active=True)

    if request.method == 'POST':
        customer = Customer.objects.get(pk=request.POST['customer'], company=company)
        project_id = request.POST.get('project')
        project = Project.objects.get(pk=project_id, company=company) if project_id else None

        invoice = Invoice.objects.create(
            company=company, # Tag Header
            customer=customer,
            project=project,
            invoice_date=request.POST['invoice_date'],
            due_date=request.POST['due_date'],
            invoice_number=f"INV-{timezone.now().strftime('%Y%m%d-%H%M%S')}",
            description=request.POST.get('description', ''),
            customer_message=request.POST.get('customer_message', ''),
            internal_notes=request.POST.get('internal_notes', ''),
            payment_terms=request.POST.get('payment_terms'),
            status='Sent'
        )
        
        prods = request.POST.getlist('product')
        accts = request.POST.getlist('account')
        qtys = request.POST.getlist('quantity')
        prices = request.POST.getlist('unit_price')
        
        total = decimal.Decimal(0)
        wh, _ = Warehouse.objects.get_or_create(name="Main Warehouse", company=company)

        for i in range(len(prods)):
            if prods[i] and qtys[i]:
                p = Product.objects.get(pk=prods[i], company=company)
                q = decimal.Decimal(qtys[i])
                pr = decimal.Decimal(prices[i])
                line_tot = q * pr
                
                rev_acc = None
                if i < len(accts) and accts[i]: 
                    rev_acc = Account.objects.get(pk=accts[i], company=company)
                
                if not rev_acc: 
                    rev_acc = p.revenue_account or revenue_accounts.first()

                # --- FIX IS HERE: Add company=company ---
                InvoiceLine.objects.create(
                    company=company, # <--- Tag the Line Item!
                    invoice=invoice, 
                    product=p, 
                    revenue_account=rev_acc, 
                    description=p.name, 
                    quantity=q, 
                    unit_price=pr, 
                    line_total=line_tot
                )
                # ----------------------------------------
                
                total += line_tot

                # Deduct Inventory (Ensure StockItem has company tag too)
                stock, created = StockItem.objects.get_or_create(
                    product=p, 
                    warehouse=wh, 
                    defaults={'company': company, 'quantity': 0}
                )
                stock.quantity = decimal.Decimal(stock.quantity) - q
                stock.save()
        
        invoice.total_amount = total
        invoice.save()
        
        return redirect('invoice_detail', invoice_id=invoice.id)

    return render(request, 'accounting/create_invoice.html', {
        'customers': customers, 
        'products': products, 
        'projects': projects, 
        'revenue_accounts': revenue_accounts
    })

@login_required
def invoice_list(request):
    company = get_company(request)
    invoices = Invoice.objects.filter(company=company)
    return render(request, 'accounting/invoice_list.html', {'invoices': invoices})

@login_required
def invoice_detail(request, invoice_id):
    company = get_company(request)
    invoice = Invoice.objects.get(pk=invoice_id, company=company)
    return render(request, 'accounting/invoice_detail.html', {'invoice': invoice})

@login_required
def change_invoice_status(request, invoice_id, new_status):
    company = get_company(request)
    if request.method == 'POST':
        inv = Invoice.objects.get(pk=invoice_id, company=company)
        inv.status = new_status
        inv.save()
    return redirect('invoice_detail', invoice_id=invoice_id)

@login_required
@transaction.atomic
def receive_payment(request, invoice_id):
    company = get_company(request)
    invoice = Invoice.objects.get(pk=invoice_id, company=company)
    
    # Only show Bank accounts for deposit
    banks = Account.objects.filter(company=company, account_type='Bank', is_active=True)

    if request.method == 'POST':
        bank = Account.objects.get(pk=request.POST['deposit_account'], company=company)
        
        invoice.status = 'Paid'
        invoice.save()

        # Create Header
        jv = JournalVoucher.objects.create(
            company=company,  # <--- Tag Company
            jv_number=f"PMT-{invoice.invoice_number}", 
            jv_date=request.POST['payment_date'], 
            description=f"Pmt: {invoice.invoice_number}", 
            status='Posted', 
            posted_at=timezone.now()
        )

        # 1. Debit Bank (Increase Cash)
        JournalVoucherLine.objects.create(
            company=company,  # <--- Tag Company
            journal_voucher=jv, 
            account=bank, 
            debit_amount=invoice.total_amount, 
            credit_amount=0, 
            line_description="Received"
        )
        bank.current_balance += invoice.total_amount
        bank.save()

        # 2. Credit Revenue (Recognize Income NOW)
        for line in invoice.lines.all():
            JournalVoucherLine.objects.create(
                company=company,  # <--- Tag Company
                journal_voucher=jv, 
                account=line.revenue_account, 
                debit_amount=0, 
                credit_amount=line.line_total, 
                line_description=f"Sale: {line.description}"
            )
            line.revenue_account.current_balance += line.line_total
            line.revenue_account.save()
            
        return redirect('customer_detail', customer_id=invoice.customer.id)

    return render(request, 'accounting/receive_payment.html', {'invoice': invoice, 'deposit_accounts': banks})

@login_required
@transaction.atomic
def refund_invoice(request, invoice_id):
    company = get_company(request)
    invoice = Invoice.objects.get(pk=invoice_id, company=company)
    
    if request.method == 'POST':
        bank = Account.objects.get(pk=request.POST['deposit_account'], company=company)
        invoice.status = 'Refunded'
        invoice.save()

        jv = JournalVoucher.objects.create(
            company=company,  # <--- Tag Company
            jv_number=f"RFND-{invoice.invoice_number}", 
            jv_date=request.POST['refund_date'], 
            description=f"Refund: {invoice.invoice_number}", 
            status='Posted', 
            posted_at=timezone.now()
        )

        # Credit Bank (Money Out)
        JournalVoucherLine.objects.create(
            company=company,  # <--- Tag Company
            journal_voucher=jv, 
            account=bank, 
            debit_amount=0, 
            credit_amount=invoice.total_amount, 
            line_description="Refund Paid"
        )
        bank.current_balance -= invoice.total_amount
        bank.save()

        # Debit Revenue (Reverse Sales)
        for line in invoice.lines.all():
            JournalVoucherLine.objects.create(
                company=company,  # <--- Tag Company
                journal_voucher=jv, 
                account=line.revenue_account, 
                debit_amount=line.line_total, 
                credit_amount=0, 
                line_description="Refund Exp"
            )
            line.revenue_account.current_balance -= line.line_total
            line.revenue_account.save()
        
        return redirect('customer_detail', customer_id=invoice.customer.id)

    deposit_accounts = Account.objects.filter(company=company, account_type='Bank', is_active=True)
    return render(request, 'accounting/refund_invoice.html', {'invoice': invoice, 'deposit_accounts': deposit_accounts})

# --- EXPENSES ---
@login_required
@transaction.atomic
def create_expense(request):
    company = get_company(request)
    vendors = Vendor.objects.filter(company=company, is_active=True)
    payment_accounts = Account.objects.filter(company=company, account_type='Bank', is_active=True)
    expense_accounts = Account.objects.filter(company=company, is_active=True)
    projects = Project.objects.filter(company=company, status='In Progress')
    open_pos = PurchaseOrder.objects.filter(company=company, status__in=['Issued', 'Received'])

    if request.method == 'POST':
        exp = Expense.objects.create(
            company=company,
            vendor=Vendor.objects.get(pk=request.POST['vendor'], company=company),
            expense_date=request.POST['expense_date'],
            payment_account=Account.objects.get(pk=request.POST['payment_account'], company=company),
            reference_number=request.POST['reference_number'],
            description=request.POST.get('description', ''),
            project=Project.objects.get(pk=request.POST['project'], company=company) if request.POST.get('project') else None,
            purchase_order=PurchaseOrder.objects.get(pk=request.POST['purchase_order'], company=company) if request.POST.get('purchase_order') else None
        )
        
        accts = request.POST.getlist('account')
        amts = request.POST.getlist('amount')
        descs = request.POST.getlist('line_description')
        total = decimal.Decimal(0)

        for i in range(len(accts)):
            if accts[i] and amts[i]:
                amt = decimal.Decimal(amts[i])
                ExpenseLine.objects.create(
                    company=company, 
                    expense=exp, 
                    expense_account=Account.objects.get(pk=accts[i], company=company), 
                    description=descs[i], 
                    amount=amt
                )
                total += amt
        
        exp.total_amount = total
        exp.save()

        # GL Entry - Tagging Everything with Company
        jv = JournalVoucher.objects.create(
            company=company, # <--- Tag JV
            jv_number=f"EXP-{exp.id}", 
            jv_date=exp.expense_date, 
            description=f"Exp: {exp.vendor.name}", 
            status='Posted', 
            posted_at=timezone.now()
        )
        
        # Credit Payment Account
        JournalVoucherLine.objects.create(
            company=company, # <--- Tag Line
            journal_voucher=jv, 
            account=exp.payment_account, 
            credit_amount=total, 
            debit_amount=0, 
            line_description="Payment"
        )
        exp.payment_account.current_balance -= total
        exp.payment_account.save()
        
        # Debit Expense Accounts
        for line in exp.lines.all():
            JournalVoucherLine.objects.create(
                company=company, # <--- Tag Line
                journal_voucher=jv, 
                account=line.expense_account, 
                debit_amount=line.amount, 
                credit_amount=0, 
                line_description=line.description
            )
            if line.expense_account.normal_balance == 'Debit': 
                line.expense_account.current_balance += line.amount
            else: 
                line.expense_account.current_balance -= line.amount
            line.expense_account.save()
        
        return redirect('expense_list')

    return render(request, 'accounting/create_expense.html', {
        'vendors': vendors, 
        'payment_accounts': payment_accounts, 
        'expense_accounts': expense_accounts, 
        'projects': projects, 
        'open_pos': open_pos
    })

@login_required
def expense_list(request):
    company = get_company(request)
    exps = Expense.objects.filter(company=company)
    return render(request, 'accounting/expense_list.html', {'expenses': exps})

@login_required
def expense_detail(request, expense_id):
    company = get_company(request)
    return render(request, 'accounting/expense_detail.html', {'expense': Expense.objects.get(pk=expense_id, company=company)})

@login_required
def change_expense_status(request, expense_id, new_status):
    company = get_company(request)
    if request.method == 'POST':
        e = Expense.objects.get(pk=expense_id, company=company)
        if e.status == 'Draft': e.status = new_status; e.save()
    return redirect('expense_detail', expense_id=expense_id)

# --- POS ---
@login_required
def create_po(request):
    company = get_company(request)
    accounts = Account.objects.filter(company=company, is_active=True)
    vendors = Vendor.objects.filter(company=company)
    
    if request.method == 'POST':
        # 1. Fetch Vendor first so we can grab their details
        vendor_obj = Vendor.objects.get(pk=request.POST['vendor'], company=company)

        # 2. Create PO with Name & Address Snapshot
        po = PurchaseOrder.objects.create(
            company=company,
            po_number=f"PO-{timezone.now().strftime('%Y%m%d-%H%M%S')}", 
            po_date=request.POST['po_date'],
            vendor=vendor_obj,
            vendor_name=vendor_obj.name,       # <--- FIX: Save Name explicitly
            vendor_address=vendor_obj.address, # <--- FIX: Save Address explicitly
            description=request.POST['description']
        )
        
        # Get list data
        accts = request.POST.getlist('account')
        items = request.POST.getlist('item_description')
        qtys = request.POST.getlist('quantity')
        prices = request.POST.getlist('unit_price')
        
        grand_total = decimal.Decimal(0)

        for i in range(len(qtys)):
            if qtys[i] and prices[i] and i < len(accts) and accts[i]:
                q = decimal.Decimal(qtys[i])
                p = decimal.Decimal(prices[i])
                line_total = q * p
                desc = items[i] if i < len(items) else ""

                PurchaseOrderLine.objects.create(
                    company=company,
                    purchase_order=po, 
                    account=Account.objects.get(pk=accts[i], company=company), 
                    item_description=desc, 
                    quantity=q, 
                    unit_price=p, 
                    line_total=line_total
                )
                grand_total += line_total
        
        po.total_amount = grand_total
        po.save()
        return redirect('po_list')

    return render(request, 'accounting/create_po.html', {'accounts': accounts, 'vendors': vendors})

@login_required
def po_list(request):
    company = get_company(request)
    orders = PurchaseOrder.objects.filter(company=company)
    return render(request, 'accounting/po_list.html', {'orders': orders})

@login_required
def po_detail(request, po_id):
    company = get_company(request)
    po = PurchaseOrder.objects.get(pk=po_id, company=company)
    paid = po.expenses.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    return render(request, 'accounting/po_detail.html', {'order': po, 'total_paid': paid, 'remaining_balance': po.total_amount - paid, 'related_expenses': po.expenses.all()})

@login_required
def change_po_status(request, po_id, new_status):
    company = get_company(request)
    if request.method == 'POST':
        po = PurchaseOrder.objects.get(pk=po_id, company=company)
        po.status = new_status
        po.save()
    return redirect('po_detail', po_id=po_id)

# --- INVENTORY ---
@login_required
def product_list(request):
    company = get_company(request)
    products = Product.objects.filter(company=company)
    return render(request, 'accounting/product_list.html', {'products': products})

@login_required
def add_product(request):
    company = get_company(request)
    asset_types = ['Asset', 'Other Current Assets', 'Fixed Assets', 'Other Assets']
    asset_accounts = Account.objects.filter(company=company, account_type__in=asset_types, is_active=True)
    expense_types = ['Expense', 'Expenses', 'Cost of Goods Sold', 'Other Expense']
    expense_accounts = Account.objects.filter(company=company, account_type__in=expense_types, is_active=True)
    revenue_accounts = Account.objects.filter(company=company, account_type__in=['Revenue', 'Income', 'Other Income'], is_active=True)
    vendors = Vendor.objects.filter(company=company, is_active=True)
    categories = Category.objects.filter(company=company)

    if request.method == 'POST':
        try:
            cat_name = request.POST.get('category_name')
            category = None
            if cat_name: category, _ = Category.objects.get_or_create(name=cat_name, company=company)
            
            vendor_id = request.POST.get('preferred_vendor')
            preferred_vendor = Vendor.objects.get(pk=vendor_id, company=company) if vendor_id else None

            Product.objects.create(
                company=company,
                sku=request.POST['sku'], name=request.POST['name'], description=request.POST.get('description', ''),
                category=category, unit_of_measure=request.POST.get('unit_of_measure', 'Item'), reorder_level=request.POST.get('reorder_level', 0),
                is_active=request.POST.get('is_active') == 'on', preferred_vendor=preferred_vendor,
                unit_cost=request.POST.get('unit_cost', 0), unit_price=request.POST.get('unit_price', 0),
                inventory_asset_account=Account.objects.get(pk=request.POST['asset_account'], company=company),
                expense_account=Account.objects.get(pk=request.POST['expense_account'], company=company),
                revenue_account=Account.objects.get(pk=request.POST['revenue_account'], company=company)
            )
            return redirect('product_list')
        except Exception as e:
             return render(request, 'accounting/add_product.html', {'error': str(e), 'asset_accounts': asset_accounts, 'expense_accounts': expense_accounts, 'revenue_accounts': revenue_accounts, 'vendors': vendors, 'categories': categories})
    return render(request, 'accounting/add_product.html', {'asset_accounts': asset_accounts, 'expense_accounts': expense_accounts, 'revenue_accounts': revenue_accounts, 'vendors': vendors, 'categories': categories})

@login_required
def delete_product(request, product_id):
    company = get_company(request)
    if request.method == 'POST': Product.objects.get(pk=product_id, company=company).delete()
    return redirect('product_list')

@login_required
@transaction.atomic
def adjust_stock(request, product_id):
    company = get_company(request)
    product = Product.objects.get(pk=product_id, company=company)
    
    # 1. Ensure a Warehouse exists for THIS company
    warehouse, _ = Warehouse.objects.get_or_create(
        name="Main Warehouse", 
        company=company
    )
    
    # 2. Get or Create the Stock Item linked to THIS company
    stock_item, created = StockItem.objects.get_or_create(
        product=product, 
        warehouse=warehouse,
        company=company,   # <--- THIS WAS MISSING
        defaults={'quantity': 0}
    )

    if request.method == 'POST':
        old_qty = stock_item.quantity
        new_qty = decimal.Decimal(request.POST['quantity'])
        diff = new_qty - old_qty
        
        if diff == 0: 
            return redirect('stock_levels')
            
        value_change = diff * product.unit_cost
        stock_item.quantity = new_qty
        stock_item.save()
        
        # GL Posting
        balancing_account = Account.objects.filter(company=company, account_type='Equity').first()
        
        if balancing_account:
            jv = JournalVoucher.objects.create(
                company=company, # Tag the JV
                jv_number=f"INV-ADJ-{stock_item.id}-{timezone.now().strftime('%H%M%S')}", 
                jv_date=timezone.now().date(), 
                description=f"Inv Adj: {product.name} ({request.POST['reason']})", 
                status='Posted', 
                posted_at=timezone.now()
            )
            
            if value_change > 0:
                # Increase Inventory (Debit Asset)
                JournalVoucherLine.objects.create(
                    company=company,
                    journal_voucher=jv, 
                    account=product.inventory_asset_account, 
                    debit_amount=value_change, 
                    credit_amount=0, 
                    line_description=f"Inc ({diff})"
                )
                # Credit Equity
                JournalVoucherLine.objects.create(
                    company=company,
                    journal_voucher=jv, 
                    account=balancing_account, 
                    debit_amount=0, 
                    credit_amount=value_change, 
                    line_description="Adj"
                )
                product.inventory_asset_account.current_balance += value_change
                balancing_account.current_balance += value_change
            else:
                # Decrease Inventory (Credit Asset)
                abs_val = abs(value_change)
                JournalVoucherLine.objects.create(
                    company=company,
                    journal_voucher=jv, 
                    account=product.inventory_asset_account, 
                    debit_amount=0, 
                    credit_amount=abs_val, 
                    line_description=f"Dec ({diff})"
                )
                # Debit Equity
                JournalVoucherLine.objects.create(
                    company=company,
                    journal_voucher=jv, 
                    account=balancing_account, 
                    debit_amount=abs_val, 
                    credit_amount=0, 
                    line_description="Adj"
                )
                product.inventory_asset_account.current_balance -= abs_val
                balancing_account.current_balance -= abs_val
            
            product.inventory_asset_account.save()
            balancing_account.save()
        
        return redirect('stock_levels')

    return render(request, 'accounting/adjust_stock.html', {'product': product, 'current_stock': stock_item})

@login_required
def stock_levels(request):
    company = get_company(request)
    if not Warehouse.objects.filter(company=company).exists(): Warehouse.objects.create(name="Main Warehouse", company=company)
    stocks = StockItem.objects.filter(product__company=company).select_related('product', 'warehouse')
    total_items = stocks.aggregate(Sum('quantity'))['quantity__sum'] or 0
    total_value = sum(stock.quantity * stock.product.unit_cost for stock in stocks)
    return render(request, 'accounting/stock_levels.html', {'stocks': stocks, 'total_items': total_items, 'total_value': total_value, 'report_date': timezone.now().date()})

# --- FIXED ASSETS ---
@login_required
def asset_list(request):
    company = get_company(request)
    assets = FixedAsset.objects.filter(company=company)
    return render(request, 'accounting/asset_list.html', {'assets': assets})

@login_required
def add_asset(request):
    company = get_company(request)
    
    # --- FIX 1: Broaden the search so the dropdowns are NOT empty ---
    # Look for 'Fixed Assets', 'Asset', 'Other Assets' so we find SOMETHING
    asset_types = ['Fixed Assets', 'Asset', 'Other Assets', 'Other Current Assets']
    asset_accounts = Account.objects.filter(company=company, account_type__in=asset_types, is_active=True)
    
    expense_types = ['Expense', 'Expenses', 'Other Expense', 'Depreciation']
    expense_accounts = Account.objects.filter(company=company, account_type__in=expense_types, is_active=True)
    
    vendors = Vendor.objects.filter(company=company, is_active=True)
    
    if request.method == 'POST':
        try:
            # Handle optional numeric fields safely
            purchase_cost = request.POST.get('purchase_cost') or 0
            salvage_value = request.POST.get('salvage_value') or 0
            useful_life = request.POST.get('useful_life_years') or 0
            
            vendor_id = request.POST.get('vendor')
            vendor = Vendor.objects.get(pk=vendor_id, company=company) if vendor_id else None

            # --- FIX 2: Safety Check ---
            # If the user clicks save with empty dropdowns, show an error message instead of crashing
            asset_acc_id = request.POST.get('asset_account')
            depr_exp_id = request.POST.get('depreciation_expense_account')
            accum_depr_id = request.POST.get('accumulated_depreciation_account')

            if not asset_acc_id or not depr_exp_id or not accum_depr_id:
                messages.error(request, "Error: You must select GL Accounts for Asset, Expense, and Accumulated Depreciation. Please create them in the Chart of Accounts if the list is empty.")
                return render(request, 'accounting/add_asset.html', {
                    'asset_accounts': asset_accounts, 
                    'expense_accounts': expense_accounts, 
                    'vendors': vendors
                })

            FixedAsset.objects.create(
                company=company,
                asset_number=request.POST.get('asset_number') or f"FA-{timezone.now().strftime('%Y%m%d%S')}",
                name=request.POST['name'],
                category=request.POST['category'],
                location=request.POST['location'],
                status=request.POST['status'],
                condition=request.POST['condition'],
                vendor=vendor,
                description=request.POST.get('description', ''),
                acquisition_date=request.POST['acquisition_date'],
                
                # Numeric fields
                purchase_cost=purchase_cost,
                salvage_value=salvage_value,
                useful_life_years=useful_life,
                
                serial_number=request.POST.get('serial_number', ''),
                warranty_expiry_date=request.POST.get('warranty_expiry_date') or None,
                notes=request.POST.get('notes', ''),
                
                # Link Accounts
                asset_account=Account.objects.get(pk=asset_acc_id, company=company),
                depreciation_expense_account=Account.objects.get(pk=depr_exp_id, company=company),
                accumulated_depreciation_account=Account.objects.get(pk=accum_depr_id, company=company),
            )
            messages.success(request, "Fixed Asset created successfully.")
            return redirect('asset_list')
            
        except Exception as e:
            messages.error(request, f"Error saving asset: {str(e)}")
            # Fall through to re-render form with error message

    return render(request, 'accounting/add_asset.html', {
        'asset_accounts': asset_accounts, 
        'expense_accounts': expense_accounts, 
        'vendors': vendors
    })

@login_required
def asset_detail(request, asset_id):
    company = get_company(request)
    asset = FixedAsset.objects.get(pk=asset_id, company=company)
    return render(request, 'accounting/asset_detail.html', {'asset': asset, 'book_value': asset.current_value})

@login_required
def edit_asset(request, asset_id):
    company = get_company(request)
    asset = FixedAsset.objects.get(pk=asset_id, company=company)
    asset_accounts = Account.objects.filter(company=company, account_type='Asset', is_active=True)
    expense_accounts = Account.objects.filter(company=company, account_type='Expense', is_active=True)
    vendors = Vendor.objects.filter(company=company, is_active=True)
    if request.method == 'POST':
        asset.name = request.POST['name']
        # ... (simplified update logic, assume same fields)
        asset.save()
        return redirect('asset_detail', asset_id=asset.id)
    return render(request, 'accounting/edit_asset.html', {'asset': asset, 'asset_accounts': asset_accounts, 'expense_accounts': expense_accounts, 'vendors': vendors})

@login_required
def depreciation_view(request):
    company = get_company(request)
    assets = FixedAsset.objects.filter(company=company, status='Active')
    return render(request, 'accounting/depreciation_view.html', {'assets': assets})

@login_required
@transaction.atomic
def post_depreciation(request, asset_id):
    company = get_company(request)
    asset = FixedAsset.objects.get(pk=asset_id, company=company)
    amount = decimal.Decimal(asset.monthly_depreciation)
    
    if amount > 0:
        # --- FIX: Make JV Number Unique by adding Time (Hour-Minute-Second) ---
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        jv_number = f"DEPR-{asset.id}-{timestamp}"
        # ----------------------------------------------------------------------

        jv = JournalVoucher.objects.create(
            company=company, 
            jv_number=jv_number, 
            jv_date=timezone.now().date(), 
            description=f"Monthly Depr: {asset.name}", 
            status='Posted', 
            posted_at=timezone.now()
        )
        
        # Debit Depreciation Expense
        JournalVoucherLine.objects.create(
            company=company,
            journal_voucher=jv, 
            account=asset.depreciation_expense_account, 
            debit_amount=amount, 
            credit_amount=0, 
            line_description="Depr Exp"
        )
        asset.depreciation_expense_account.current_balance += amount
        asset.depreciation_expense_account.save()

        # Credit Accumulated Depreciation
        JournalVoucherLine.objects.create(
            company=company,
            journal_voucher=jv, 
            account=asset.accumulated_depreciation_account, 
            debit_amount=0, 
            credit_amount=amount, 
            line_description="Accum Depr"
        )
        asset.accumulated_depreciation_account.current_balance -= amount
        asset.accumulated_depreciation_account.save()
        
        messages.success(request, f"Posted ${amount:.2f} depreciation.")
    
    return redirect('depreciation_view')

@login_required
@transaction.atomic
def dispose_asset(request, asset_id):
    company = get_company(request)
    asset = FixedAsset.objects.get(pk=asset_id, company=company)
    bank_accounts = Account.objects.filter(company=company, account_type='Asset', is_active=True)
    income_expense_accounts = Account.objects.filter(company=company, account_type__in=['Revenue', 'Expense'], is_active=True)
    if request.method == 'POST':
        sale_price = decimal.Decimal(request.POST.get('sale_price') or 0)
        disposal_type = request.POST['disposal_type']
        disposal_date = datetime.strptime(request.POST['disposal_date'], "%Y-%m-%d").date()
        
        delta = disposal_date - asset.acquisition_date
        total_depr = decimal.Decimal(asset.monthly_depreciation) * decimal.Decimal(delta.days / 30.44)
        max_depr = asset.purchase_cost - asset.salvage_value
        if total_depr > max_depr: total_depr = max_depr
        book_value = asset.purchase_cost - total_depr
        gain_loss = sale_price - book_value

        asset.status = 'Sold' if disposal_type == 'Sold' else 'Disposed'
        asset.save()

        jv = JournalVoucher.objects.create(company=company, jv_number=f"DISP-{asset.asset_number}-{timezone.now().strftime('%H%M%S')}", jv_date=disposal_date, description=f"Disposal: {asset.name}", status='Posted', posted_at=timezone.now())
        JournalVoucherLine.objects.create(journal_voucher=jv, account=asset.asset_account, debit_amount=0, credit_amount=asset.purchase_cost, line_description="Remove Cost")
        asset.asset_account.current_balance -= asset.purchase_cost
        asset.asset_account.save()
        JournalVoucherLine.objects.create(journal_voucher=jv, account=asset.accumulated_depreciation_account, debit_amount=total_depr, credit_amount=0, line_description="Remove Accum")
        asset.accumulated_depreciation_account.current_balance += total_depr
        asset.accumulated_depreciation_account.save()

        if sale_price > 0:
            bank = Account.objects.get(pk=request.POST['deposit_account'], company=company)
            JournalVoucherLine.objects.create(journal_voucher=jv, account=bank, debit_amount=sale_price, credit_amount=0, line_description="Proceeds")
            bank.current_balance += sale_price
            bank.save()

        gl_acc = Account.objects.get(pk=request.POST['gl_account'], company=company)
        if gain_loss > 0:
            JournalVoucherLine.objects.create(journal_voucher=jv, account=gl_acc, debit_amount=0, credit_amount=gain_loss, line_description="Gain")
            gl_acc.current_balance += gain_loss
        elif gain_loss < 0:
            JournalVoucherLine.objects.create(journal_voucher=jv, account=gl_acc, debit_amount=abs(gain_loss), credit_amount=0, line_description="Loss")
            gl_acc.current_balance += abs(gain_loss)
        gl_acc.save()
        return redirect('asset_list')
    return render(request, 'accounting/dispose_asset.html', {'asset': asset, 'bank_accounts': bank_accounts, 'income_expense_accounts': income_expense_accounts})

# --- PROJECTS ---
@login_required
def project_list(request):
    company = get_company(request)
    query = request.GET.get('search', '')
    if query: p = Project.objects.filter(company=company).filter(Q(name__icontains=query) | Q(code__icontains=query))
    else: p = Project.objects.filter(company=company)
    return render(request, 'accounting/project_list.html', {'projects': p, 'search_query': query})

@login_required
def add_project(request):
    company = get_company(request)
    if request.method == 'POST':
        try:
            Project.objects.create(
                company=company,
                name=request.POST['name'], code=request.POST.get('code') or f"PRJ-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                customer=Customer.objects.get(pk=request.POST['customer'], company=company) if request.POST.get('customer') else None,
                description=request.POST['description'], start_date=request.POST['start_date'],
                deadline=request.POST['deadline'] or None, status=request.POST['status']
            )
            return redirect('project_list')
        except Exception as e:
             return render(request, 'accounting/add_project.html', {'customers': Customer.objects.filter(company=company, is_active=True), 'error': str(e)})
    return render(request, 'accounting/add_project.html', {'customers': Customer.objects.filter(company=company, is_active=True)})

@login_required
def project_detail(request, project_id):
    company = get_company(request)
    p = Project.objects.get(pk=project_id, company=company)
    rev = p.invoices.exclude(status='Void').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    cost = p.expenses.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    return render(request, 'accounting/project_detail.html', {'project': p, 'total_revenue': rev, 'total_cost': cost, 'profit': rev - cost, 'invoices': p.invoices.all(), 'expenses': p.expenses.all()})

@login_required
def change_project_status(request, project_id, new_status):
    company = get_company(request)
    if request.method == 'POST':
        p = Project.objects.get(pk=project_id, company=company)
        p.status = new_status
        p.save()
    return redirect('project_detail', project_id=project_id)

@login_required
def delete_project(request, project_id):
    company = get_company(request)
    if request.method == 'POST': Project.objects.get(pk=project_id, company=company).delete()
    return redirect('project_list')

@login_required
def project_profitability_report(request):
    company = get_company(request)
    pid = request.GET.get('project_id')
    projects = Project.objects.filter(company=company)
    target = projects.filter(id=pid) if pid else projects
    data, tr, tc, tp = [], 0, 0, 0
    for p in target:
        r = p.invoices.exclude(status='Void').aggregate(Sum('total_amount'))['total_amount__sum'] or decimal.Decimal(0)
        c = p.expenses.aggregate(Sum('total_amount'))['total_amount__sum'] or decimal.Decimal(0)
        data.append({'name': p.name, 'code': p.code, 'customer': p.customer, 'status': p.status, 'revenue': r, 'cost': c, 'profit': r-c, 'margin': ((r-c)/r*100) if r else 0})
        tr += r; tc += c; tp += (r-c)
    return render(request, 'accounting/project_report.html', {'projects': projects, 'selected_project_id': int(pid) if pid else None, 'report_data': data, 'total_revenue': tr, 'total_cost': tc, 'total_profit': tp})

# --- BUDGETING ---
@login_required
def budget_list(request):
    company = get_company(request)
    return render(request, 'accounting/budget_list.html', {'budgets': Budget.objects.filter(company=company).order_by('-year')})

@login_required
def add_budget(request):
    company = get_company(request)
    if request.method == 'POST':
        b = Budget.objects.create(company=company, name=request.POST['name'], year=request.POST['year'], description=request.POST['description'])
        return redirect('edit_budget', budget_id=b.id)
    return render(request, 'accounting/add_budget.html')

@login_required
def edit_budget(request, budget_id):
    company = get_company(request)
    budget = Budget.objects.get(pk=budget_id, company=company)
    accts = Account.objects.filter(company=company, account_type__in=['Revenue', 'Income', 'Other Income', 'Expense', 'Expenses', 'Cost of Goods Sold'])
    if request.method == 'POST':
        for a in accts:
            val = request.POST.get(f'amount_{a.id}')
            if val: BudgetItem.objects.update_or_create(budget=budget, account=a, defaults={'monthly_amount': decimal.Decimal(val), 'company': company})
        return redirect('budget_list')
    return render(request, 'accounting/edit_budget.html', {'budget': budget, 'pnl_accounts': accts, 'existing_items': {i.account.id: i.monthly_amount for i in budget.items.all()}})

@login_required
def budget_variance(request, budget_id):
    company = get_company(request)
    b = Budget.objects.get(pk=budget_id, company=company)
    s, e = f"{b.year}-01-01", f"{b.year}-12-31"
    data, tbi, tai, tbe, tae = [], 0, 0, 0, 0
    for item in b.items.select_related('account'):
        ann_bud = item.monthly_amount * 12
        lines = JournalVoucherLine.objects.filter(account=item.account, journal_voucher__jv_date__range=[s, e], journal_voucher__status='Posted')
        if item.account.normal_balance == 'Credit': # Income
            act = lines.aggregate(n=Sum('credit_amount')-Sum('debit_amount'))['n'] or 0
            var = act - ann_bud
            tbi += ann_bud; tai += act
        else:
            act = lines.aggregate(n=Sum('debit_amount')-Sum('credit_amount'))['n'] or 0
            var = ann_bud - act
            tbe += ann_bud; tae += act
        data.append({'account': item.account, 'budget': ann_bud, 'actual': act, 'variance': var, 'percent': (act/ann_bud*100) if ann_bud else 0})
    return render(request, 'accounting/budget_variance.html', {'budget': b, 'report_data': data, 'total_budget_income': tbi, 'total_actual_income': tai, 'total_budget_expense': tbe, 'total_actual_expense': tae})

@login_required
def latest_budget_variance(request):
    company = get_company(request)
    lb = Budget.objects.filter(company=company).order_by('-year').first()
    return redirect('budget_variance', budget_id=lb.id) if lb else redirect('add_budget')

@login_required
def delete_budget(request, budget_id):
    company = get_company(request)
    if request.method == 'POST': Budget.objects.get(pk=budget_id, company=company).delete()
    return redirect('budget_list')

# --- JOURNAL VOUCHER ---
@login_required
@transaction.atomic
def create_voucher(request):
    company = get_company(request)
    accounts = Account.objects.filter(company=company, is_active=True)
    
    if request.method == 'POST':
        # 1. Create Header with Company
        v = JournalVoucher.objects.create(
            company=company,  # <--- Tag the JV
            jv_number=f"JV-{timezone.now().strftime('%Y%m%d-%H%M%S')}", 
            jv_date=request.POST['jv_date'], 
            description=request.POST['description']
        )
        
        accts = request.POST.getlist('account')
        debits = request.POST.getlist('debit')
        credits = request.POST.getlist('credit')
        descs = request.POST.getlist('line_description')
        
        td, tc = decimal.Decimal(0), decimal.Decimal(0)
        
        for i in range(len(accts)):
            d = decimal.Decimal(debits[i] or 0)
            c = decimal.Decimal(credits[i] or 0)
            
            # 2. Create Lines with Company
            JournalVoucherLine.objects.create(
                company=company,  # <--- Tag the Line
                journal_voucher=v, 
                account=Account.objects.get(pk=accts[i], company=company), 
                debit_amount=d, 
                credit_amount=c, 
                line_description=descs[i]
            )
            td += d
            tc += c
        
        # Validation: Must Balance
        if td != tc:
            v.delete()
            messages.error(request, "Journal Entry does not balance. Credits must equal Debits.")
            return render(request, 'accounting/create_voucher.html', {'accounts': accounts})
        
        return redirect('voucher_list')

    return render(request, 'accounting/create_voucher.html', {'accounts': accounts})

@login_required
def voucher_list(request):
    company = get_company(request)
    query = request.GET.get('search', '')
    if query: vouchers = JournalVoucher.objects.filter(company=company).filter(Q(jv_number__icontains=query) | Q(description__icontains=query))
    else: vouchers = JournalVoucher.objects.filter(company=company)
    return render(request, 'accounting/voucher_list.html', {'vouchers': vouchers, 'search_query': query})

@login_required
def voucher_detail(request, jv_id):
    company = get_company(request)
    voucher = JournalVoucher.objects.get(pk=jv_id, company=company)
    totals = voucher.lines.all().aggregate(total_debits=Sum('debit_amount'), total_credits=Sum('credit_amount'))
    return render(request, 'accounting/voucher_detail.html', {'voucher': voucher, 'total_debits': totals['total_debits'], 'total_credits': totals['total_credits']})

@login_required
@transaction.atomic
def edit_voucher(request, jv_id):
    company = get_company(request)
    voucher = JournalVoucher.objects.get(pk=jv_id, company=company)
    if voucher.status != 'Draft': return redirect('voucher_detail', jv_id=jv_id)

    if request.method == 'POST':
        voucher.jv_date = request.POST['jv_date']
        voucher.description = request.POST['description']
        voucher.save()
        voucher.lines.all().delete()

        accts = request.POST.getlist('account')
        debits = request.POST.getlist('debit')
        credits = request.POST.getlist('credit')
        descs = request.POST.getlist('line_description')
        
        for i in range(len(accts)):
            JournalVoucherLine.objects.create(
                journal_voucher=voucher,
                account=Account.objects.get(pk=accts[i], company=company),
                debit_amount=decimal.Decimal(debits[i] or 0),
                credit_amount=decimal.Decimal(credits[i] or 0),
                line_description=descs[i]
            )
        return redirect('voucher_detail', jv_id=jv_id)

    accounts = Account.objects.filter(company=company, is_active=True)
    return render(request, 'accounting/edit_voucher.html', {'voucher': voucher, 'accounts': accounts})

@login_required
@transaction.atomic
def post_voucher(request, jv_id):
    company = get_company(request)
    if request.method == 'POST':
        v = JournalVoucher.objects.get(pk=jv_id, company=company)
        if v.status == 'Draft':
            for line in v.lines.all():
                bal_chg = line.debit_amount - line.credit_amount
                if line.account.normal_balance == 'Credit': line.account.current_balance -= bal_chg
                else: line.account.current_balance += bal_chg
                line.account.save()
            v.status = 'Posted'
            v.posted_at = timezone.now()
            v.save()
    return redirect('voucher_detail', jv_id=jv_id)

@login_required
def upload_voucher(request):
    company = get_company(request)
    if request.method == 'POST':
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            return render(request, 'accounting/upload_voucher.html', {'error': 'Not CSV'})
        try:
            decoded = csv_file.read().decode('utf-8').splitlines()
            reader = csv.reader(decoded)
            next(reader)
            lines, td, tc = [], decimal.Decimal(0), decimal.Decimal(0)
            for r in reader:
                d, c = decimal.Decimal(r[1] or 0), decimal.Decimal(r[2] or 0)
                # Assuming CSV has Account Numbers. Needs validation for company scope in real app.
                acc = Account.objects.get(account_number=r[0], company=company)
                lines.append({'acc': acc, 'd': d, 'c': c, 'desc': r[3]})
                td += d
                tc += c
            if td != tc: raise ValueError("Unbalanced")
            
            with transaction.atomic():
                v = JournalVoucher.objects.create(
                    company=company,
                    jv_number=f"JV-CSV-{timezone.now().strftime('%Y%m%d-%H%M%S')}",
                    jv_date=timezone.now().date(),
                    description=f"Upload: {csv_file.name}",
                    status='Draft'
                )
                for l in lines:
                    JournalVoucherLine.objects.create(journal_voucher=v, account=l['acc'], debit_amount=l['d'], credit_amount=l['c'], line_description=l['desc'])
            return redirect('voucher_list')
        except Exception as e:
            return render(request, 'accounting/upload_voucher.html', {'error': str(e)})
    return render(request, 'accounting/upload_voucher.html')

@login_required
def download_single_voucher(request, jv_id):
    company = get_company(request)
    v = JournalVoucher.objects.get(pk=jv_id, company=company)
    resp = HttpResponse(content_type='text/csv')
    resp['Content-Disposition'] = f'attachment; filename="JV-{v.jv_number}.csv"'
    w = csv.writer(resp)
    w.writerow(['JV Number', 'Date', 'Description', 'Status'])
    w.writerow([v.jv_number, v.jv_date, v.description, v.status])
    w.writerow([])
    w.writerow(['Account', 'Name', 'Debit', 'Credit', 'Line Desc'])
    for l in v.lines.all():
        w.writerow([l.account.account_number, l.account.account_name, l.debit_amount, l.credit_amount, l.line_description])
    return resp

@login_required
def download_all_vouchers(request):
    company = get_company(request)
    resp = HttpResponse(content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="All_JVs.csv"'
    w = csv.writer(resp)
    w.writerow(['JV Number', 'Date', 'Description', 'Status', 'Account', 'Debit', 'Credit', 'Line Desc'])
    for v in JournalVoucher.objects.filter(company=company):
        for l in v.lines.all():
            w.writerow([v.jv_number, v.jv_date, v.description, v.status, l.account.account_number, l.debit_amount, l.credit_amount, l.line_description])
    return resp

# --- BANKING (SAAS) ---
@login_required
def bank_account_list(request):
    company = get_company(request)
    return render(request, 'accounting/bank_account_list.html', {'bank_accounts': BankAccount.objects.filter(company=company)})

@login_required
def add_bank_account(request):
    company = get_company(request)
    
    if request.method == 'POST':
        BankAccount.objects.create(
            company=company,
            name=request.POST['name'],
            account_number=request.POST['account_number'],
            gl_account=Account.objects.get(pk=request.POST['gl_account'], company=company)
        )
        return redirect('bank_account_list')
    
    # --- FIX: Look for 'Bank' OR 'Asset' accounts ---
    # This finds your accounts whether they are labeled "Bank" or "Asset"
    assets = Account.objects.filter(
        company=company, 
        account_type__in=['Bank', 'Asset'], 
        is_active=True
    ).order_by('account_number')
    # ------------------------------------------------
    
    return render(request, 'accounting/add_bank_account.html', {'assets': assets})

@login_required
def delete_bank_account(request, bank_id):
    company = get_company(request)
    if request.method == 'POST': BankAccount.objects.get(pk=bank_id, company=company).delete()
    return redirect('bank_account_list')

@login_required
def upload_bank_statement(request, bank_id):
    company = get_company(request)
    bank = BankAccount.objects.get(pk=bank_id, company=company)
    
    if request.method == 'POST':
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Not a CSV file.")
            return redirect('upload_bank_statement', bank_id=bank_id)

        try:
            decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
            reader = csv.reader(decoded_file)
            next(reader, None) # Skip Header

            count = 0
            for row in reader:
                if len(row) < 3: continue

                date_str = row[0].strip()
                description = row[1].strip()
                amount_str = row[2].strip()

                # Data Cleaning
                clean_amount = amount_str.replace('$', '').replace(',', '').replace(' ', '')
                if '(' in clean_amount and ')' in clean_amount:
                    clean_amount = '-' + clean_amount.replace('(', '').replace(')', '')
                
                if not clean_amount: continue

                # Date Parsing
                formatted_date = None
                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%m-%d-%Y']:
                    try:
                        formatted_date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                
                if formatted_date:
                    # --- FIX IS HERE: Added company=company ---
                    BankStatementLine.objects.create(
                        company=company,  # <--- Tag the Company!
                        bank_account=bank,
                        date=formatted_date,
                        description=description,
                        amount=decimal.Decimal(clean_amount)
                    )
                    count += 1
            
            messages.success(request, f"Successfully uploaded {count} lines.")
            return redirect('reconcile_bank', bank_id=bank_id)

        except Exception as e:
            messages.error(request, f"Critical Error: {e}")
        
    return render(request, 'accounting/upload_bank_statement.html', {'bank_account': bank})

@login_required
def reconcile_bank(request, bank_id):
    company = get_company(request)
    bank = BankAccount.objects.get(pk=bank_id, company=company)
    s_date = request.GET.get('start_date')
    e_date = request.GET.get('end_date')
    
    b_lines = BankStatementLine.objects.filter(bank_account=bank, matched_journal_line__isnull=True).order_by('date')
    s_lines = JournalVoucherLine.objects.filter(account=bank.gl_account, reconciliation_match__isnull=True).order_by('journal_voucher__jv_date')
    m_lines = BankStatementLine.objects.filter(bank_account=bank, matched_journal_line__isnull=False).order_by('-date')

    if s_date and e_date:
        b_lines = b_lines.filter(date__range=[s_date, e_date])
        s_lines = s_lines.filter(journal_voucher__jv_date__range=[s_date, e_date])
        m_lines = m_lines.filter(date__range=[s_date, e_date])

    return render(request, 'accounting/reconcile_bank.html', {'bank_account': bank, 'bank_lines': b_lines, 'system_lines': s_lines, 'matched_lines': m_lines, 'start_date': s_date, 'end_date': e_date})

# --- Reporting Views ---

def report_index(request):
    """
    Shows the main menu for the Report Center.
    """
    return render(request, 'accounting/report_index.html')

def trial_balance_report(request):
    """
    Generates and displays the Trial Balance report.
    """
    # Your logic for calculating trial balance goes here.
    # This is a placeholder to get the page loading.
    # You likely had logic here to sum debits/credits per account.
    # I will provide the basic structure we built earlier.
    
    report_lines = []
    total_debits = decimal.Decimal(0)
    total_credits = decimal.Decimal(0)
    start_date_str = ''
    end_date_str = ''

    if request.method == 'POST':
        date_option = request.POST.get('date_range_option')
        lines_query = JournalVoucherLine.objects.filter(journal_voucher__status='Posted')
        
        if date_option == 'custom':
            start_date_str = request.POST.get('start_date')
            end_date_str = request.POST.get('end_date')
            lines_query = lines_query.filter(journal_voucher__jv_date__lte=end_date_str)
        else:
            if lines_query.exists():
                first_jv = JournalVoucher.objects.filter(status='Posted').order_by('jv_date').first()
                last_jv = JournalVoucher.objects.filter(status='Posted').order_by('jv_date').last()
                start_date_str = first_jv.jv_date.strftime('%Y-%m-%d') if first_jv else ''
                end_date_str = last_jv.jv_date.strftime('%Y-%m-%d') if last_jv else ''

        account_balances = {}
        account_changes = lines_query.values('account_id').annotate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )
        for change in account_changes:
            account_balances[change['account_id']] = (change['total_debit'] or 0) - (change['total_credit'] or 0)

        all_accounts = Account.objects.all().order_by('account_number')
        for account in all_accounts:
            balance = account_balances.get(account.id, decimal.Decimal(0))
            final_debit = decimal.Decimal(0)
            final_credit = decimal.Decimal(0)

            if account.normal_balance == 'Debit':
                if balance >= 0: final_debit = balance
                else: final_credit = -balance
            else:
                if balance <= 0: final_debit = -balance
                else: final_credit = balance

            report_lines.append({
                'number': account.account_number,
                'name': account.account_name,
                'debit': final_debit,
                'credit': final_credit
            })
            total_debits += final_debit
            total_credits += final_credit

    context = {
        'report_lines': report_lines,
        'total_debits': total_debits,
        'total_credits': total_credits,
        'start_date': start_date_str,
        'end_date': end_date_str
    }
    return render(request, 'accounting/trial_balance_report.html', context)

def download_trial_balance(request):
    """
    Generates the CSV download for the Trial Balance.
    """
    # Basic CSV generation logic (simplified for the fix)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="Trial_Balance.csv"'
    writer = csv.writer(response)
    writer.writerow(['Account Number', 'Account Name', 'Debit', 'Credit'])
    # (You would repeat the calculation logic here to fill rows)
    return response

@login_required
def income_statement(request):
    company = get_company(request)
    start_date = request.GET.get('start_date') or f"{timezone.now().year}-01-01"
    end_date = request.GET.get('end_date') or f"{timezone.now().year}-12-31"

    # --- HELPER FUNCTION TO CALCULATE SECTION TOTALS ---
    def get_section_data(account_types, normal_balance):
        accounts = Account.objects.filter(company=company, account_type__in=account_types)
        data = []
        total = decimal.Decimal(0)
        
        for acc in accounts:
            # Calculate net movement for the period
            lines = JournalVoucherLine.objects.filter(
                account=acc, 
                journal_voucher__jv_date__range=[start_date, end_date], 
                journal_voucher__status='Posted'
            )
            d = lines.aggregate(Sum('debit_amount'))['debit_amount__sum'] or 0
            c = lines.aggregate(Sum('credit_amount'))['credit_amount__sum'] or 0
            
            # Net change logic based on account type
            if normal_balance == 'Credit':
                net = c - d
            else:
                net = d - c
                
            if net != 0:
                data.append({'name': acc.account_name, 'amount': net})
                total += net
        return data, total

    # 1. OPERATING INCOME
    inc_list, inc_total = get_section_data(['Revenue', 'Income'], 'Credit')

    # 2. COST OF GOODS SOLD
    cogs_list, cogs_total = get_section_data(['Cost of Goods Sold'], 'Debit')

    # GROSS PROFIT = Income - COGS
    gross_profit = inc_total - cogs_total

    # 3. OPERATING EXPENSES
    exp_list, exp_total = get_section_data(['Expense', 'Expenses'], 'Debit')

    # NET OPERATING INCOME = Gross Profit - Expenses
    net_operating_income = gross_profit - exp_total

    # 4. OTHER INCOME
    other_inc_list, other_inc_total = get_section_data(['Other Income'], 'Credit')

    # 5. OTHER EXPENSES
    other_exp_list, other_exp_total = get_section_data(['Other Expense'], 'Debit')

    # NET OTHER INCOME = Other Income - Other Expenses
    net_other_income = other_inc_total - other_exp_total

    # FINAL NET INCOME
    net_income = net_operating_income + net_other_income

    return render(request, 'accounting/income_statement.html', {
        'start_date': start_date,
        'end_date': end_date,
        # Data for Template
        'inc_list': inc_list, 'inc_total': inc_total,
        'cogs_list': cogs_list, 'cogs_total': cogs_total,
        'gross_profit': gross_profit,
        'exp_list': exp_list, 'exp_total': exp_total,
        'net_operating_income': net_operating_income,
        'other_inc_list': other_inc_list, 'other_inc_total': other_inc_total,
        'other_exp_list': other_exp_list, 'other_exp_total': other_exp_total,
        'net_other_income': net_other_income,
        'net_income': net_income
    })

@login_required
@login_required
def balance_sheet(request):
    company = get_company(request)
    
    # 1. Define ALL possible names for Asset types
    ASSET_TYPES = [
        'Asset', 'Assets', 'Current Asset', 'Fixed Assets', 'Bank', 
        'Cash', 'Accounts Receivable', 'Inventory', 'Other Current Assets', 
        'Other Assets', 'Security Deposit'
    ]
    
    # 2. Define ALL possible names for Liability types
    LIABILITY_TYPES = [
        'Liability', 'Liabilities', 'Current Liability', 'Long Term Liabilities', 
        'Credit Card', 'Accounts Payable', 'Other Current Liabilities', 
        'Payroll Liabilities', 'Taxes Payable'
    ]
    
    # 3. Define ALL possible names for Equity types
    EQUITY_TYPES = [
        'Equity', 'Owner\'s Equity', 'Shareholder\'s Equity', 
        'Retained Earnings', 'Capital', 'Opening Balance Equity'
    ]

    # 4. Filter the database using these lists
    assets = Account.objects.filter(company=company, account_type__in=ASSET_TYPES).order_by('account_number')
    liabilities = Account.objects.filter(company=company, account_type__in=LIABILITY_TYPES).order_by('account_number')
    equity = Account.objects.filter(company=company, account_type__in=EQUITY_TYPES).order_by('account_number')

    # 5. Calculate Totals safely (treating None as 0)
    total_assets = assets.aggregate(Sum('current_balance'))['current_balance__sum'] or decimal.Decimal(0)
    total_liabilities = liabilities.aggregate(Sum('current_balance'))['current_balance__sum'] or decimal.Decimal(0)
    total_equity = equity.aggregate(Sum('current_balance'))['current_balance__sum'] or decimal.Decimal(0)

    # 6. Check for Net Income (Revenue - Expenses) to add to Equity dynamically
    # This ensures the Balance Sheet actually balances!
    revenue_types = ['Revenue', 'Income', 'Other Income', 'Sales']
    expense_types = ['Expense', 'Expenses', 'Cost of Goods Sold', 'Other Expense']
    
    total_revenue = Account.objects.filter(company=company, account_type__in=revenue_types).aggregate(Sum('current_balance'))['current_balance__sum'] or decimal.Decimal(0)
    total_expenses = Account.objects.filter(company=company, account_type__in=expense_types).aggregate(Sum('current_balance'))['current_balance__sum'] or decimal.Decimal(0)
    
    # Calculate Net Income (Revenue is normally Credit, Expense is Debit)
    # Note: Logic depends on how you store balances. Usually Revenue is stored as positive credit.
    # We'll assume standard storage where Credits increase Revenue/Equity and Debits increase Assets/Expenses.
    # If your system stores everything as positive numbers based on normal balance:
    current_net_income = total_revenue - total_expenses

    # Add Net Income to Total Equity for the report display
    total_equity += current_net_income

    return render(request, 'accounting/balance_sheet.html', {
        'assets': assets,
        'liabilities': liabilities,
        'equity': equity,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'current_net_income': current_net_income, # Optional: Pass this if you want to show it as a line item
    })

def ar_aging(request):
    # Placeholder for AR Aging
    return render(request, 'accounting/ar_aging.html', {})

def ap_aging(request):
    # Placeholder for AP Aging
    return render(request, 'accounting/ap_aging.html', {})

def sales_by_customer(request):
    # Placeholder for Sales by Customer
    return render(request, 'accounting/sales_by_customer.html', {})

@login_required
def custom_report(request):
    company = get_company(request)
    
    # --- 1. POPULATE DROPDOWNS (Always run this) ---
    all_accounts = Account.objects.filter(company=company).order_by('account_number')
    
    # Get unique account types for the filter list
    account_types = list(Account.objects.filter(company=company)
                         .values_list('account_type', flat=True)
                         .distinct().order_by('account_type'))

    # Default Context
    context = {
        'all_accounts': all_accounts,
        'account_types': account_types,
        'start_date': request.POST.get('start_date') or f"{timezone.now().year}-01-01",
        'end_date': request.POST.get('end_date') or f"{timezone.now().year}-12-31",
        'report_data': None,
        'selected_types': [],
        'selected_accounts': [],
    }

    # --- 2. PROCESS REPORT GENERATION ---
    if request.method == 'POST':
        try:
            start_date = context['start_date']
            end_date = context['end_date']
            
            # Get selections from form
            selected_types = request.POST.getlist('account_types')
            selected_acc_ids = request.POST.getlist('accounts')
            
            # Convert IDs to integers for safety
            selected_acc_ids = [int(id) for id in selected_acc_ids if id.isdigit()]
            
            context['selected_types'] = selected_types
            context['selected_accounts'] = selected_acc_ids

            # --- 3. FILTER ACCOUNTS ---
            accounts = all_accounts
            
            # If user selected specific accounts, prioritize those
            if selected_acc_ids:
                accounts = accounts.filter(id__in=selected_acc_ids)
            # Otherwise, check if they filtered by type
            elif selected_types:
                accounts = accounts.filter(account_type__in=selected_types)
            
            # --- 4. BUILD REPORT DATA ---
            report_data = []
            
            for acc in accounts:
                # Get lines within date range
                lines = JournalVoucherLine.objects.filter(
                    account=acc,
                    journal_voucher__jv_date__range=[start_date, end_date],
                    journal_voucher__status='Posted'
                ).select_related('journal_voucher').order_by('journal_voucher__jv_date')

                if not lines.exists() and acc.current_balance == 0:
                    continue  # Skip empty accounts to keep report clean

                # Calculate Starting Balance (Sum of all moves BEFORE start_date)
                past_lines = JournalVoucherLine.objects.filter(
                    account=acc,
                    journal_voucher__jv_date__lt=start_date,
                    journal_voucher__status='Posted'
                )
                
                start_debit = past_lines.aggregate(Sum('debit_amount'))['debit_amount__sum'] or 0
                start_credit = past_lines.aggregate(Sum('credit_amount'))['credit_amount__sum'] or 0
                
                if acc.normal_balance == 'Debit':
                    starting_bal = start_debit - start_credit
                else:
                    starting_bal = start_credit - start_debit

                # Process current lines
                processed_lines = []
                running_bal = starting_bal
                
                for line in lines:
                    debit = line.debit_amount
                    credit = line.credit_amount
                    
                    if acc.normal_balance == 'Debit':
                        running_bal += (debit - credit)
                    else:
                        running_bal += (credit - debit)
                        
                    processed_lines.append({
                        'date': line.journal_voucher.jv_date,
                        'ref': line.journal_voucher.jv_number,
                        'desc': line.line_description or line.journal_voucher.description,
                        'debit': debit,
                        'credit': credit,
                        'balance': running_bal,
                        'id': line.journal_voucher.id 
                    })

                report_data.append({
                    'account': acc,
                    'starting_balance': starting_bal,
                    'lines': processed_lines,
                    'ending_balance': running_bal
                })

            context['report_data'] = report_data

        except Exception as e:
            messages.error(request, f"Error generating report: {str(e)}")
            
    return render(request, 'accounting/custom_report.html', context)

def predict_expense_account(request):
    vendor_id = request.GET.get('vendor_id')
    if vendor_id:
        # Find the most common expense account used for this vendor
        most_common = ExpenseLine.objects.filter(
            expense__vendor_id=vendor_id
        ).values('expense_account').annotate(
            count=Count('expense_account')
        ).order_by('-count').first()
        
        if most_common:
            return JsonResponse({'suggested_account_id': most_common['expense_account']})
            
    return JsonResponse({'suggested_account_id': None})

# --- BANK RECONCILIATION (SaaS Enabled) ---

@login_required
def bank_account_list(request):
    company = get_company(request)
    return render(request, 'accounting/bank_account_list.html', {'bank_accounts': BankAccount.objects.filter(company=company)})

@login_required
def add_bank_account(request):
    company = get_company(request)
    
    if request.method == 'POST':
        BankAccount.objects.create(
            company=company,
            name=request.POST['name'],
            account_number=request.POST['account_number'],
            gl_account=Account.objects.get(pk=request.POST['gl_account'], company=company)
        )
        return redirect('bank_account_list')
    
    # --- FIX: Look for 'Bank' OR 'Asset' accounts ---
    # This finds your accounts whether they are labeled "Bank" or "Asset"
    assets = Account.objects.filter(
        company=company, 
        account_type__in=['Bank', 'Asset'], 
        is_active=True
    ).order_by('account_number')
    # ------------------------------------------------
    
    return render(request, 'accounting/add_bank_account.html', {'assets': assets})

@login_required
def delete_bank_account(request, bank_id):
    company = get_company(request)
    if request.method == 'POST':
        BankAccount.objects.get(pk=bank_id, company=company).delete()
        messages.success(request, "Bank account deleted.")
    return redirect('bank_account_list')

@login_required
def upload_bank_statement(request, bank_id):
    company = get_company(request)
    # Ensure the bank account belongs to this company
    bank = BankAccount.objects.get(pk=bank_id, company=company)
    
    if request.method == 'POST':
        csv_file = request.FILES['csv_file']
        
        # Check file type
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Not a CSV file.")
            return redirect('upload_bank_statement', bank_id=bank_id)

        try:
            decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
            reader = csv.reader(decoded_file)
            next(reader, None) # Skip Header

            count = 0
            for row in reader:
                if len(row) < 3: continue

                date_str = row[0].strip()
                description = row[1].strip()
                amount_str = row[2].strip()

                # 1. Clean Amount
                clean_amount = amount_str.replace('$', '').replace(',', '').replace(' ', '')
                if '(' in clean_amount and ')' in clean_amount:
                    clean_amount = '-' + clean_amount.replace('(', '').replace(')', '')
                
                if not clean_amount: continue

                # 2. Parse Date
                formatted_date = None
                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%m-%d-%Y']:
                    try:
                        formatted_date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                
                if formatted_date:
                    # 3. Create Record with COMPANY LINK
                    BankStatementLine.objects.create(
                        company=company,  # <--- THIS IS THE CRITICAL FIX
                        bank_account=bank,
                        date=formatted_date,
                        description=description,
                        amount=decimal.Decimal(clean_amount)
                    )
                    count += 1
            
            messages.success(request, f"Successfully uploaded {count} lines.")
            return redirect('reconcile_bank', bank_id=bank_id)

        except Exception as e:
            # If there is still an error, it will show up here
            messages.error(request, f"Critical Error: {e}")
        
    return render(request, 'accounting/upload_bank_statement.html', {'bank_account': bank})

@login_required
def reconcile_bank(request, bank_id):
    company = get_company(request)
    bank_account = BankAccount.objects.get(pk=bank_id, company=company)
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Left Side: Bank Lines
    bank_lines = BankStatementLine.objects.filter(
        bank_account=bank_account, 
        matched_journal_line__isnull=True
    ).order_by('date')

    # Right Side: GL Transactions
    system_lines = JournalVoucherLine.objects.filter(
        account=bank_account.gl_account,
        reconciliation_match__isnull=True 
    ).order_by('journal_voucher__jv_date')

    if start_date and end_date:
        bank_lines = bank_lines.filter(date__range=[start_date, end_date])
        system_lines = system_lines.filter(journal_voucher__jv_date__range=[start_date, end_date])

    # History
    matched_lines = BankStatementLine.objects.filter(
        bank_account=bank_account, 
        matched_journal_line__isnull=False
    ).order_by('-date')
    
    if start_date and end_date:
        matched_lines = matched_lines.filter(date__range=[start_date, end_date])

    context = {
        'bank_account': bank_account,
        'bank_lines': bank_lines,
        'system_lines': system_lines,
        'matched_lines': matched_lines,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'accounting/reconcile_bank.html', context)

@login_required
def match_transaction(request, statement_id, jv_line_id):
    b_line = BankStatementLine.objects.get(pk=statement_id)
    s_line = JournalVoucherLine.objects.get(pk=jv_line_id)
    
    # Calculate Net GL Amount
    sys_amt = s_line.debit_amount - s_line.credit_amount
    
    if b_line.amount == sys_amt:
        b_line.matched_journal_line = s_line
        b_line.save()
        messages.success(request, "Transaction Matched.")
    else:
        messages.error(request, f"Mismatch: Bank {b_line.amount} vs GL {sys_amt}")
        
    return redirect('reconcile_bank', bank_id=b_line.bank_account.id)

@login_required
def unmatch_transaction(request, statement_id):
    b_line = BankStatementLine.objects.get(pk=statement_id)
    b_line.matched_journal_line = None
    b_line.save()
    return redirect('reconcile_bank', bank_id=b_line.bank_account.id)