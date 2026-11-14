from django.urls import path

from . import views

# Mounted at /api/companies/. Fixed paths come before <slug> (models.RESERVED_SLUGS).
urlpatterns = [
    path("", views.CompanyRegisterView.as_view(), name="company-register"),
    path("me/", views.MyCompanyView.as_view(), name="company-me"),
    path("me/logo/", views.CompanyLogoView.as_view(), name="company-logo"),
    path("me/jobs/", views.MyJobsView.as_view(), name="company-jobs"),
    path("me/jobs/<int:pk>/", views.MyJobDetailView.as_view(), name="company-job"),
    path("me/jobs/<int:pk>/close/", views.CloseJobView.as_view(), name="company-job-close"),
    path("me/jobs/<int:pk>/applications/", views.JobApplicationsView.as_view(), name="company-job-applications"),
    path("me/jobs/<int:pk>/applications/bulk/", views.JobApplicationsBulkView.as_view(), name="company-job-applications-bulk"),
    path("me/jobs/<int:pk>/applications/export.csv", views.JobApplicationsCsvView.as_view(), name="company-job-applications-csv"),
    path("me/jobs/<int:pk>/applications/print/", views.JobApplicationsPrintView.as_view(), name="company-job-applications-print"),
    path("me/applications/<int:pk>/", views.CompanyApplicationUpdateView.as_view(), name="company-application"),
    path("me/team/", views.TeamView.as_view(), name="company-team"),
    path("me/team/invitations/", views.TeamInvitationsView.as_view(), name="company-team-invitations"),
    path("me/team/invitations/<int:pk>/", views.TeamInvitationDetailView.as_view(), name="company-team-invitation"),
    path("me/team/members/<int:pk>/", views.TeamMemberDetailView.as_view(), name="company-team-member"),
    path("invitations/<str:token>/", views.InvitationByTokenView.as_view(), name="company-invitation"),
    path("review/", views.CompanyReviewListView.as_view(), name="company-review-list"),
    path("review/<int:pk>/", views.CompanyReviewActionView.as_view(), name="company-review-action"),
    path("<slug:slug>/", views.CompanyPublicView.as_view(), name="company-public"),
]

# Mounted at /api/applications/
application_urlpatterns = [
    path("", views.MyApplicationsView.as_view(), name="applications"),
    path("<int:pk>/withdraw/", views.WithdrawApplicationView.as_view(), name="application-withdraw"),
    path("answers/<int:pk>/file/", views.AnswerFileView.as_view(), name="application-answer-file"),
]
