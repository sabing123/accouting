from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView, View
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils import timezone

from organisations.middleware import TenantContextMixin
from receivables.models import Customer, Product, Invoice, Receipt, CreditMemo
from receivables.services import CustomerService, InvoiceService, ReceiptService, CreditMemoService


class CustomerListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Customer
    context_object_name = 'customers'
    template_name = 'receivables/customer_list.html'
    paginate_by = 25

    def get_queryset(self):
        queryset = Customer.objects.filter(organisation=self.request.tenant)

        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by('name')


class CustomerCreateView(LoginRequiredMixin, TenantContextMixin, CreateView):
    model = Customer
    template_name = 'receivables/customer_form.html'
    success_url = reverse_lazy('receivables:customer-list')

    def get_form_class(self):
        from receivables.forms import CustomerForm
        return CustomerForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        form.instance.organisation = self.request.tenant
        messages.success(self.request, _("Customer created successfully."))
        return super().form_valid(form)


class CustomerDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Customer
    context_object_name = 'customer'
    template_name = 'receivables/customer_detail.html'

    def get_queryset(self):
        return Customer.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['open_invoices'] = self.object.invoices.filter(
            status__in=['sent', 'partial']
        ).order_by('-due_date')
        context['recent_payments'] = self.object.receipts.order_by('-receipt_date')[:10]
        return context


class CustomerUpdateView(LoginRequiredMixin, TenantContextMixin, UpdateView):
    model = Customer
    template_name = 'receivables/customer_form.html'
    success_url = reverse_lazy('receivables:customer-list')

    def get_form_class(self):
        from receivables.forms import CustomerForm
        return CustomerForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def get_queryset(self):
        return Customer.objects.filter(organisation=self.request.tenant)

    def form_valid(self, form):
        messages.success(self.request, _("Customer updated successfully."))
        return super().form_valid(form)


class CustomerStatementView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Customer
    template_name = 'receivables/customer_statement.html'
    context_object_name = 'customer'

    def get_queryset(self):
        return Customer.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statement'] = CustomerService.get_customer_statement(self.object)
        return context


class ProductListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Product
    context_object_name = 'products'
    template_name = 'receivables/product_list.html'

    def get_queryset(self):
        return Product.objects.filter(organisation=self.request.tenant)

class ProductCreateView(LoginRequiredMixin, TenantContextMixin, CreateView):
    model = Product
    fields = ['name', 'product_code', 'description', 'type', 'unit_price', 'unit', 'revenue_account', 'tax_rate', 'is_taxable']
    template_name = 'receivables/product_form.html'
    success_url = reverse_lazy('receivables:product-list')

    def form_valid(self, form):
        form.instance.organisation = self.request.tenant
        return super().form_valid(form)


class ProductUpdateView(LoginRequiredMixin, TenantContextMixin, UpdateView):
    model = Product
    fields = ['name', 'product_code', 'description', 'type', 'unit_price', 'unit', 'revenue_account', 'tax_rate', 'is_active', 'is_taxable']
    template_name = 'receivables/product_form.html'
    success_url = reverse_lazy('receivables:product-list')

    def get_queryset(self):
        return Product.objects.filter(organisation=self.request.tenant)


class InvoiceListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Invoice
    context_object_name = 'invoices'
    template_name = 'receivables/invoice_list.html'
    paginate_by = 25

    def get_queryset(self):
        queryset = Invoice.objects.filter(
            organisation=self.request.tenant
        ).select_related('customer')

        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        customer = self.request.GET.get('customer')
        if customer:
            queryset = queryset.filter(customer_id=customer)

        overdue = self.request.GET.get('overdue')
        if overdue:
            queryset = queryset.filter(
                status__in=['sent', 'partial'],
                due_date__lt=timezone.now().date()
            )

        return queryset.order_by('-invoice_date')


class InvoiceCreateView(LoginRequiredMixin, TenantContextMixin, View):
    template_name = 'receivables/invoice_form.html'

    def get(self, request):
        customers = Customer.objects.filter(organisation=request.tenant, is_active=True)
        products = Product.objects.filter(organisation=request.tenant, is_active=True)
        from ledger.models import Account
        revenue_accounts = Account.objects.filter(
            organisation=request.tenant,
            account_type__name='income',
            is_active=True
        )

        return render(request, self.template_name, {
            'customers': customers,
            'products': products,
            'revenue_accounts': revenue_accounts,
        })

    def post(self, request):
        customer_id = request.POST.get('customer')
        invoice_date = request.POST.get('invoice_date')
        due_date = request.POST.get('due_date')
        payment_terms = request.POST.get('payment_terms', 'net_30')
        description = request.POST.get('description', '')

        customer = get_object_or_404(Customer, pk=customer_id, organisation=request.tenant)

        # Build lines from POST
        lines = []
        for key in request.POST:
            if key.startswith('line_account_'):
                idx = key.split('_')[-1]
                lines.append({
                    'account': request.POST.get(f'line_account_{idx}'),
                    'description': request.POST.get(f'line_description_{idx}', ''),
                    'quantity': request.POST.get(f'line_quantity_{idx}', 1),
                    'unit_price': request.POST.get(f'line_price_{idx}', 0),
                    'tax_rate': request.POST.get(f'line_tax_{idx}', 0),
                    'discount_percent': request.POST.get(f'line_discount_{idx}', 0),
                    'product': request.POST.get(f'line_product_{idx}'),
                })

        try:
            invoice = InvoiceService.create_invoice(
                organisation=request.tenant,
                customer=customer,
                invoice_date=invoice_date,
                lines=lines,
                created_by=request.user,
                due_date=due_date or None,
                payment_terms=payment_terms,
                description=description,
            )

            messages.success(request, _("Invoice created successfully."))
            return redirect('receivables:invoice-detail', pk=invoice.pk)
        except Exception as e:
            messages.error(request, str(e))
            return self.get(request)


class InvoiceDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Invoice
    context_object_name = 'invoice'
    template_name = 'receivables/invoice_detail.html'

    def get_queryset(self):
        return Invoice.objects.filter(organisation=self.request.tenant).prefetch_related('lines__account')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['payments'] = self.object.payments.select_related('receipt').order_by('-receipt__receipt_date')
        return context


class InvoiceEditView(LoginRequiredMixin, TenantContextMixin, UpdateView):
    model = Invoice
    template_name = 'receivables/invoice_form.html'
    success_url = reverse_lazy('receivables:invoice-list')

    def get_queryset(self):
        return Invoice.objects.filter(
            organisation=self.request.tenant,
            status='draft'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['customers'] = Customer.objects.filter(organisation=self.request.tenant)
        context['products'] = Product.objects.filter(organisation=self.request.tenant)
        return context


class InvoiceSendView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, organisation=request.tenant)

        try:
            InvoiceService.send_invoice(invoice, request.user)
            messages.success(request, _("Invoice sent and posted to accounting."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('receivables:invoice-detail', pk=pk)


class InvoiceCancelView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, organisation=request.tenant)
        reason = request.POST.get('reason', '')

        try:
            InvoiceService.cancel_invoice(invoice, request.user, reason)
            messages.success(request, _("Invoice cancelled successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('receivables:invoice-detail', pk=pk)


class InvoicePDFView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, organisation=request.tenant)

        # Generate PDF
        from reportlab.pdfgen import canvas
        from io import BytesIO
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'

        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        p.drawString(100, 750, f"Invoice: {invoice.invoice_number}")
        p.drawString(100, 720, f"Customer: {invoice.customer.name}")
        p.drawString(100, 690, f"Date: {invoice.invoice_date}")
        p.drawString(100, 660, f"Due Date: {invoice.due_date}")
        p.drawString(100, 630, f"Total: ${invoice.total}")
        p.showPage()
        p.save()

        response.write(buffer.getvalue())
        buffer.close()
        return response


class ReceiptListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Receipt
    context_object_name = 'receipts'
    template_name = 'receivables/receipt_list.html'
    paginate_by = 25

    def get_queryset(self):
        queryset = Receipt.objects.filter(
            organisation=self.request.tenant
        ).select_related('customer')

        customer = self.request.GET.get('customer')
        if customer:
            queryset = queryset.filter(customer_id=customer)

        return queryset.order_by('-receipt_date')


class ReceiptCreateView(LoginRequiredMixin, TenantContextMixin, View):
    template_name = 'receivables/receipt_form.html'

    def get(self, request):
        customers = Customer.objects.filter(organisation=request.tenant, is_active=True)
        from banking.models import BankAccount
        bank_accounts = BankAccount.objects.filter(organisation=request.tenant, is_active=True)

        return render(request, self.template_name, {
            'customers': customers,
            'bank_accounts': bank_accounts,
        })

    def post(self, request):
        customer_id = request.POST.get('customer')
        receipt_date = request.POST.get('receipt_date')
        amount = request.POST.get('amount')
        payment_method = request.POST.get('payment_method')
        check_number = request.POST.get('check_number', '')
        bank_account_id = request.POST.get('bank_account')

        customer = get_object_or_404(Customer, pk=customer_id, organisation=request.tenant)

        # Get invoice applications
        applications = []
        for key in request.POST:
            if key.startswith('invoice_amount_'):
                invoice_id = key.replace('invoice_amount_', '')
                app_amount = request.POST.get(key)
                if app_amount:
                    applications.append({
                        'invoice_id': invoice_id,
                        'amount': app_amount,
                    })

        try:
            receipt = ReceiptService.create_receipt(
                organisation=request.tenant,
                customer=customer,
                receipt_date=receipt_date,
                amount=amount,
                applications=applications,
                created_by=request.user,
                payment_method=payment_method,
                check_number=check_number,
                bank_account_id=bank_account_id or None,
            )

            if request.POST.get('process_immediately'):
                ReceiptService.process_receipt(receipt, request.user)

            messages.success(request, _("Receipt created successfully."))
            return redirect('receivables:receipt-detail', pk=receipt.pk)
        except Exception as e:
            messages.error(request, str(e))
            return self.get(request)


class ReceiptDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Receipt
    context_object_name = 'receipt'
    template_name = 'receivables/receipt_detail.html'

    def get_queryset(self):
        return Receipt.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['applications'] = self.object.applications.select_related('invoice').all()
        return context


class ReceiptProcessView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        receipt = get_object_or_404(Receipt, pk=pk, organisation=request.tenant)

        try:
            ReceiptService.process_receipt(receipt, request.user)
            messages.success(request, _("Receipt processed successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('receivables:receipt-detail', pk=pk)


class CreditMemoListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = CreditMemo
    context_object_name = 'credit_memos'
    template_name = 'receivables/credit_memo_list.html'

    def get_queryset(self):
        return CreditMemo.objects.filter(organisation=self.request.tenant)

class CreditMemoCreateView(LoginRequiredMixin, TenantContextMixin, View):
    template_name = 'receivables/credit_memo_form.html'

    def get(self, request):
        customers = Customer.objects.filter(organisation=request.tenant, is_active=True)
        return render(request, self.template_name, {'customers': customers})

    def post(self, request):
        customer_id = request.POST.get('customer')
        credit_date = request.POST.get('credit_date')
        amount = request.POST.get('amount')
        reason = request.POST.get('reason')
        invoice_id = request.POST.get('invoice')

        customer = get_object_or_404(Customer, pk=customer_id, organisation=request.tenant)

        try:
            memo = CreditMemoService.create_credit_memo(
                organisation=request.tenant,
                customer=customer,
                credit_date=credit_date,
                amount=amount,
                reason=reason,
                invoice_id=invoice_id or None,
                created_by=request.user,
            )

            if request.POST.get('issue_immediately'):
                CreditMemoService.issue_credit_memo(memo, request.user)

            messages.success(request, _("Credit memo created successfully."))
            return redirect('receivables:credit-memo-issue', pk=memo.pk)
        except Exception as e:
            messages.error(request, str(e))
            return self.get(request)


class CreditMemoIssueView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        memo = get_object_or_404(CreditMemo, pk=pk, organisation=request.tenant)

        try:
            CreditMemoService.issue_credit_memo(memo, request.user)
            messages.success(request, _("Credit memo issued successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('receivables:credit-memo-list')


# HTMX endpoints
class CustomerInvoicesHTMXView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk, organisation=request.tenant)
        return render(request, 'receivables/partials/customer_invoices.html', {
            'customer': customer,
            'open_invoices': customer.invoices.filter(status__in=['sent', 'partial']).order_by('-due_date'),
        })
