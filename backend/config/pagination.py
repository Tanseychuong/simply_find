from django.conf import settings
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """DRF's page-number pagination, plus a client-chosen ?page_size=
    (e.g. the landing page asks for 4 per category) that can never exceed
    MAX_PAGE_SIZE, so nobody can request the whole table in one call."""

    page_size_query_param = "page_size"
    max_page_size = settings.MAX_PAGE_SIZE
