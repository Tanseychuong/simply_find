from django.urls import path

from . import views

# Mounted at /api/drives/. Codes are upper case, so they never clash with "mine" or "claim".
urlpatterns = [
    path("mine/", views.MyDrivesView.as_view(), name="drives-mine"),
    path("mine/<int:pk>/", views.MyDriveDetailView.as_view(), name="drive-mine"),
    path("mine/<int:pk>/qr.png", views.DriveQrView.as_view(), name="drive-qr"),
    path("mine/<int:pk>/students/", views.DriveStudentsView.as_view(), name="drive-students"),
    path("mine/<int:pk>/students/<int:reg_pk>/documents/", views.DeskDocumentView.as_view(), name="drive-desk-document"),
    path("mine/<int:pk>/students/<int:reg_pk>/resend/", views.ResendClaimView.as_view(), name="drive-resend-claim"),
    path("claim/", views.ClaimView.as_view(), name="drive-claim"),
    path("<str:code>/", views.PublicDriveView.as_view(), name="drive-public"),
]
