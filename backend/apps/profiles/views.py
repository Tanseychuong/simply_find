"""
The signed-in student's own profile, document vault and certificates.
Mounted at /api/profile/.
"""

from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents import services as vault
from apps.documents.credentials import check_credential
from apps.documents.models import Credential, Document, DocumentAccess
from apps.opportunities.models import Opportunity

from .eligibility import reasons_not_eligible
from .models import StudentProfile
from .serializers import (
    CredentialSerializer,
    DocumentAccessSerializer,
    DocumentSerializer,
    StudentProfileSerializer,
)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(StudentProfileSerializer(StudentProfile.for_user(request.user)).data)

    @transaction.atomic
    def patch(self, request):
        serializer = StudentProfileSerializer(StudentProfile.for_user(request.user), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DocumentsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_throttles(self):
        self.throttle_scope = "uploads" if self.request.method == "POST" else None
        return super().get_throttles() if self.throttle_scope else []

    def get(self, request):
        return Response(DocumentSerializer(Document.objects.filter(owner=request.user), many=True).data)

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"file": ["Choose a file to upload."]}, status=status.HTTP_400_BAD_REQUEST)
        document = vault.add_document(
            request.user, upload, kind=request.data.get("kind", ""), title=request.data.get("title", ""),
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class DocumentDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _document(self, request, pk):
        return get_object_or_404(Document, pk=pk, owner=request.user)

    def patch(self, request, pk):
        serializer = DocumentSerializer(self._document(request, pk), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        self._document(request, pk).delete()  # signals.py removes the stored file
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentFileView(APIView):
    """The owner downloads their own file. Companies only ever get the
    copy attached to an application (apps/companies/views.AnswerFileView)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk, owner=request.user)
        return vault.stream(document.file, document.original_filename or document.title)


class CredentialsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "uploads"

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    def get(self, request):
        return Response(CredentialSerializer(Credential.objects.filter(owner=request.user), many=True).data)

    def post(self, request):
        serializer = CredentialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential = vault.add_credential(request.user, serializer.validated_data)
        return Response(CredentialSerializer(credential).data, status=status.HTTP_201_CREATED)


class CredentialDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        get_object_or_404(Credential, pk=pk, owner=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CredentialCheckView(APIView):
    """Check again, e.g. after the issuer fixed the badge."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "uploads"

    def post(self, request, pk):
        credential = check_credential(get_object_or_404(Credential, pk=pk, owner=request.user))
        return Response(CredentialSerializer(credential).data)


class AccessLogView(APIView):
    """Who opened my documents: the hiring teams that read my applications."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entries = DocumentAccess.objects.filter(owner=request.user)[:200]
        return Response(DocumentAccessSerializer(entries, many=True).data)


class EligibilityView(APIView):
    """Can I apply for this role? Lets the page explain before the form."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, opportunity_id):
        opportunity = get_object_or_404(Opportunity, pk=opportunity_id)
        if not opportunity.is_visible_to(request.user):
            return Response(status=status.HTTP_404_NOT_FOUND)
        reasons = reasons_not_eligible(request.user, opportunity)
        return Response({"eligible": not reasons, "reasons": reasons})
