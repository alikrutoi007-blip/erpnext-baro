from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = [line.strip() for line in f.read().splitlines() if line.strip() and not line.startswith("#")]

setup(
    name="baro_crm",
    version="0.0.1",
    description="Baro Service operations CRM for ERPNext",
    author="Baro Service",
    author_email="baroservicellc@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
