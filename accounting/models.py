from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone  # <--- THIS WAS MISSING

class Company(models.Model):
    """
    Represents a Client (Tenant) who buys your software.
    Everything else in the system will be linked to this.
    """
    name = models.CharField(max_length=200)
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='company_profile')
    
    # Contact & Branding
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)

    verification_code = models.CharField(max_length=6, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# --- CORE FINANCIAL MODELS ---
class Account(models.Model):
    ACCOUNT_TYPES = [
        ('Accounts Receivable', 'Accounts Receivable (A/R)'),
        ('Other Current Assets', 'Other Current Assets'),
        ('Bank', 'Bank'),
        ('Fixed Assets', 'Fixed Assets'),
        ('Other Assets', 'Other Assets'),
        ('Accounts Payable', 'Accounts Payable (A/P)'),
        ('Credit Card', 'Credit Card'),
        ('Other Current Liabilities', 'Other Current Liabilities'),
        ('Long Term Liabilities', 'Long Term Liabilities'),
        ('Equity', 'Equity'),
        ('Income', 'Income'),
        ('Other Income', 'Other Income'),
        ('Cost of Goods Sold', 'Cost of Goods Sold'),
        ('Expenses', 'Expenses'),
        ('Other Expense', 'Other Expense'),
    ]

    NORMAL_BALANCES = [('Debit', 'Debit'), ('Credit', 'Credit')]

    company = models.ForeignKey('Company', on_delete=models.CASCADE)
    account_number = models.CharField(max_length=20, unique=True)
    account_name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=50, choices=ACCOUNT_TYPES)
    normal_balance = models.CharField(max_length=10, choices=NORMAL_BALANCES)
    current_balance = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_number} - {self.account_name}"

    class Meta:
        ordering = ['account_number']

# --- ENTITIES ---
class Vendor(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField(blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    class Meta:
        ordering = ['name']

class Customer(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField(blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    class Meta:
        ordering = ['name']

# --- PROJECTS (JOB COSTING) ---
class Project(models.Model):
    PROJECT_STATUS = [
        ('Not Started', 'Not Started'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('On Hold', 'On Hold'),
        ('Cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects')
    description = models.TextField(blank=True, default='')
    
    start_date = models.DateField(default=timezone.now)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=PROJECT_STATUS, default='In Progress')
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"
        
    class Meta:
        ordering = ['-created_at']

# --- INVENTORY ---
class Warehouse(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField(blank=True, default='')
    def __str__(self): return self.name

class Category(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=50, unique=True)
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "Categories"

class Product(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    sku = models.CharField(max_length=50, unique=True, verbose_name="SKU")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    
    unit_of_measure = models.CharField(max_length=50, default="Item")
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    preferred_vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    
    unit_cost = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    unit_price = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    
    inventory_asset_account = models.ForeignKey(Account, related_name='asset_products', on_delete=models.PROTECT, limit_choices_to={'account_type': 'Asset'})
    expense_account = models.ForeignKey(Account, related_name='expense_products', on_delete=models.PROTECT, limit_choices_to={'account_type': 'Expense'}, null=True)
    revenue_account = models.ForeignKey(Account, related_name='revenue_products', on_delete=models.PROTECT, limit_choices_to={'account_type': 'Revenue'}, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.sku}] {self.name}"

class StockItem(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    class Meta: unique_together = ('product', 'warehouse')
    @property
    def total_value(self): return self.quantity * self.product.unit_cost

# --- TRANSACTIONS ---
class PurchaseOrder(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    PO_STATUSES = [('Draft', 'Draft'), ('Issued', 'Issued'), ('Received', 'Received'), ('Cancelled', 'Cancelled'), ('Closed', 'Closed')]
    po_number = models.CharField(max_length=50, unique=True)
    po_date = models.DateField()
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, null=True)
    vendor_name = models.CharField(max_length=100, blank=True, default='')
    vendor_address = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=PO_STATUSES, default='Draft')
    total_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.po_number} - {self.vendor_name}"
    class Meta: ordering = ['-po_date', '-po_number']

class PurchaseOrderLine(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    purchase_order = models.ForeignKey(PurchaseOrder, related_name='lines', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    item_description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=19, decimal_places=2)
    line_total = models.DecimalField(max_digits=19, decimal_places=2)
    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

class Invoice(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    INVOICE_STATUSES = [('Draft', 'Draft'), ('Sent', 'Sent'), ('Paid', 'Paid'), ('Void', 'Void'), ('Refunded', 'Refunded')]
    PAYMENT_TERMS = [('Due on Receipt', 'Due on Receipt'), ('Net 15', 'Net 15'), ('Net 30', 'Net 30'), ('Net 60', 'Net 60')]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    ar_account = models.ForeignKey(Account, on_delete=models.PROTECT, limit_choices_to={'account_type': 'Asset'}, null=True)
    
    # --- NEW PROJECT LINK ---
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    invoice_date = models.DateField()
    due_date = models.DateField()
    invoice_number = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, default='')
    
    customer_message = models.TextField(blank=True, default='', help_text="Message displayed on the invoice")
    internal_notes = models.TextField(blank=True, default='', help_text="Private notes, not shown to customer")
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS, default='Due on Receipt')

    status = models.CharField(max_length=20, choices=INVOICE_STATUSES, default='Draft')
    total_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.invoice_number} - {self.customer.name}"
    class Meta: ordering = ['-invoice_date', '-invoice_number']

class InvoiceLine(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, related_name='lines', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    revenue_account = models.ForeignKey(Account, on_delete=models.PROTECT)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    unit_price = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    line_total = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    
    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)
    def __str__(self): return f"{self.description} ({self.line_total})"

class JournalVoucher(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    JV_STATUSES = [('Draft', 'Draft'), ('Posted', 'Posted')]
    jv_number = models.CharField(max_length=50, unique=True)
    jv_date = models.DateField()
    description = models.TextField()
    status = models.CharField(max_length=20, choices=JV_STATUSES, default='Draft')
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    def __str__(self): return f"{self.jv_number} - {self.description}"
    class Meta: ordering = ['-jv_date', '-jv_number']

class JournalVoucherLine(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    journal_voucher = models.ForeignKey(JournalVoucher, related_name='lines', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    credit_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    line_description = models.CharField(max_length=255, blank=True)
    def __str__(self): return f"Line for JV {self.journal_voucher.jv_number}"

# --- BANKING ---
class BankAccount(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    gl_account = models.OneToOneField(Account, on_delete=models.PROTECT, limit_choices_to={'account_type': 'Asset'})
    currency = models.CharField(max_length=10, default='USD')
    def __str__(self): return f"{self.name} ({self.account_number})"

class BankStatementLine(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE)
    date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=19, decimal_places=2)
    matched_journal_line = models.OneToOneField(JournalVoucherLine, on_delete=models.SET_NULL, null=True, blank=True, related_name='reconciliation_match')
    created_at = models.DateTimeField(auto_now_add=True)

# --- EXPENSES ---
class Expense(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    EXPENSE_STATUSES = [('Draft', 'Draft'), ('Approved', 'Approved'), ('Declined', 'Declined')]
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    expense_date = models.DateField()
    reference_number = models.CharField(max_length=50, blank=True, default='')
    description = models.TextField(blank=True, default='')
    payment_account = models.ForeignKey(Account, related_name='expense_payments', on_delete=models.PROTECT)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    
    # --- NEW PROJECT LINK ---
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=EXPENSE_STATUSES, default='Draft')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Exp #{self.id} - {self.vendor.name}"
    class Meta: ordering = ['-expense_date']

class ExpenseLine(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    expense = models.ForeignKey(Expense, related_name='lines', on_delete=models.CASCADE)
    expense_account = models.ForeignKey(Account, related_name='expense_lines', on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=19, decimal_places=2)
    def __str__(self): return f"{self.expense_account.account_name}: {self.amount}"

# --- ASSET MANAGEMENT ---
class FixedAsset(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    ASSET_STATUS = [('Active', 'Active'), ('Sold', 'Sold'), ('Disposed', 'Disposed'), ('In Repair', 'In Repair')]
    CONDITION_CHOICES = [('New', 'New'), ('Excellent', 'Excellent'), ('Good', 'Good'), ('Fair', 'Fair'), ('Poor', 'Poor')]

    asset_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=ASSET_STATUS, default='Active')
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='New')
    description = models.TextField(blank=True, default='')
    acquisition_date = models.DateField()
    purchase_cost = models.DecimalField(max_digits=19, decimal_places=2)
    salvage_value = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    useful_life_years = models.IntegerField()
    serial_number = models.CharField(max_length=100, blank=True, default='')
    warranty_expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    image_url = models.URLField(blank=True, default='')
    
    asset_account = models.ForeignKey(Account, related_name='fixed_assets', on_delete=models.PROTECT, limit_choices_to={'account_type': 'Asset'})
    depreciation_expense_account = models.ForeignKey(Account, related_name='depreciation_expenses', on_delete=models.PROTECT, limit_choices_to={'account_type': 'Expense'})
    accumulated_depreciation_account = models.ForeignKey(Account, related_name='accumulated_depreciations', on_delete=models.PROTECT, limit_choices_to={'account_type': 'Asset'})
    
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.asset_number} - {self.name}"

    @property
    def monthly_depreciation(self):
        depreciable_amount = self.purchase_cost - self.salvage_value
        total_months = self.useful_life_years * 12
        return depreciable_amount / total_months if total_months > 0 else 0
    
    @property
    def current_value(self):
        from datetime import date
        today = date.today()
        delta = today - self.acquisition_date
        months_passed = delta.days / 30.44
        total_depreciation = float(self.monthly_depreciation) * months_passed
        max_depreciation = float(self.purchase_cost - self.salvage_value)
        if total_depreciation > max_depreciation: total_depreciation = max_depreciation
        return float(self.purchase_cost) - total_depreciation

# --- BUDGETING ---
class Budget(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    year = models.IntegerField(default=2025)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.name} ({self.year})"

class BudgetItem(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    budget = models.ForeignKey(Budget, related_name='items', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    monthly_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0.00)
    class Meta: unique_together = ('budget', 'account')
    def __str__(self): return f"{self.account.account_name}: {self.monthly_amount}"

# In accounting/models.py

class CompanySettings(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    """
    Stores the global settings for the application instance.
    Usually, there is only one row in this table.
    """
    company_name = models.CharField(max_length=200, default="My Company")
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)

    def __str__(self):
        return self.company_name

    # Helper to always get the single instance
    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj