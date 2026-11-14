from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Exists, OuterRef, Q
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Opportunity, OpportunityCategory, SavedOpportunity
from .permissions import CanVerifyOpportunity, IsOwnerOrReadOnly
from .serializers import (
    OpportunityCategoryWithCountSerializer,
    OpportunityCreateSerializer,
    ModerationOpportunitySerializer,
    OpportunityDetailSerializer,
    OpportunityRejectSerializer,
    OpportunitySerializer,
    SavedOpportunitySerializer,
)
from .services import (
    approve_opportunity,
    landing_stats,
    list_visible_opportunities,
    reject_opportunity,
    submit_opportunity,
)


def _current_user(request):
    return request.user if request.user.is_authenticated else None


class OpportunityCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Public, read-only — categories are admin-managed via /admin/.
    Each one carries `live_count` (open listings this visitor can see),
    ordered busiest-first, which is what the landing page sections use."""

    serializer_class = OpportunityCategoryWithCountSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None  # a short, admin-curated list — always return it whole

    def get_queryset(self):
        user = _current_user(self.request)
        live = Opportunity.visibility_q(user, prefix="opportunities__") & Opportunity.open_q(prefix="opportunities__")
        return (
            OpportunityCategory.objects.filter(is_active=True)
            .annotate(live_count=Count("opportunities", filter=live, distinct=True))
            .order_by("-live_count", "name")
        )


class OpportunityViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "organization", "description", "location"]
    # ?ordering=application_deadline -> closing soonest first (no-deadline last)
    ordering_fields = ["published_at", "application_deadline"]

    def get_serializer_class(self):
        if self.action == "create":
            return OpportunityCreateSerializer
        if self.action == "retrieve":
            return OpportunityDetailSerializer
        return OpportunitySerializer

    def get_queryset(self):
        user = _current_user(self.request)

        if self.action in ("update", "partial_update", "destroy"):
            # Editing only ever allowed on your own still-pending submissions.
            # Company jobs are edited through /api/companies/me/jobs/<id>/ instead,
            # which applies the re-review and requirement rules.
            return Opportunity.objects.filter(posted_by=user, status=Opportunity.Status.PENDING, company__isnull=True)

        if self.action in ("approve", "reject"):
            # CanVerifyOpportunity already restricts who reaches this action
            # at all — a moderator specifically needs to look up PENDING
            # (not-yet-visible) items, which the visibility filter below
            # would otherwise exclude.
            return Opportunity.objects.all()

        if self.action == "retrieve":
            # Visible under the normal rule (including ones past their
            # deadline, so saved links keep working), OR it's your own
            # submission regardless of moderation status.
            visible_ids = list_visible_opportunities(user, include_expired=True).values("pk")
            if user:
                # Your own submissions, in any status. A company job only
                # while you're still on that company's team.
                from apps.companies.models import Company
                my_companies = Company.objects.filter(memberships__user=user).values("pk")
                mine = Q(posted_by=user) & (Q(company=None) | Q(company__in=my_companies))
                qs = Opportunity.objects.filter(Q(pk__in=visible_ids) | mine)
            else:
                qs = Opportunity.objects.filter(pk__in=visible_ids)
            return self._with_saved_flag(qs.select_related("category", "posted_by", "company"), user)

        # list, and the default for any other action
        category_slug = self.request.query_params.get("category")
        include_expired = self.request.query_params.get("include_expired") == "true"
        qs = list_visible_opportunities(user, category_slug=category_slug, include_expired=include_expired)
        return self._with_saved_flag(qs.defer("sections"), user)  # only the detail view shows them

    @staticmethod
    def _with_saved_flag(queryset, user):
        if not user:
            return queryset
        saved = SavedOpportunity.objects.filter(user=user, opportunity=OuterRef("pk"))
        return queryset.annotate(user_has_saved=Exists(saved))

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def perform_create(self, serializer):
        opportunity = submit_opportunity(self.request.user, serializer.validated_data)
        serializer.instance = opportunity

    # --- Public landing data ------------------------------------------------

    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny])
    def stats(self, request):
        user = _current_user(request)
        premium = settings.PREMIUM_ENABLED
        tier = "premium" if not premium or (user and user.is_premium_active()) else "free"
        key = f"opportunities:landing-stats:{tier}"
        data = cache.get(key)
        if data is None:
            data = landing_stats(user)
            cache.set(key, data, settings.LANDING_STATS_CACHE_SECONDS)
        return Response({
            **data,
            "premium_enabled": premium,
            "early_access_hours": settings.EARLY_ACCESS_HOURS if premium else 0,
        })

    # --- Moderation actions -------------------------------------------------

    @action(detail=False, methods=["get"], permission_classes=[CanVerifyOpportunity])
    def pending(self, request):
        """The moderation queue, API-side — the admin panel's bulk actions
        cover this too; this exists for the custom moderator UI."""
        queryset = (
            Opportunity.objects.filter(status=Opportunity.Status.PENDING)
            .select_related("category", "posted_by", "company")
            .prefetch_related("requirements")
            .order_by("submitted_at", "pk")
        )
        page = self.paginate_queryset(queryset)
        # Moderators review the full write-up, sections included.
        serializer = ModerationOpportunitySerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[CanVerifyOpportunity])
    def approve(self, request, pk=None):
        opportunity = self.get_object()
        approve_opportunity(opportunity, request.user)
        return Response(OpportunitySerializer(opportunity, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], permission_classes=[CanVerifyOpportunity])
    def reject(self, request, pk=None):
        serializer = OpportunityRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        opportunity = self.get_object()
        reject_opportunity(opportunity, request.user, serializer.validated_data["reason"])
        return Response(OpportunitySerializer(opportunity, context=self.get_serializer_context()).data)

    # --- Save / unsave -------------------------------------------------------

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def save(self, request, pk=None):
        opportunity = self.get_object()
        SavedOpportunity.objects.get_or_create(user=request.user, opportunity=opportunity)
        return Response(status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], permission_classes=[permissions.IsAuthenticated])
    def unsave(self, request, pk=None):
        SavedOpportunity.objects.filter(user=request.user, opportunity_id=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def saved(self, request):
        queryset = SavedOpportunity.objects.filter(user=request.user).select_related(
            "opportunity", "opportunity__category", "opportunity__posted_by", "opportunity__company"
        )
        page = self.paginate_queryset(queryset)
        serializer = SavedOpportunitySerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)
