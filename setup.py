from setuptools import setup, find_packages

setup(
    name="cluster-server-installer",
    version="1.0.2",
    include_package_data=True,
    package_data={'': ['resources/tailscale/*.tgz', 'resources/deployments/certificates/*.yaml',
                       'resources/deployments/dashboard/*.yaml', 'resources/deployments/ciy/*.yaml',
                       'resources/deployments/storage/*.yaml', 'resources/deployments/database/*.yaml',
                       'resources/cert_provider/*','resources/deployments/descheduler/*.yaml' ,
                       'resources/deployments/loadbalancer/*.yaml']},
    packages=find_packages(),
    install_requires=['kubernetes', 'requests', 'python-crontab']
)
