from django.views.generic import TemplateView


def FlatPageViewGenerator(name):
    class CurrentView(TemplateView):
        template_name = name
    return CurrentView
