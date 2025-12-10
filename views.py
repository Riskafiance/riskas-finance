# In accounting/views.py
from django.shortcuts import render, redirect
from .models import Account

def account_list(request):
    """
    This view fetches all accounts from the database and displays them.
    """
    accounts = Account.objects.all()
    context = {
        'accounts': accounts
    }
    return render(request, 'accounting/account_list.html', context)

def add_account(request):
    """
    This view handles the form for adding a new account.
    """
    if request.method == 'POST':
        # Get the data from the form
        number = request.POST['account_number']
        name = request.POST['account_name']
        acc_type = request.POST['account_type']
        normal_bal = request.POST['normal_balance']

        # Create and save the new account object
        Account.objects.create(
            account_number=number,
            account_name=name,
            account_type=acc_type,
            normal_balance=normal_bal
        )
        # Redirect back to the account list after adding
        return redirect('account_list')
    
    # If it's a GET request, just show the blank form
    return render(request, 'accounting/add_account.html')