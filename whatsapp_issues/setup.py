from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in whatsapp_issues/__init__.py
from whatsapp_issues import __version__ as version

setup(
    name="whatsapp_issues",
    version=version,
    description="WhatsApp Business interface for creating and rating issues (Provast CRM work orders)",
    author="Venco",
    author_email="chude@venco.co",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
