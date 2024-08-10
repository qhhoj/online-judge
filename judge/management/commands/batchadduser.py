import csv
import secrets
import string

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from judge.models import Language, Profile

ALPHABET = string.ascii_letters + string.digits

html_header = """
<meta charset="UTF-8">

<style>
    .card {
        font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
        font-size: 28px;
        width: 800px;
        /*background-color: rgb(230, 230, 230);*/
        border: 3px solid #D20062;
        border-radius: 5px;
        padding: 20px;
        margin: 20px;
        break-inside: avoid;
    }

    .participantName {
        font-size: 30px;
        font-weight: bold;
    }

    code {
        color: #D20062;
        padding: 0 20px 0 0;
    }

    p {
        margin: 10px 10px 10px 0;
    }
</style>
"""

user_html_template = """
<div class="card ">
    <div class="participantName">{fullname}</div>

    <p>
        login:
        <code>{username}</code>
        password:
        <code>{password}</code>
    </p>

    <p>
        website:
        <code>{site_url}</code>
    </p>
</div>
"""


def generate_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def add_user(username, fullname, password):
    usr = User(username=username, first_name=fullname, is_active=True)
    usr.set_password(password)
    usr.save()

    profile = Profile(user=usr)
    profile.language = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
    profile.save()


class Command(BaseCommand):
    help = 'batch create users'

    def add_arguments(self, parser):
        parser.add_argument('input', help='csv file containing username and fullname')
        parser.add_argument('output', help='where to store output csv file')
        parser.add_argument('--html', dest='html', help='where to store print password html file')

    def handle(self, *args, **options):
        fin = open(options['input'], 'r', encoding='utf-8-sig')
        fout = open(options['output'], 'w', newline='')

        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=['username', 'fullname', 'password'])
        writer.writeheader()

        usr_list = []

        for row in reader:
            username = row['username']
            fullname = row['fullname']
            password = generate_password()

            add_user(username, fullname, password)

            usr_list.append((username, fullname, password))

            writer.writerow({
                'username': username,
                'fullname': fullname,
                'password': password,
            })

        if options['html'] is not None:
            fhtml = open(options['html'], 'w')
            fhtml.write(html_header)

            for username, fullname, password in usr_list:
                fhtml.write(user_html_template.format(
                    username=username,
                    fullname=fullname,
                    password=password,
                    site_url=settings.SITE_FULL_URL,
                ))
        fin.close()
        fout.close()
