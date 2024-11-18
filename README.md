
# Installation
1. `pip install django-mass-update`
2. Add `mass_update` to `INSTALLED_APPS`
3. Add `path('admin/', include('mass_update.urls'))`, to urls.py before admin.site.urls

# Important mentions
This project was heavily influenced by `burke-software`'s `django-mass-edit`. This project does not reuse any code from it, though it is heavily inspired by it.

https://github.com/burke-software/django-mass-edit/
