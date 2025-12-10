from django.urls import path
from . import views

urlpatterns = [
    # --- Dashboard ---
    path('', views.dashboard, name='dashboard'),

    # --- Settings & Profile (SaaS) ---
    path('settings/profile/', views.profile_view, name='profile_view'),
    path('settings/company/', views.settings_view, name='settings_view'),

    # --- Account URLs ---
    path('chart-of-accounts/', views.account_list, name='account_list'),
    path('add/', views.add_account, name='add_account'),
    path('account/<int:account_id>/edit/', views.edit_account, name='edit_account'),
    path('toggle_activity/<int:account_id>/', views.toggle_account_activity, name='toggle_account_activity'),
    path('recalculate-balances/', views.recalculate_balances, name='recalculate_balances'),
    path('account/<int:account_id>/ledger/', views.account_ledger, name='account_ledger'),

    # --- Journal Voucher URLs ---
    path('vouchers/', views.voucher_list, name='voucher_list'),
    path('vouchers/create/', views.create_voucher, name='create_voucher'),
    path('vouchers/upload/', views.upload_voucher, name='upload_voucher'),
    path('vouchers/<int:jv_id>/', views.voucher_detail, name='voucher_detail'),
    path('vouchers/<int:jv_id>/edit/', views.edit_voucher, name='edit_voucher'),
    path('vouchers/<int:jv_id>/post/', views.post_voucher, name='post_voucher'),
    path('vouchers/<int:jv_id>/download/', views.download_single_voucher, name='download_single_voucher'),
    path('vouchers/download_all/', views.download_all_vouchers, name='download_all_vouchers'),
    
    # --- Reporting URLs ---
    path('reports/', views.report_index, name='report_index'),
    path('reports/trial_balance/', views.trial_balance_report, name='trial_balance_report'),
    path('reports/trial_balance/download/', views.download_trial_balance, name='download_trial_balance'),
    path('reports/income-statement/', views.income_statement, name='income_statement'),
    path('reports/balance-sheet/', views.balance_sheet, name='balance_sheet'),
    path('reports/ar-aging/', views.ar_aging, name='ar_aging'),
    path('reports/ap-aging/', views.ap_aging, name='ap_aging'),
    path('reports/sales-by-customer/', views.sales_by_customer, name='sales_by_customer'),
    path('reports/custom/', views.custom_report, name='custom_report'),

    # --- Purchase Order URLs ---
    path('purchase-orders/', views.po_list, name='po_list'),
    path('purchase-orders/create/', views.create_po, name='create_po'),
    path('purchase-orders/<int:po_id>/', views.po_detail, name='po_detail'),
    path('purchase-orders/<int:po_id>/status/<str:new_status>/', views.change_po_status, name='change_po_status'),

    # --- Vendor URLs ---
    path('vendors/', views.vendor_list, name='vendor_list'),
    path('vendors/add/', views.add_vendor, name='add_vendor'),
    path('vendors/edit/<int:vendor_id>/', views.edit_vendor, name='edit_vendor'),
    path('vendors/toggle/<int:vendor_id>/', views.toggle_vendor_activity, name='toggle_vendor_activity'),
    path('vendors/<int:vendor_id>/', views.vendor_detail, name='vendor_detail'),

    # --- Expense URLs ---
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/create/', views.create_expense, name='create_expense'),
    path('expenses/<int:expense_id>/', views.expense_detail, name='expense_detail'),
    path('expenses/<int:expense_id>/status/<str:new_status>/', views.change_expense_status, name='change_expense_status'),
    path('api/predict-account/', views.predict_expense_account, name='predict_expense_account'),

    # --- Customer URLs ---
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.add_customer, name='add_customer'),
    path('customers/edit/<int:customer_id>/', views.edit_customer, name='edit_customer'),
    path('customers/toggle/<int:customer_id>/', views.toggle_customer_activity, name='toggle_customer_activity'),
    path('customers/<int:customer_id>/', views.customer_detail, name='customer_detail'),

    # --- Invoice URLs ---
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/create/', views.create_invoice, name='create_invoice'),
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:invoice_id>/status/<str:new_status>/', views.change_invoice_status, name='change_invoice_status'),
    path('invoices/<int:invoice_id>/receive_payment/', views.receive_payment, name='receive_payment'),
    path('invoices/<int:invoice_id>/refund/', views.refund_invoice, name='refund_invoice'),

    # --- Inventory URLs ---
    path('inventory/products/', views.product_list, name='product_list'),
    path('inventory/products/add/', views.add_product, name='add_product'),
    path('inventory/stock/', views.stock_levels, name='stock_levels'),
    path('inventory/adjust/<int:product_id>/', views.adjust_stock, name='adjust_stock'),
    path('inventory/products/delete/<int:product_id>/', views.delete_product, name='delete_product'),

    # --- Fixed Asset URLs ---
    path('assets/', views.asset_list, name='asset_list'),
    path('assets/add/', views.add_asset, name='add_asset'),
    path('assets/<int:asset_id>/', views.asset_detail, name='asset_detail'),
    path('assets/<int:asset_id>/edit/', views.edit_asset, name='edit_asset'),
    path('assets/dispose/<int:asset_id>/', views.dispose_asset, name='dispose_asset'),
    path('assets/depreciation/', views.depreciation_view, name='depreciation_view'),
    path('assets/post-depreciation/<int:asset_id>/', views.post_depreciation, name='post_depreciation'),

    # --- Project URLs ---
    path('projects/', views.project_list, name='project_list'),
    path('projects/add/', views.add_project, name='add_project'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
    path('projects/<int:project_id>/status/<str:new_status>/', views.change_project_status, name='change_project_status'),
    path('projects/delete/<int:project_id>/', views.delete_project, name='delete_project'),
    path('projects/reports/profitability/', views.project_profitability_report, name='project_profitability_report'),

    # --- Budget URLs ---
    path('budgeting/', views.budget_list, name='budget_list'),
    path('budgeting/add/', views.add_budget, name='add_budget'),
    path('budgeting/edit/<int:budget_id>/', views.edit_budget, name='edit_budget'),
    path('budgeting/variance/<int:budget_id>/', views.budget_variance, name='budget_variance'),
    path('budgeting/variance/latest/', views.latest_budget_variance, name='latest_budget_variance'),
    path('budgeting/delete/<int:budget_id>/', views.delete_budget, name='delete_budget'),

    # --- Bank Reconciliation URLs ---
    path('banking/', views.bank_account_list, name='bank_account_list'),
    path('banking/add/', views.add_bank_account, name='add_bank_account'),
    path('banking/delete/<int:bank_id>/', views.delete_bank_account, name='delete_bank_account'),
    path('banking/<int:bank_id>/upload/', views.upload_bank_statement, name='upload_bank_statement'),
    path('banking/<int:bank_id>/reconcile/', views.reconcile_bank, name='reconcile_bank'),
    path('banking/match/<int:statement_id>/<int:jv_line_id>/', views.match_transaction, name='match_transaction'),
    path('banking/unmatch/<int:statement_id>/', views.unmatch_transaction, name='unmatch_transaction'),
]