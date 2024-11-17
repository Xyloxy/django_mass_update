from setuptools import setup, find_packages

setup(
    name="django-mass-update",
    version="0.1.0",
    author="Xyloxy",
    author_email="seba15833@gmail.com",
    description=("Make mass updates in though the Django Admin Interface"),
    license="MPL 2.0",
    license_files=("LICENSE.txt",),
    keywords="django admin",
    url="https://github.com/Xyloxy/django-mass-update",
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Development Status :: 1 - Planning",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 4",
        "Framework :: Django :: 5",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
    ],
    install_requires=["django"],
)
