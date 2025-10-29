from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'teams', views.TeamViewSet, basename='team')


urlpatterns = [  
    path('', include(router.urls)),
    path('teams/invitations/pending/',
         views.MyTeamInvitationsView.as_view(),
         name='team-pending-invites'),

    path('teams/invitations/<int:membership_id>/respond/',
         views.RespondToTeamInvitationView.as_view(),
         name='team-respond-invite'),
]
