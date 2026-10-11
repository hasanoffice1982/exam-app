from django.conf import settings
from django.views.generic import TemplateView


class HomeView(TemplateView):
    """Public landing page: links only, no data."""

    template_name = "proctoring/home.html"

    def get_context_data(self, **kwargs):
        url = settings.STUDENT_DOWNLOAD_URL_MAC
        # only ever render real web links, never javascript: or data: URLs from a misconfigured env var
        safe = url if url.startswith(("https://", "http://")) else ""
        return {**super().get_context_data(**kwargs), "download_url": safe}
