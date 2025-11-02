from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden
)
from django.shortcuts import render

from judge.forms import URLForm
from judge.models import URL


def shorten_url(request):
    if request.method == 'POST':
        form = URLForm(request.POST)
        if form.is_valid():
            url = form.save()
            return render(request, 'shortener/success.html', {'context': url})
        else:
            return HttpResponseBadRequest('Invalid Form')
    else:
        form = URLForm()
        return render(request, 'shortener/index.html', {'form': form})


def redirect_url(request, short_code):
    try:
        url = URL.objects.get(short_code=short_code)
        return render(request, 'shortener/wait_redirect.html', {'original_url': url.original_url})
    except URL.DoesNotExist:
        return HttpResponseForbidden('URL not exist')
