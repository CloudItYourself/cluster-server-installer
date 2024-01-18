from setuptools import setup, find_packages

setup(
    name="cluster-server-installer",
    version="0.0.1",
    include_package_data=True,
    package_data={'': ['cluster_server_installer/resources/tailscale/*.tgz']},
    packages=find_packages(),
    install_requires=['kubernetes', 'requests']  # Todo: load requirements.txt
)
