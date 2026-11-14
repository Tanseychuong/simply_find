"""
Mounted at /api/drives/.
  mine/...            the company's drives and desk signups (hiring team, two-step sign-in)
  claim/              a student claims an account made for them at the desk
  <CODE>/             a drive's public page (what the QR code opens)
"""

import io

import segno
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import _signed_in
from apps.companies.views import _hiring_company
from apps.profiles.serializers import DocumentSerializer

from . import services
from .models import DriveRegistration, RecruitmentDrive
from .serializers import DriveSerializer, PublicDriveSerializer, RegistrationSerializer


def _drives(company):
    return RecruitmentDrive.objects.filter(company=company).annotate(
        registration_count=Count("registrations"),
        claimed_count=Count("registrations", filter=Q(registrations__claimed_at__isnull=False)),
    ).prefetch_related("opportunities")


def _my_drive(request, pk):
    company = _hiring_company(request)
    return company, get_object_or_404(_drives(company), pk=pk)


class MyDrivesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(DriveSerializer(_drives(_hiring_company(request)), many=True).data)

    def post(self, request):
        company = _hiring_company(request)
        serializer = DriveSerializer(data=request.data, company=company)
        serializer.is_valid(raise_exception=True)
        drive = serializer.save(company=company, created_by=request.user)
        return Response(DriveSerializer(_drives(company).get(pk=drive.pk)).data, status=status.HTTP_201_CREATED)


class MyDriveDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        return Response(DriveSerializer(_my_drive(request, pk)[1]).data)

    def patch(self, request, pk):
        company, drive = _my_drive(request, pk)
        serializer = DriveSerializer(drive, data=request.data, partial=True, company=company)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(DriveSerializer(_drives(company).get(pk=pk)).data)

    def delete(self, request, pk):
        _my_drive(request, pk)[1].delete()  # students' accounts stay; only the drive link goes
        return Response(status=status.HTTP_204_NO_CONTENT)


class DriveQrView(APIView):
    """A PNG QR code of the drive's public link, for posters and the desk."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        drive = _my_drive(request, pk)[1]
        buf = io.BytesIO()
        segno.make(drive.public_url, error="m").save(buf, kind="png", scale=10, border=2)
        response = HttpResponse(buf.getvalue(), content_type="image/png")
        response["Content-Disposition"] = f'inline; filename="drive-{drive.code}.png"'
        return response


class DriveStudentsView(APIView):
    """GET: who signed up at this drive. POST: sign a student up at the desk."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_throttles(self):
        self.throttle_scope = "desk_signups" if self.request.method == "POST" else None
        return super().get_throttles() if self.throttle_scope else []

    def get(self, request, pk):
        drive = _my_drive(request, pk)[1]
        registrations = drive.registrations.select_related("student", "registered_by")
        return Response(RegistrationSerializer(registrations, many=True).data)

    def post(self, request, pk):
        drive = _my_drive(request, pk)[1]
        if not drive.is_active:
            raise ValidationError({"detail": "This drive is closed."})
        registration = services.assisted_signup(drive, request.user, request.data)
        return Response(RegistrationSerializer(registration).data, status=status.HTTP_201_CREATED)


def _registration(request, pk, reg_pk):
    drive = _my_drive(request, pk)[1]
    return get_object_or_404(DriveRegistration.objects.select_related("student", "drive__company"),
                             pk=reg_pk, drive=drive)


class DeskDocumentView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "uploads"

    def post(self, request, pk, reg_pk):
        registration = _registration(request, pk, reg_pk)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Choose a file to upload."})
        document = services.desk_upload(registration, request.user, upload,
                                        request.data.get("kind", ""), request.data.get("title", ""))
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class ResendClaimView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "desk_signups"

    def post(self, request, pk, reg_pk):
        registration = _registration(request, pk, reg_pk)
        if registration.claimed_at:
            raise ValidationError({"detail": "The student already claimed this account."})
        services.send_claim_email(registration)
        return Response({"detail": "Sent."})


class ClaimView(APIView):
    """GET ?token= : what was set up for me. POST {token, password}: claim it."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def _registration(self, token):
        registration = services.registration_for_token(token)
        if registration is None:
            raise ValidationError({"token": "This link has expired or was already used."})
        return registration

    def get(self, request):
        registration = self._registration(request.query_params.get("token"))
        student = registration.student
        return Response({
            "name": student.name, "email": student.email,
            "drive": registration.drive.name, "company": registration.drive.company.name,
            "documents": DocumentSerializer(student.documents.all(), many=True).data,
        })

    def post(self, request):
        registration = self._registration(request.data.get("token"))
        student = services.claim(registration, str(request.data.get("password") or ""))
        return _signed_in(student)


class PublicDriveView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, code):
        drive = get_object_or_404(
            RecruitmentDrive.objects.select_related("company").prefetch_related("opportunities__company"),
            code=code.upper(), is_active=True, company__status="approved",
        )
        return Response(PublicDriveSerializer(drive, context={"request": request}).data)
