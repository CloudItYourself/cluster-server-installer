import os
import pathlib
import random
from typing import Final, Tuple


class LegoCertificateInstaller:
    LEGO_FILE_PATH: Final[pathlib.Path] = pathlib.Path(__file__).parent.parent / 'resources' / 'cert_provider' / 'lego'
    DNS_TIMEOUT: Final[int] = 10 * 60

    def __init__(self, go_daddy_access_key: str, go_daddy_secret_key: str, email: str, domain: str):
        LegoCertificateInstaller.LEGO_FILE_PATH.chmod(0o777)
        self._access_key = go_daddy_access_key
        self._secret_key = go_daddy_secret_key
        self._email = email
        self._domain = domain

    def install_certificates(self) -> bool:
        command = f'GODADDY_API_KEY={self._access_key} \
        GODADDY_API_SECRET={self._secret_key} \
        GODADDY_PROPAGATION_TIMEOUT= \
        lego --dns-timeout {LegoCertificateInstaller.DNS_TIMEOUT}--email {self._email} --dns godaddy --domains {self._domain}'
        cert_installed = os.system(command + " run") == 0
        if not cert_installed:
            return False

        return os.system(
            f'(crontab - l 2 > /dev/null; echo "{random.randrange(0, 59)} {random.randrange(0, 23)} 20 * * {command} renew") | crontab -') == 0

    def get_certificate_root_path(self) -> Tuple[pathlib.Path, pathlib.Path]:
        return (LegoCertificateInstaller.LEGO_FILE_PATH.parent / '.lego' / f'{self._domain}.crt',
                LegoCertificateInstaller.LEGO_FILE_PATH.parent / '.lego' / f'{self._domain}.key')
