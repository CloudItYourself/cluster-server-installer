import os
import pathlib
import shutil
import tarfile
from tempfile import TemporaryDirectory
from typing import Final


class HeadScaleHandler:
    HEAD_SCALE_VERSION: Final[str] = '0.22.3'
    HEAD_SCALE_CONFIG_PATH: Final[pathlib.Path] = '/etc/headscale/config.yaml'
    HEAD_SCALE_URL: Final[str] = 'server_url: http://{host_url}:30000'
    HEAD_SCALE_ADDR: Final[str] = 'listen_addr: 0.0.0.0:30000'

    @staticmethod
    def check_if_headsscale_is_installed() -> bool:
        return os.system('systemctl status headscale') == 0

    @staticmethod
    def install_headscale(host_url: str) -> bool:
        status = False
        status &= os.system(f'wget --output-document=headscale.deb \
  https://github.com/juanfont/headscale/releases/download/v{HeadScaleHandler.HEAD_SCALE_VERSION}/headscale_{HeadScaleHandler.HEAD_SCALE_VERSION}_linux_amd64.deb') == 0
        status &= os.system(f'dpkg --install headscale.deb') == 0
        status &= os.system(f'systemctl enable headscale') == 0
        if not status:
            return False
        head_scale_config = HeadScaleHandler.HEAD_SCALE_CONFIG_PATH.read_text()
        HeadScaleHandler.HEAD_SCALE_CONFIG_PATH.write_text(
            head_scale_config.replace('server_url: http://127.0.0.1:8080',
                                      HeadScaleHandler.HEAD_SCALE_URL.format(host_url=host_url)).replace(
                'listen_addr: 127.0.0.1:8080', HeadScaleHandler.HEAD_SCALE_ADDR))
        HeadScaleHandler.HEAD_SCALE_CONFIG_PATH.chmod(0o600)
        status &= os.system(f'systemctl start headscale') == 0
        return status and os.system(f'systemctl status headscale') == 0

    @staticmethod
    def install_tailscale() -> bool:
        tailscale_file = pathlib.Path(__file__).parent / 'resources' / 'tailscale' / 'tailscale_1.56.1_amd64.tgz'
        tailscale_file_path = pathlib.Path('/usr/bin/tailscale')
        tailscaled_file_path = pathlib.Path('/usr/sbin/tailscaled')

        with TemporaryDirectory() as tmp, tarfile.open(tailscale_file, mode="r:gz") as tar:
            tmp_as_path = pathlib.Path(tmp)
            tar.extractall(path=tmp)
            tailscale_file_path.write_bytes((tmp_as_path / 'tailscale_1.56.1_amd64' / 'tailscale').read_bytes())
            tailscaled_file_path.write_bytes((tmp_as_path / 'tailscale_1.56.1_amd64' / 'tailscaled').read_bytes())
            tailscale_file_path.chmod(0o777)
            tailscaled_file_path.chmod(0o777)

            systemd_base_path = pathlib.Path(r'/etc/systemd/system/tailscaled.service')
            systemd_defaults_path = pathlib.Path(r'/etc/default/tailscaled')
            systemd_base_path.write_bytes((tmp_as_path / 'tailscale_1.56.1_amd64' / 'systemd' / 'tailscaled.service').read_bytes())
            systemd_defaults_path.write_bytes((tmp_as_path / 'tailscale_1.56.1_amd64' / 'systemd' / 'tailscaled.defaults').read_bytes())

            return os.system('systemctl enable tailscaled') == 0 and os.system('systemctl start tailscaled')

if __name__ == '__main__':
    HeadScaleHandler.install_tailscale()
