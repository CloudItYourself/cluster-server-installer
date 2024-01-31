import logging
import os
import pathlib
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from typing import Final

from cluster_server_installer import LOGGER_NAME

ACL_TEMPLATE = """
{
  "acls": [
  {
      "action": "accept",
      "users": ["cluster-user"],
      "ports": ["*"]
    }
  ],
  "autoApprovers": {
        "routes": {
            "10.42.0.0/16":        ["cluster-user"],
            "2001:cafe:42::/56": ["cluster-user"],
        },
    },
}
"""


class VpnServerInstaller:
    VPN_PORT: Final[int] = 30000
    HEAD_SCALE_VERSION: Final[str] = '0.22.3'
    HEAD_SCALE_CONFIG_PATH: Final[pathlib.Path] = pathlib.Path('/etc/headscale/config.yaml')
    HEAD_SCALE_ACL_PATH: Final[pathlib.Path] = pathlib.Path('/etc/headscale/acl.json')
    HEAD_SCALE_URL: Final[str] = 'server_url: http://{host_url}:30000'
    HEAD_SCALE_ADDR: Final[str] = 'listen_addr: 0.0.0.0:30000'
    HEAD_SCALE_ACL_LINE: Final[str] = 'acl_policy_path: ""'

    def __init__(self):
        self._logger = logging.getLogger(LOGGER_NAME)

    @staticmethod
    def check_if_headscale_is_installed() -> bool:
        return os.system('systemctl is-active quiet headscale') == 0

    @staticmethod
    def check_if_tailscale_is_installed() -> bool:
        return os.system('systemctl is-active quiet tailscaled') == 0

    def install_vpn(self, host_url: str):
        installation_status = True
        self._logger.info("Checking if headscale is installed")
        if not VpnServerInstaller.check_if_headscale_is_installed():
            self._logger.info("Installing headscale...")
            installation_status = self.install_headscale(host_url=host_url)
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

    def install_headscale(self, host_url: str) -> bool:
        status = True
        status &= os.system(f'wget --output-document=headscale.deb \
  https://github.com/juanfont/headscale/releases/download/v{VpnServerInstaller.HEAD_SCALE_VERSION}/headscale_{VpnServerInstaller.HEAD_SCALE_VERSION}_linux_amd64.deb') == 0
        self._logger.info("Headscale dpkg in progress")
        status &= os.system(f'dpkg --install headscale.deb') == 0

        self._logger.info("Enablind headscale service")
        status &= os.system(f'systemctl enable headscale') == 0
        if not status:
            return False

        self._logger.info("Configuring headscale service")
        VpnServerInstaller.HEAD_SCALE_ACL_PATH.write_text(ACL_TEMPLATE)
        head_scale_config = VpnServerInstaller.HEAD_SCALE_CONFIG_PATH.read_text()
        VpnServerInstaller.HEAD_SCALE_CONFIG_PATH.write_text(
            head_scale_config.replace('server_url: http://127.0.0.1:8080',
                                      VpnServerInstaller.HEAD_SCALE_URL.format(host_url=host_url)).replace(
                'listen_addr: 127.0.0.1:8080', VpnServerInstaller.HEAD_SCALE_ADDR).replace(
                VpnServerInstaller.HEAD_SCALE_ACL_LINE,
                f'acl_policy_path: {str(VpnServerInstaller.HEAD_SCALE_ACL_PATH.absolute())}'))
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
    VpnServerInstaller.install_vpn()
