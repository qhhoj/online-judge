import random
import string

from django.conf import settings
from django.db import models


class URL(models.Model):
    original_url = models.URLField(max_length=1000)
    short_code = models.CharField(max_length=20, unique=True)

    def save(self, *args, **kwargs):
        if not self.short_code:
            self.short_code = self.generate_short_code()
            while URL.objects.filter(short_code=self.short_code).exists():
                self.short_code = self.generate_short_code()
        super().save(*args, **kwargs)

    def generate_short_code(self):
        length = settings.SHORT_URL_LENGTH
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

    def __str__(self):
        return f'{self.short_code} -> {self.original_url}'
