from django.urls import path

from . import views

# Mounted at /api/profile/
urlpatterns = [
    path("", views.ProfileView.as_view(), name="profile"),
    path("documents/", views.DocumentsView.as_view(), name="profile-documents"),
    path("documents/<int:pk>/", views.DocumentDetailView.as_view(), name="profile-document"),
    path("documents/<int:pk>/file/", views.DocumentFileView.as_view(), name="profile-document-file"),
    path("credentials/", views.CredentialsView.as_view(), name="profile-credentials"),
    path("credentials/<int:pk>/", views.CredentialDetailView.as_view(), name="profile-credential"),
    path("credentials/<int:pk>/check/", views.CredentialCheckView.as_view(), name="profile-credential-check"),
    path("access-log/", views.AccessLogView.as_view(), name="profile-access-log"),
    path("eligibility/<int:opportunity_id>/", views.EligibilityView.as_view(), name="profile-eligibility"),
]
