import argparse

from cluster_server_installer import LOGGER_NAME
from cluster_server_installer.k8s.k3s_installer import K3sInstaller
from cluster_server_installer.utilities.logging import initialize_logger
from cluster_server_installer.vpn.vpn_installer import VpnServerInstaller


def main(host_url: str, email: str, registry: str, access_key: str):
    initialize_logger(LOGGER_NAME)
    vpn_installer = VpnServerInstaller()
    vpn_installer.install_vpn(host_url=host_url)

    k3s_installer = K3sInstaller()
    k3s_installer.install_kubernetes(host_url=host_url, email=email, registry_url=registry, access_key=access_key)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='CloudIY Server Installer',
        description='Installs VPN and K3S')
    parser.add_argument('server_url', type=str)
    parser.add_argument('email', type=str)
    parser.add_argument('registry', type=str)
    parser.add_argument('access_key', type=str)
    args = parser.parse_args()
    main(args.server_url, args.email, args.registry, args.access_key)
