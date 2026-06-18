from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView, View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum

from organisations.middleware import TenantContextMixin
from payables.models import Vendor, Bill, BillLine, Payment, PaymentLine, PaymentMethod
from payables.services import VendorService, BillService, PaymentService


class VendorListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Vendor
    context_object_name = 'vendors'
    template_name = 'payables/vendor_list.html'
    paginate_by = 25

    def get_queryset(self):
        queryset = Vendor.objects.filter(organisation=self.request.tenant)

        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by('name')


class VendorCreateView(LoginRequiredMixin, TenantContextMixin, CreateView):
    model = Vendor
    template_name = 'payables/vendor_form.html'
    success_url = reverse_lazy('payables:vendor-list')

    def get_form_class(self):
        from payables.forms import VendorForm
        return VendorForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        form.instance.organisation = self.request.tenant
        messages.success(self.request, _("Vendor created successfully."))
        return super().form_valid(form)


class VendorDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Vendor
    context_object_name = 'vendor'
    template_name = 'payables/vendor_detail.html'

    def get_queryset(self):
        return Vendor.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['open_bills'] = self.object.bills.filter(
            status__in=['open', 'partial']
        ).order_by('-due_date')
        context['recent_transactions'] = self.object.payments.order_by('-payment_date')[:10]
        return context


class VendorUpdateView(LoginRequiredMixin, TenantContextMixin, UpdateView):
    model = Vendor
    template_name = 'payables/vendor_form.html'
    success_url = reverse_lazy('payables:vendor-list')

    def get_form_class(self):
        from payables.forms import VendorForm
        return VendorForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def get_queryset(self):
        return Vendor.objects.filter(organisation=self.request.tenant)

    def form_valid(self, form):
        messages.success(self.request, _("Vendor updated successfully."))
        return super().form_valid(form)


class BillListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Bill
    context_object_name = 'bills'
    template_name = 'payables/bill_list.html'
    paginate_by = 25

    def get_queryset(self):
        queryset = Bill.objects.filter(
            organisation=self.request.tenant
        ).select_related('vendor')

        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        vendor = self.request.GET.get('vendor')
        if vendor:
            queryset = queryset.filter(vendor_id=vendor)

        overdue = self.request.GET.get('overdue')
        if overdue:
            queryset = queryset.filter(
                status__in=['open', 'partial'],
                due_date__lt=timezone.now().date()
            )

        return queryset.order_by('-bill_date')


class BillCreateView(LoginRequiredMixin, TenantContextMixin, CreateView):
    model = Bill
    template_name = 'payables/bill_form.html'
    success_url = reverse_lazy('payables:bill-list')

    def get_form_class(self):
        from payables.forms import BillForm
        return BillForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        # Create bill using service
        lines = []
        for key in self.request.POST:
            if key.startswith('line_account_'):
                idx = key.split('_')[-1]
                lines.append({
                    'account': self.request.POST.get(f'line_account_{idx}'),
                    'description': self.request.POST.get(f'line_description_{idx}', ''),
                    'quantity': self.request.POST.get(f'line_quantity_{idx}', 1),
                    'unit_price': self.request.POST.get(f'line_price_{idx}', 0),
                    'tax_rate': self.request.POST.get(f'line_tax_{idx}', 0),
                })

        bill = BillService.create_bill(
            organisation=self.request.tenant,
            vendor=form.cleaned_data['vendor'],
            bill_date=form.cleaned_data['bill_date'],
            due_date=form.cleaned_data['due_date'],
            lines=lines,
            created_by=self.request.user,
        )

        self.object = bill
        messages.success(self.request, _("Bill created successfully."))
        return redirect(self.get_success_url())


class BillDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Bill
    context_object_name = 'bill'
    template_name = 'payables/bill_detail.html'

    def get_queryset(self):
        return Bill.objects.filter(organisation=self.request.tenant).prefetch_related('lines__account')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['payments'] = self.object.payments.select_related('payment').order_by('-payment__payment_date')
        return context


class BillPostView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        bill = get_object_or_404(Bill, pk=pk, organisation=request.tenant)

        try:
            BillService.post_bill(bill, request.user)
            messages.success(request, _("Bill posted successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('payables:bill-detail', pk=pk)


class BillVoidView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        bill = get_object_or_404(Bill, pk=pk, organisation=request.tenant)
        reason = request.POST.get('reason', '')

        try:
            BillService.void_bill(bill, request.user, reason)
            messages.success(request, _("Bill voided successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('payables:bill-detail', pk=pk)


class PaymentListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Payment
    context_object_name = 'payments'
    template_name = 'payables/payment_list.html'
    paginate_by = 25

    def get_queryset(self):
        queryset = Payment.objects.filter(
            organisation=self.request.tenant
        ).select_related('vendor', 'payment_method')

        vendor = self.request.GET.get('vendor')
        if vendor:
            queryset = queryset.filter(vendor_id=vendor)

        return queryset.order_by('-payment_date')


class PaymentCreateView(LoginRequiredMixin, TenantContextMixin, View):
    template_name = 'payables/payment_form.html'

    def get(self, request):
        vendors = Vendor.objects.filter(organisation=request.tenant, is_active=True)
        payment_methods = PaymentMethod.objects.filter(organisation=request.tenant, is_active=True)

        return render(request, self.template_name, {
            'vendors': vendors,
            'payment_methods': payment_methods,
        })

    def post(self, request):
        vendor_id = request.POST.get('vendor')
        payment_date = request.POST.get('payment_date')
        amount = request.POST.get('amount')
        payment_method_id = request.POST.get('payment_method')

        vendor = get_object_or_404(Vendor, pk=vendor_id, organisation=request.tenant)
        payment_method = get_object_or_404(PaymentMethod, pk=payment_method_id, organisation=request.tenant)

        # Get bill applications
        applications = []
        for key in request.POST:
            if key.startswith('bill_amount_'):
                bill_id = key.replace('bill_amount_', '')
                app_amount = request.POST.get(key)
                if app_amount:
                    applications.append({
                        'bill_id': bill_id,
                        'amount': app_amount,
                    })

        try:
            payment = PaymentService.create_payment(
                organisation=request.tenant,
                vendor=vendor,
                payment_date=payment_date,
                amount=amount,
                payment_method=payment_method,
                applications=applications,
                created_by=request.user,
            )

            if request.POST.get('process_immediately'):
                PaymentService.process_payment(payment, request.user)

            messages.success(request, _("Payment created successfully."))
            return redirect('payables:payment-detail', pk=payment.pk)
        except Exception as e:
            messages.error(request, str(e))
            return self.get(request)


class PaymentDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Payment
    context_object_name = 'payment'
    template_name = 'payables/payment_detail.html'

    def get_queryset(self):
        return Payment.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['applications'] = self.object.applications.select_related('bill').all()
        return context


class PaymentProcessView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk, organisation=request.tenant)

        try:
            PaymentService.process_payment(payment, request.user)
            messages.success(request, _("Payment processed successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('payables:payment-detail', pk=pk)


# Vendor Statement View
class VendorStatementView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Vendor
    template_name = 'payables/vendor_statement.html'
    context_object_name = 'vendor'

    def get_queryset(self):
        return Vendor.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statement'] = VendorService.get_vendor_statement(self.object)
        return context


# HTMX endpoints
class VendorBillsHTMXView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request, pk):
        vendor = get_object_or_404(Vendor, pk=pk, organisation=request.tenant)
        return render(request, 'payables/partials/vendor_bills.html', {
            'vendor': vendor,
            'open_bills': vendor.get_open_bills(),
        })
