from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import client_country, client_ip, is_bot, record_page_view


class PageViewHitSerializer(serializers.Serializer):
    visitor_id = serializers.UUIDField()
    path = serializers.CharField(max_length=2000)
    referrer = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    utm_source = serializers.CharField(max_length=200, required=False, allow_blank=True)


class PageViewHitView(APIView):
    """The frontend reports each page it shows. Always answers 204 with no
    body, so a tracking hiccup never surfaces to the visitor."""

    permission_classes = (permissions.AllowAny,)
    throttle_scope = "analytics"

    def post(self, request):
        serializer = PageViewHitSerializer(data=request.data)
        if serializer.is_valid() and not is_bot(request.META.get("HTTP_USER_AGENT", "")):
            user = request.user if request.user.is_authenticated else None
            record_page_view(
                **serializer.validated_data, user=user,
                ip_address=client_ip(request.META), country=client_country(request.META),
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
