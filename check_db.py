import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()
from account.models import Service
print("Services:")
for s in Service.objects.all():
    print(f"- {s.slug}: show_on_homepage={s.show_on_homepage}, sort_order={s.sort_order}")
