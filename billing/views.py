from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, ListView, View
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib import messages

from organisations.middleware import TenantContextMixin
from billing.models import Plan, Subscription, PaymentHistory, Coupon
from billing.services import StripeService, SubscriptionService


class PlansListView(ListView):
    model = Plan
    context_object_name = 'plans'
    template_name = 'billing/plans.html'

    def get_queryset(self):
        return Plan.objects.active()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['current_subscription'] = getattr(self.request.user.get_default_organisation(), 'subscription', None)
        return context


class SubscriptionView(LoginRequiredMixin, TenantContextMixin, TemplateView):
    template_name = 'billing/subscription.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.tenant:
            context['subscription'] = getattr(self.request.tenant, 'subscription', None)
            context['plans'] = Plan.objects.active()

            # Get payment methods from Stripe
            if context['subscription'] and context['subscription'].stripe_customer_id:
                try:
                    context['payment_methods'] = StripeService.get_payment_methods(
                        context['subscription'].stripe_customer_id
                    )
                except Exception:
                    context['payment_methods'] = []

        return context


class CheckoutView(LoginRequiredMixin, TenantContextMixin, View):
    template_name = 'billing/checkout.html'

    def get(self, request):
        plan_id = request.GET.get('plan')
        if not plan_id:
            return redirect('billing:plans')

        plan = get_object_or_404(Plan, pk=plan_id, is_active=True)
        billing_period = request.GET.get('period', 'monthly')

        # Get or create subscription
        organisation = request.tenant
        subscription = getattr(organisation, 'subscription', None)

        if subscription and subscription.stripe_customer_id:
            customer_id = subscription.stripe_customer_id
        else:
            customer_id = None

        # Determine price
        if billing_period == 'yearly':
            price = plan.price_yearly
            stripe_price_id = plan.stripe_price_yearly_id
        else:
            price = plan.price_monthly
            stripe_price_id = plan.stripe_price_monthly_id

        return render(request, self.template_name, {
            'plan': plan,
            'billing_period': billing_period,
            'price': price,
            'stripe_price_id': stripe_price_id,
            'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
            'customer_id': customer_id,
        })

    def post(self, request):
        plan_id = request.POST.get('plan_id')
        payment_method_id = request.POST.get('payment_method_id')
        billing_period = request.POST.get('billing_period', 'monthly')
        coupon_code = request.POST.get('coupon_code', '')

        plan = get_object_or_404(Plan, pk=plan_id)

        try:
            subscription = SubscriptionService.activate_subscription(
                organisation=request.tenant,
                plan=plan,
                billing_period=billing_period,
                payment_method_id=payment_method_id,
                coupon_code=coupon_code or None,
            )

            messages.success(request, "Subscription activated successfully!")
            return redirect('billing:subscription')
        except Exception as e:
            messages.error(request, str(e))
            return self.get(request)


class CancelSubscriptionView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request):
        subscription = getattr(request.tenant, 'subscription', None)

        if not subscription:
            return redirect('billing:subscription')

        reason = request.POST.get('reason', '')
        immediately = request.POST.get('immediately') == 'true'

        try:
            SubscriptionService.cancel_subscription(subscription, reason, immediately)

            if immediately:
                messages.success(request, "Subscription cancelled immediately.")
            else:
                messages.success(request, "Subscription will be cancelled at the end of the billing period.")
        except Exception as e:
            messages.error(request, str(e))

        return redirect('billing:subscription')


class ReactivateSubscriptionView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request):
        subscription = getattr(request.tenant, 'subscription', None)

        if not subscription:
            return redirect('billing:subscription')

        try:
            SubscriptionService.reactivate_subscription(subscription)
            messages.success(request, "Subscription reactivated.")
        except Exception as e:
            messages.error(request, str(e))

        return redirect('billing:subscription')


class ChangePlanView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request):
        subscription = getattr(request.tenant, 'subscription', None)
        new_plan_id = request.POST.get('plan_id')

        if not subscription:
            return redirect('billing:subscription')

        new_plan = get_object_or_404(Plan, pk=new_plan_id, is_active=True)

        try:
            SubscriptionService.change_plan(subscription, new_plan)
            messages.success(request, f"Plan changed to {new_plan.name}.")
        except Exception as e:
            messages.error(request, str(e))

        return redirect('billing:subscription')


class PaymentHistoryView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = PaymentHistory
    context_object_name = 'payments'
    template_name = 'billing/payment_history.html'
    paginate_by = 20

    def get_queryset(self):
        return PaymentHistory.objects.filter(organisation=self.request.tenant).order_by('-created_at')


class CreateCustomerPortalView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request):
        subscription = getattr(request.tenant, 'subscription', None)

        if not subscription or not subscription.stripe_customer_id:
            return JsonResponse({'error': 'No Stripe customer found'}, status=400)

        try:
            session = stripe.billing_portal.Session.create(
                customer=subscription.stripe_customer_id,
                return_url=request.build_absolute_uri(reverse('billing:subscription')),
            )
            return JsonResponse({'url': session.url})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(View):
    """Handle Stripe webhook events."""

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            return JsonResponse({'error': 'Invalid payload'}, status=400)
        except stripe.error.SignatureVerificationError:
            return JsonResponse({'error': 'Invalid signature'}, status=400)

        # Handle the event
        SubscriptionService.handle_webhook_event(event)

        return JsonResponse({'status': 'success'})


class BillingIndexView(LoginRequiredMixin, TenantContextMixin, TemplateView):
    template_name = 'billing/index.html'
