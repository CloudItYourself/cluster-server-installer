import logging
import os
import pathlib
import shutil
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from typing import Final

from cluster_server_installer import LOGGER_NAME
from cluster_server_installer.certificates.lego_certificate_installer import LegoCertificateInstaller

ACL_TEMPLATE = """
{{
  "acls": [
  {{"action": "accept", "src": ["*"], "dst": ["*:*"]}}
  ],
  "autoApprovers": {{
        "routes": {{
            "10.42.0.0/16":        ["cluster-user"],
{cluster_subnets}            "2001:cafe:42::/56": ["cluster-user"],
        }},
    }},
}}
"""


class VpnServerInstaller:
    VPN_PORT: Final[int] = 30000
    HEAD_SCALE_VERSION: Final[str] = '1.0.0'

    HEAD_SCALE_CONFIG_PATH: Final[pathlib.Path] = pathlib.Path('/etc/headscale/config.yaml')
    HEAD_SCALE_ACL_PATH: Final[pathlib.Path] = pathlib.Path('/etc/headscale/acl.json')
    HEAD_SCALE_URL: Final[str] = 'server_url: https://{host_url}:30000'
    HEAD_SCALE_ADDR: Final[str] = 'listen_addr: 0.0.0.0:30000'
    HEAD_SCALE_ACL_LINE: Final[str] = 'acl_policy_path: ""'
    HEAD_SCALE_CERT_PATH: Final[str] = 'tls_cert_path: ""'
    HEAD_SCALE_KEY_PATH: Final[str] = 'tls_key_path: ""'

    def __init__(self):
        self._logger = logging.getLogger(LOGGER_NAME)

    @staticmethod
    def check_if_headscale_is_installed() -> bool:
        return os.system('systemctl is-active quiet headscale') == 0

    @staticmethod
    def check_if_tailscale_is_installed() -> bool:
        return os.system('systemctl is-active quiet tailscaled') == 0

    def install_vpn(self, host_url: str, email: str, gitlab_token: str, godaddy_key: str, godaddy_secret: str):
        installation_status = True
        self._logger.info("Checking if headscale is installed")
        if not VpnServerInstaller.check_if_headscale_is_installed():
            self._logger.info("Installing certificates...")
            cert_installer = LegoCertificateInstaller(godaddy_key, godaddy_secret, email, host_url)

            if not cert_installer.install_certificates():
                raise RuntimeError("Failed to issue headscale certificates")

            self._logger.info("Installing headscale...")
            certs_location = cert_installer.get_certificate_root_path()
            installation_status = self.install_headscale(host_url=host_url, gitlab_token=gitlab_token,
                                                         cert_crt_path=certs_location[0],
                                                         cert_key_path=certs_location[1])
            self._logger.info(f"Headscale installation status: {installation_status}")

        if not installation_status:
            self._logger.fatal("Error!! failed to install headscale... aborting")
            raise RuntimeError("Failed to install headscale... aborting")

        self._logger.info("Checking if tailscale client is installed")
        if not VpnServerInstaller.check_if_tailscale_is_installed():
            self._logger.info("Installing tailscale client...")
            installation_status &= VpnServerInstaller.install_tailscale()
            self._logger.info(f"Tailscale installation status: {installation_status}")

        if not installation_status:
            self._logger.fatal("Error!! failed to install tailscale... aborting")
            raise RuntimeError("Failed to install tailscale... aborting")

    @staticmethod
    def create_headscale_acl_policies():
        string = ''
        template = '            "10.42.{subnet}.0/24":        ["cluster-user"],\n'
        for i in range(255):
            string += template.format(subnet=i)
        return ACL_TEMPLATE.format(cluster_subnets=string)

    def install_headscale(self, host_url: str, gitlab_token: str, cert_crt_path: pathlib.Path,
                          cert_key_path: pathlib.Path) -> bool:
        status = True
        status &= os.system(f'wget --header="PRIVATE-TOKEN: {gitlab_token}" --output-document=headscale.deb \
  https://gitlab.com/api/v4/projects/54080196/packages/generic/headscale-ciy/{VpnServerInstaller.HEAD_SCALE_VERSION}/headscale-ciy-{VpnServerInstaller.HEAD_SCALE_VERSION}-amd64.deb') == 0
        self._logger.info("Headscale dpkg in progress")
        status &= os.system(f'dpkg --install headscale.deb') == 0

        self._logger.info("Enablind headscale service")
        status &= os.system(f'systemctl enable headscale') == 0
        if not status:
            return False

        self._logger.info("Configuring headscale service")
        VpnServerInstaller.HEAD_SCALE_ACL_PATH.write_text(VpnServerInstaller.create_headscale_acl_policies())
        head_scale_config = VpnServerInstaller.HEAD_SCALE_CONFIG_PATH.read_text()
        VpnServerInstaller.HEAD_SCALE_CONFIG_PATH.write_text(
            head_scale_config.replace('server_url: http://127.0.0.1:8080',
                                      VpnServerInstaller.HEAD_SCALE_URL.format(host_url=host_url)).replace(
                'listen_addr: 127.0.0.1:8080', VpnServerInstaller.HEAD_SCALE_ADDR).replace(
                VpnServerInstaller.HEAD_SCALE_ACL_LINE,
                f'acl_policy_path: {str(VpnServerInstaller.HEAD_SCALE_ACL_PATH.absolute())}').replace(
                VpnServerInstaller.HEAD_SCALE_KEY_PATH, f'tls_key_path: {str(cert_key_path.absolute())}').replace(
                VpnServerInstaller.HEAD_SCALE_CERT_PATH, f'tls_cert_path: {str(cert_crt_path.absolute())}'))

        VpnServerInstaller.HEAD_SCALE_CONFIG_PATH.chmod(0o777)
        VpnServerInstaller.HEAD_SCALE_ACL_PATH.chmod(0o777)

        self._logger.info("Starting headscale")
        status &= os.system(f'systemctl start headscale') == 0
        return status and os.system(
            'headscale users create cluster-user') == 0 and VpnServerInstaller.check_if_headscale_is_installed()

    @staticmethod
    def install_tailscale() -> bool:
        tailscale_file = pathlib.Path(__file__).parent.parent / 'resources' / 'tailscale' / 'tailscale_1.56.1_amd64.tgz'
        tailscale_file_path = pathlib.Path('/usr/bin/tailscale')
        tailscaled_file_path = pathlib.Path('/usr/sbin/tailscaled')

        os.system('systemctl unmask tailscaled.service')  # precaution

        with (TemporaryDirectory() as tmp, tarfile.open(tailscale_file, mode="r:gz") as tar):
            tmp_as_path = pathlib.Path(tmp)
            tar.extractall(path=tmp)
            tailscale_file_path.write_bytes((tmp_as_path / 'tailscale_1.56.1_amd64' / 'tailscale').read_bytes())
            tailscaled_file_path.write_bytes((tmp_as_path / 'tailscale_1.56.1_amd64' / 'tailscaled').read_bytes())
            tailscale_file_path.chmod(0o777)
            tailscaled_file_path.chmod(0o777)

            systemd_base_path = pathlib.Path(r'/etc/systemd/system/tailscaled.service')
            systemd_defaults_path = pathlib.Path(r'/etc/default/tailscaled')
            systemd_base_path.write_bytes(
                (tmp_as_path / 'tailscale_1.56.1_amd64' / 'systemd' / 'tailscaled.service').read_bytes())
            systemd_defaults_path.write_bytes(
                (tmp_as_path / 'tailscale_1.56.1_amd64' / 'systemd' / 'tailscaled.defaults').read_bytes())

            return os.system('systemctl enable tailscaled') == 0 and \
                os.system('systemctl start tailscaled') == 0 and VpnServerInstaller.check_if_tailscale_is_installed()

    @staticmethod
    def get_api_key() -> str:
        return subprocess.run(['headscale', 'apikeys', 'create'],
                              stdout=subprocess.PIPE).stdout.decode('utf-8').splitlines()[-1]

    @staticmethod
    def get_headscale_preauthkey() -> str:
        return subprocess.run(['headscale', 'preauthkeys', 'create', '-u', 'cluster-user'],
                              stdout=subprocess.PIPE).stdout.decode('utf-8').splitlines()[-1]


if __name__ == '__main__':
    print(VpnServerInstaller.create_headscale_acl_policies())
