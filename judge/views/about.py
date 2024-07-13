from django.conf import settings
from django.views.generic import TemplateView


class AboutView(TemplateView):
    template_name = 'about.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['TEAM_MEMBERS'] = settings.TEAM_MEMBERS
        return context
