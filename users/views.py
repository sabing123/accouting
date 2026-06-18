from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView, PasswordResetView, PasswordResetConfirmView
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import UpdateView, CreateView
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.views import View
from django.contrib import messages

from users.models import User, UserProfile, UserActivity
from users.forms import (
    CustomAuthenticationForm,
    UserRegistrationForm,
    UserProfileForm,
    PasswordChangeForm,
)


class LoginView(LoginView):
    form_class = CustomAuthenticationForm
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        from django.utils import timezone
        response = super().form_valid(form)
        # Log login activity
        UserActivity.objects.create(
            user=self.request.user,
            action=UserActivity.ActionType.LOGIN,
            ip_address=self.request.META.get('REMOTE_ADDR'),
            user_agent=self.request.META.get('HTTP_USER_AGENT', '')[:255]
        )
        self.request.user.last_login_ip = self.request.META.get('REMOTE_ADDR')
        self.request.user.save(update_fields=['last_login_ip'])
        return response

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('dashboard:index')


class LogoutView(LogoutView):
    next_page = reverse_lazy('account_login')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            UserActivity.objects.create(
                user=request.user,
                action=UserActivity.ActionType.LOGOUT,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        return super().dispatch(request, *args, **kwargs)


class UserRegistrationView(SuccessMessageMixin, CreateView):
    model = User
    form_class = UserRegistrationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('account_login')
    success_message = _("Account created! Please check your email to verify your account.")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard:index')
        return super().dispatch(request, *args, **kwargs)


class UserProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = 'users/profile.html'
    success_url = reverse_lazy('users:profile')
    success_message = _("Profile updated successfully!")

    def get_object(self):
        return self.request.user


class UserSettingsView(LoginRequiredMixin, View):
    template_name = 'users/settings.html'

    def get(self, request):
        password_form = PasswordChangeForm(request.user)
        return render(request, self.template_name, {
            'password_form': password_form,
            'user': request.user,
        })

    def post(self, request):
        password_form = PasswordChangeForm(request.user, request.POST)

        if password_form.is_valid():
            password_form.save()
            UserActivity.objects.create(
                user=request.user,
                action=UserActivity.ActionType.PASSWORD_CHANGE,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, _("Password changed successfully!"))
            return redirect('users:settings')

        return render(request, self.template_name, {
            'password_form': password_form,
            'user': request.user,
        })


class UserActivityListView(LoginRequiredMixin, View):
    template_name = 'users/activity.html'

    def get(self, request):
        activities = request.user.activities.all()[:50]
        return render(request, self.template_name, {
            'activities': activities,
        })


class VerifyEmailView(View):
    """Verify user's email using verification code."""

    def get(self, request, code):
        try:
            user = User.objects.get(verification_code=code)
            if user.verify_email(code):
                messages.success(request, _("Your email has been verified."))
                return redirect('account_login')
            else:
                messages.error(request, _("Invalid or expired verification link."))
        except User.DoesNotExist:
            messages.error(request, _("Invalid verification link."))

        return redirect('account_login')


class ResendVerificationView(View):
    """Resend verification email."""

    def post(self, request):
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            if not user.email_verified:
                code = user.generate_verification_code()
                # In production, send email

        except User.DoesNotExist:
            pass

        messages.success(request, _("If an account exists with that email, a verification link has been sent."))
        return redirect('account_login')
