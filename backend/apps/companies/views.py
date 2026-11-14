"""
Company API.

  /api/companies/                      POST  register the signed-in user's company (pending approval)
  /api/companies/me/                   GET/PATCH  your company profile + review status
  /api/companies/me/logo/              POST  upload a logo image (multipart `logo`)
  /api/companies/me/jobs/              GET/POST   your jobs (every status) / post a job
  /api/companies/me/jobs/<id>/         GET/PATCH  one job / edit it (re-reviewed unless verified)
  /api/companies/me/jobs/<id>/close/   POST  stop taking applications now
  /api/companies/me/jobs/<id>/applications/  GET  applications to one job
  /api/companies/me/applications/<id>/ PATCH  move an application along (status, private note)
  /api/companies/me/team/              GET   members, open invitations, your role
  /api/companies/me/team/invitations/  POST  invite someone by email (owners, admins)
  /api/companies/me/team/invitations/<id>/  DELETE  revoke an invitation
  /api/companies/me/team/members/<id>/ PATCH  change a role (owners) / DELETE remove or leave
  /api/companies/invitations/<token>/  GET   what an invitation is for / POST accept it

Roles (CompanyMembership.Role): every member works on jobs and applicants;
owners and admins also edit the company profile and invite people; only
owners change roles. A company always keeps at least one owner.
  /api/companies/review/               GET   moderators: companies by ?status= (default pending)
  /api/companies/review/<id>/          POST  moderators: approve/reject/suspend; admins: verify/unverify
  /api/companies/<slug>/               GET   public profile + its live jobs (approved companies only)

  /api/applications/                   GET  your own applications / POST apply (multipart)
  /api/applications/<id>/withdraw/     POST
  /api/applications/answers/<id>/file/ GET  download an uploaded file (applicant or hiring company only)
"""

from pathlib import Path

from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.opportunities.models import Opportunity
from apps.opportunities.permissions import CanVerifyOpportunity
from apps.opportunities.serializers import OpportunitySerializer
from apps.opportunities.services import list_visible_opportunities
from apps.opportunities.views import OpportunityViewSet

from .models import Application, ApplicationAnswer, Company, CompanyInvitation, CompanyMembership
from .serializers import (
    CompanyApplicationSerializer,
    CompanyInvitationSerializer,
    InviteSerializer,
    TeamMemberSerializer,
    CompanyJobCreateSerializer,
    CompanyJobSerializer,
    CompanyJobUpdateSerializer,
    CompanyOwnerSerializer,
    CompanyPublicSerializer,
    CompanyReviewActionSerializer,
    CompanyReviewSerializer,
    MyApplicationSerializer,
)
from .services import (
    accept_invitation,
    change_role,
    invite_member,
    post_job,
    remove_member,
    revoke_invitation,
    register_company,
    review_company,
    set_application_status,
    submit_application,
    update_company,
    update_job,
    withdraw_application,
)

MAX_LOGO_BYTES = 2 * 1024 * 1024
LOGO_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _membership(user) -> CompanyMembership:
    membership = CompanyMembership.for_user(user)
    if membership is None:
        raise NotFound("You're not on a company's team yet.")
    return membership


def _my_company(user) -> Company:
    return _membership(user).company


def _profile_manager(user) -> CompanyMembership:
    membership = _membership(user)
    if not membership.can_manage:
        raise PermissionDenied("Only owners and admins can change the company profile.")
    return membership


def _owner_view(company, membership):
    data = CompanyOwnerSerializer(company).data
    data["my_role"] = membership.role
    data["my_permissions"] = membership.permissions()
    return data


def _hiring_company(user) -> Company:
    """For endpoints that expose applicants' personal data: only an approved
    company may read or act on applications. A suspended or rejected company
    keeps its records (restored if reinstated) but can't open them."""
    company = _my_company(user)
    if company.status != Company.Status.APPROVED:
        raise PermissionDenied("Applications are unavailable while your company account is not approved.")
    return company


def _job_queryset(company):
    return (
        Opportunity.objects.filter(company=company)
        .select_related("category")
        .prefetch_related("requirements")
        .annotate(application_count=Count("applications", filter=~Q(applications__status="withdrawn")))
    )


class CompanyRegisterView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "company_signup"

    def post(self, request):
        serializer = CompanyOwnerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = register_company(request.user, serializer.validated_data)
        owner = CompanyMembership(company=company, user=request.user, role=CompanyMembership.Role.OWNER)
        return Response(_owner_view(company, owner), status=status.HTTP_201_CREATED)


class MyCompanyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = _membership(request.user)
        return Response(_owner_view(membership.company, membership))

    def patch(self, request):
        membership = _profile_manager(request.user)
        serializer = CompanyOwnerSerializer(membership.company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        company = update_company(membership.company, serializer.validated_data)
        return Response(_owner_view(company, membership))


class CompanyLogoView(APIView):
    """Logos are public by nature, so they go to the public media storage
    and the resulting URL is saved as the company's logo_url."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "uploads"

    def post(self, request):
        from django.core.files.storage import default_storage
        from PIL import Image, UnidentifiedImageError

        membership = _profile_manager(request.user)
        company = membership.company
        upload = request.FILES.get("logo")
        if not upload:
            raise ValidationError({"logo": "Choose an image to upload."})
        suffix = Path(upload.name).suffix.lower()
        if suffix not in LOGO_SUFFIXES or upload.size > MAX_LOGO_BYTES:
            raise ValidationError({"logo": "Upload a PNG, JPG or WebP image up to 2 MB."})
        try:
            Image.open(upload).verify()  # reject files that only pretend to be images
        except (UnidentifiedImageError, OSError):
            raise ValidationError({"logo": "That file isn't a valid image."})
        upload.seek(0)
        name = default_storage.save(f"company_logos/{company.slug}{suffix}", upload)
        url = default_storage.url(name)
        company.logo_url = url if url.startswith("http") else request.build_absolute_uri(url)
        company.save(update_fields=["logo_url", "updated_at"])
        return Response(_owner_view(company, membership))


class MyJobsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        self.throttle_scope = "company_jobs" if self.request.method == "POST" else None
        return super().get_throttles() if self.throttle_scope else []

    def get(self, request):
        jobs = _job_queryset(_my_company(request.user)).order_by("-submitted_at")
        return Response(CompanyJobSerializer(jobs, many=True).data)

    def post(self, request):
        company = _my_company(request.user)
        serializer = CompanyJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        requirements = data.pop("requirements", [])
        job = post_job(company, request.user, data, requirements)
        return Response(CompanyJobSerializer(_job_queryset(company).get(pk=job.pk)).data, status=status.HTTP_201_CREATED)


class MyJobDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        self.throttle_scope = "company_jobs" if self.request.method == "PATCH" else None
        return super().get_throttles() if self.throttle_scope else []

    def get(self, request, pk):
        job = get_object_or_404(_job_queryset(_my_company(request.user)), pk=pk)
        return Response(CompanyJobSerializer(job).data)

    def patch(self, request, pk):
        company = _my_company(request.user)
        job = get_object_or_404(Opportunity, pk=pk, company=company)
        serializer = CompanyJobUpdateSerializer(job, data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        requirements = data.pop("requirements", None)
        update_job(job, company, data, requirements)
        return Response(CompanyJobSerializer(_job_queryset(company).get(pk=pk)).data)


class CloseJobView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        company = _my_company(request.user)
        job = get_object_or_404(Opportunity, pk=pk, company=company)
        job.application_deadline = timezone.now()
        job.save(update_fields=["application_deadline"])
        return Response(CompanyJobSerializer(_job_queryset(company).get(pk=pk)).data)


class JobApplicationsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CompanyApplicationSerializer

    def get_queryset(self):
        job = get_object_or_404(Opportunity, pk=self.kwargs["pk"], company=_hiring_company(self.request.user))
        return (
            job.applications.exclude(status=Application.Status.WITHDRAWN)
            .select_related("applicant", "opportunity")
            .prefetch_related("answers")
        )


class CompanyApplicationUpdateView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CompanyApplicationSerializer
    http_method_names = ["patch"]

    def get_queryset(self):
        return (
            Application.objects.filter(opportunity__company=_hiring_company(self.request.user))
            .exclude(status=Application.Status.WITHDRAWN)
            .select_related("applicant", "opportunity__company")
        )

    def perform_update(self, serializer):
        set_application_status(serializer.instance, serializer.validated_data)


class TeamView(APIView):
    """Everyone on the team can see who else is on it."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = _membership(request.user)
        company = membership.company
        members = company.memberships.select_related("user", "invited_by")
        invitations = (company.invitations.filter(accepted_at=None, expires_at__gt=timezone.now())
                       .select_related("invited_by") if membership.can_manage else [])
        return Response({
            "my_role": membership.role,
            "my_permissions": membership.permissions(),
            "my_membership_id": membership.pk,
            "members": TeamMemberSerializer(members, many=True, context={"request": request}).data,
            "invitations": CompanyInvitationSerializer(invitations, many=True).data,
        })


class TeamInvitationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "company_invites"

    def post(self, request):
        membership = _membership(request.user)
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, _token = invite_member(membership.company, membership, **serializer.validated_data)
        return Response(CompanyInvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class TeamInvitationDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        membership = _membership(request.user)
        invitation = get_object_or_404(CompanyInvitation, pk=pk, company=membership.company, accepted_at=None)
        revoke_invitation(invitation, membership)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamMemberDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _target(self, request, pk):
        membership = _membership(request.user)
        target = get_object_or_404(CompanyMembership.objects.select_related("user", "company"),
                                   pk=pk, company=membership.company)
        return membership, target

    def patch(self, request, pk):
        membership, target = self._target(request, pk)
        target = change_role(target, membership, request.data.get("role"))
        return Response(TeamMemberSerializer(target, context={"request": request}).data)

    def delete(self, request, pk):
        membership, target = self._target(request, pk)
        remove_member(target, membership)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationByTokenView(APIView):
    """GET: what the emailed link is for (company, role, address), so the
    page can say who to sign in as. POST (signed in): accept it."""

    throttle_scope = "auth"

    def get_permissions(self):
        return [permissions.AllowAny()] if self.request.method == "GET" else [permissions.IsAuthenticated()]

    def _invitation(self, token):
        invitation = CompanyInvitation.find(token)
        if invitation is None:
            raise NotFound("This invitation link isn't valid. Ask for a new one.")
        return invitation

    def get(self, request, token):
        invitation = self._invitation(token)
        return Response({
            "company": {"name": invitation.company.name, "slug": invitation.company.slug,
                        "logo_url": invitation.company.logo_url},
            "role": invitation.role,
            "email": invitation.email,
            "invited_by": invitation.invited_by.name if invitation.invited_by else None,
            "is_pending": invitation.is_pending,
        })

    def post(self, request, token):
        membership = accept_invitation(self._invitation(token), request.user)
        return Response(_owner_view(membership.company, membership))


class CompanyReviewListView(generics.ListAPIView):
    permission_classes = [CanVerifyOpportunity]
    serializer_class = CompanyReviewSerializer

    def get_queryset(self):
        wanted = self.request.query_params.get("status", Company.Status.PENDING)
        qs = Company.objects.select_related("created_by").annotate(member_count=Count("memberships")).order_by("created_at")
        return qs if wanted == "all" else qs.filter(status=wanted)


class CompanyReviewActionView(APIView):
    """Moderators approve, reject and suspend. The verified badge is a public
    statement about a company's identity, so only admins grant or remove it."""

    permission_classes = [CanVerifyOpportunity]

    def post(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        serializer = CompanyReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        if action in ("verify", "unverify") and not request.user.is_superuser:
            raise PermissionDenied("Only administrators can change the verified badge.")
        review_company(company, request.user, action, serializer.validated_data.get("reason", ""))
        return Response(CompanyReviewSerializer(company).data)


class CompanyPublicView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        company = get_object_or_404(Company, slug=slug, status=Company.Status.APPROVED)
        user = request.user if request.user.is_authenticated else None
        # Same query shape as the feed: saved flag in one query, no sections.
        jobs = OpportunityViewSet._with_saved_flag(
            list_visible_opportunities(user).filter(company=company).defer("sections"), user,
        )[:50]
        return Response({
            "company": CompanyPublicSerializer(company).data,
            "jobs": OpportunitySerializer(jobs, many=True, context={"request": request}).data,
        })


class MyApplicationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_throttles(self):
        self.throttle_scope = "applications" if self.request.method == "POST" else None
        return super().get_throttles() if self.throttle_scope else []

    def get(self, request):
        apps = (
            Application.objects.filter(applicant=request.user)
            .select_related("opportunity", "opportunity__company")
            .prefetch_related("answers")
        )
        return Response(MyApplicationSerializer(apps, many=True).data)

    def post(self, request):
        try:
            opportunity_id = int(request.data.get("opportunity"))
        except (TypeError, ValueError):
            raise ValidationError({"opportunity": "Which job are you applying to?"})
        opportunity = get_object_or_404(Opportunity.objects.select_related("company"), pk=opportunity_id)
        application = submit_application(request.user, opportunity, request.data, request.FILES)
        return Response(MyApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


class WithdrawApplicationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        application = get_object_or_404(Application, pk=pk, applicant=request.user)
        withdraw_application(application)
        return Response(MyApplicationSerializer(application).data)


class AnswerFileView(APIView):
    """Streams an uploaded file to the applicant or the hiring company only.
    Storage URLs are never exposed."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        # A subquery, not a join across memberships: a join returns one row
        # per team member and .get() would fail once a team has two people.
        my_hiring_companies = Company.objects.filter(
            memberships__user=request.user, status=Company.Status.APPROVED,
        ).values("pk")
        answer = get_object_or_404(
            ApplicationAnswer.objects.filter(
                Q(application__applicant=request.user)
                | Q(application__opportunity__company__in=my_hiring_companies,
                    application__status__in=[
                    s for s in Application.Status.values if s != Application.Status.WITHDRAWN
                ])
            ),
            pk=pk,
        )
        if not answer.file:
            raise Http404
        response = FileResponse(
            answer.file.open("rb"), as_attachment=True, filename=answer.original_filename or "attachment",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
