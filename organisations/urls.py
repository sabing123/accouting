from django.urls import path
from organisations import views

app_name = 'organisations'

urlpatterns = [
    # Organisation management
    path('', views.OrganisationListView.as_view(), name='list'),
    path('create/', views.OrganisationCreateView.as_view(), name='create'),
    path('<slug:slug>/', views.OrganisationDetailView.as_view(), name='detail'),
    path('<slug:slug>/settings/', views.OrganisationSettingsView.as_view(), name='settings'),
    path('<slug:slug>/members/', views.MemberListView.as_view(), name='members'),
    path('<slug:slug>/members/invite/', views.MemberInviteView.as_view(), name='member-invite'),
    path('<slug:slug>/members/<uuid:user_id>/remove/', views.MemberRemoveView.as_view(), name='member-remove'),
    path('<slug:slug>/members/<uuid:user_id>/role/', views.MemberRoleUpdateView.as_view(), name='member-role-update'),

    # Invitation handling
    path('invitations/<str:token>/accept/', views.InvitationAcceptView.as_view(), name='invitation-accept'),
    path('invitations/<str:token>/decline/', views.InvitationDeclineView.as_view(), name='invitation-decline'),

    # Organisation switching
    path('switch/<slug:slug>/', views.OrganisationSwitchView.as_view(), name='switch'),

    # HTMX endpoints
    path('htmx/domains/', views.DomainCreateView.as_view(), name='domain-create'),
    path('htmx/domains/<uuid:pk>/delete/', views.DomainDeleteView.as_view(), name='domain-delete'),
]
