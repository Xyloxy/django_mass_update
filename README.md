
# Installation
1. `pip install django-mass-update`
2. Add `massupdate` to `INSTALLED_APPS`
3. Add `path('admin/', include('massupdate.urls'))`, to urls.py before admin.site.urls line

# Important mentions
This project was heavily influenced by `burke-software`'s `django-mass-edit`. This project does not reuse any code from it, but this project would not have existed otherwise.

https://github.com/burke-software/django-mass-edit/
