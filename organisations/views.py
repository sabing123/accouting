from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, View
from django.views.generic.edit import FormView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

from organisations.models import Organisation, OrganisationMembership, OrganisationInvitation, OrganisationDomain
from organisations.forms import OrganisationCreateForm, OrganisationUpdateForm, MemberInviteForm, MemberRoleForm
from organisations.services import OrganisationService


class OrganisationListView(LoginRequiredMixin, ListView):
    model = Organisation
    context_object_name = 'organisations'
    template_name = 'organisations/list.html'

    def get_queryset(self):
        return OrganisationService.get_user_organisations(self.request.user)


class OrganisationCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Organisation
    form_class = OrganisationCreateForm
    template_name = 'organisations/create.html'
    success_url = reverse_lazy('dashboard:index')
    success_message = _("Organisation '%(name)s' created successfully!")

    def form_valid(self, form):
        response = super().form_valid(form)
        OrganisationService.create_organisation(
            name=form.cleaned_data['name'],
            user=self.request.user,
            industry=form.cleaned_data.get('industry', ''),
            country=form.cleaned_data.get('country', 'US'),
            type=form.cleaned_data.get('type', Organisation.Type.LLC),
            base_currency=form.cleaned_data.get('base_currency', 'USD'),
        )
        return response


class OrganisationDetailView(LoginRequiredMixin, DetailView):
    model = Organisation
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    context_object_name = 'organisation'
    template_name = 'organisations/detail.html'

    def get_queryset(self):
        return Organisation.objects.filter(
            memberships__user=self.request.user
        )


class OrganisationSettingsView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Organisation
    form_class = OrganisationUpdateForm
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    template_name = 'organisations/settings.html'
    success_message = _("Organisation settings updated successfully!")

    def get_queryset(self):
        return Organisation.objects.filter(
            memberships__user=self.request.user
        )

    def get_success_url(self):
        return reverse_lazy('organisations:settings', kwargs={'slug': self.object.slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['domains'] = self.object.domains.all()
        return context


class MemberListView(LoginRequiredMixin, ListView):
    model = OrganisationMembership
    context_object_name = 'memberships'
    template_name = 'organisations/members.html'

    def get_queryset(self):
        self.organisation = get_object_or_404(
            Organisation,
            slug=self.kwargs['slug'],
            memberships__user=self.request.user
        )
        return self.organisation.memberships.select_related('user').all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organisation'] = self.organisation
        context['can_invite'] = self.organisation.memberships.filter(
            user=self.request.user,
            role__in=[OrganisationMembership.Role.OWNER, OrganisationMembership.Role.ADMIN]
        ).exists()
        return context


class MemberInviteView(LoginRequiredMixin, SuccessMessageMixin, FormView):
    form_class = MemberInviteForm
    template_name = 'organisations/member_invite.html'
    success_message = _("Invitation sent to %(email)s!")

    def dispatch(self, request, *args, **kwargs):
        self.organisation = get_object_or_404(
            Organisation,
            slug=kwargs['slug'],
            memberships__user=request.user,
            memberships__role__in=[
                OrganisationMembership.Role.OWNER,
                OrganisationMembership.Role.ADMIN
            ]
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        OrganisationService.invite_member(
            org=self.organisation,
            email=form.cleaned_data['email'],
            role=form.cleaned_data['role'],
            invited_by=self.request.user
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('organisations:members', kwargs={'slug': self.organisation.slug})


class MemberRemoveView(LoginRequiredMixin, View):
    def post(self, request, slug, user_id):
        organisation = get_object_or_404(
            Organisation,
            slug=slug,
            memberships__user=request.user,
            memberships__role__in=[
                OrganisationMembership.Role.OWNER,
                OrganisationMembership.Role.ADMIN
            ]
        )

        try:
            OrganisationService.remove_member(organisation, user_id, request.user)
            messages.success(request, _("Member removed successfully."))
        except ValueError as e:
            messages.error(request, str(e))

        return redirect('organisations:members', slug=slug)


class MemberRoleUpdateView(LoginRequiredMixin, FormView):
    form_class = MemberRoleForm

    def dispatch(self, request, *args, **kwargs):
        self.organisation = get_object_or_404(
            Organisation,
            slug=kwargs['slug'],
            memberships__user=request.user,
            memberships__role=OrganisationMembership.Role.OWNER
        )
        self.target_user_id = kwargs['user_id']
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        OrganisationService.update_member_role(
            org=self.organisation,
            user_id=self.target_user_id,
            new_role=form.cleaned_data['role'],
            updated_by=self.request.user
        )
        messages.success(self.request, _("Role updated successfully."))
        return redirect('organisations:members', slug=self.organisation.slug)


class InvitationAcceptView(LoginRequiredMixin, View):
    def get(self, request, token):
        try:
            membership = OrganisationService.accept_invitation(token, request.user)
            messages.success(request, _("You have joined %(org)s!") % {'org': membership.organisation.name})
            return redirect('organisations:list')
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('dashboard:index')


class InvitationDeclineView(LoginRequiredMixin, View):
    def post(self, request, token):
        from organisations.models import OrganisationInvitation

        invitation = get_object_or_404(OrganisationInvitation, token=token)
        invitation.status = OrganisationInvitation.Status.DECLINED
        invitation.save()
        messages.info(request, _("You have declined the invitation."))
        return redirect('organisations:list')


class OrganisationSwitchView(LoginRequiredMixin, View):
    def post(self, request, slug):
        organisation = get_object_or_404(
            Organisation,
            slug=slug,
            memberships__user=request.user
        )
        OrganisationService.switch_organisation(request.user, organisation)
        request.session['current_organisation_slug'] = slug
        messages.success(request, _("Switched to %(org)s") % {'org': organisation.name})
        return redirect('dashboard:index')


class DomainCreateView(LoginRequiredMixin, CreateView):
    model = OrganisationDomain
    fields = ['domain']
    template_name = 'organisations/partials/domain_form.html'

    def form_valid(self, form):
        organisation = get_object_or_404(
            Organisation,
            memberships__user=self.request.user,
            memberships__role=OrganisationMembership.Role.OWNER
        )
        if organisation.pk:
            form.instance.organisation = organisation
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('organisations:settings', kwargs={'slug': self.object.organisation.slug})


class DomainDeleteView(LoginRequiredMixin, DeleteView):
    model = OrganisationDomain
    context_object_name = 'domain'

    def get_success_url(self):
        return reverse_lazy('organisations:settings', kwargs={'slug': self.object.organisation.slug})

    def get_queryset(self):
        return OrganisationDomain.objects.filter(
            organisation__memberships__user=self.request.user,
            organisation__memberships__role=OrganisationMembership.Role.OWNER
        )
