from setuptools import setup, find_packages

setup(
    name="cluster-server-installer",
    version="0.0.1",
    include_package_data=True,
    package_data={'': ['resources/tailscale/*.tgz', 'resources/deployments/certificates/*.yaml',
                       'resources/deployments/dashboard/*.yaml','resources/cert_provider/*']},
    packages=find_packages(),
    install_requires=['kubernetes', 'requests', 'python-crontab']  # Todo: load requirements.txt
)
