import os
import pathlib
import random
import crontab
from typing import Final, Tuple


class LegoCertificateInstaller:
    LEGO_FILE_PATH: Final[pathlib.Path] = pathlib.Path(__file__).parent.parent / 'resources' / 'cert_provider' / 'lego'
    DNS_TIMEOUT: Final[int] = 10 * 60
    CERT_DIR: Final[pathlib.Path] = pathlib.Path('/usr/local/src/certs')

    def __init__(self, go_daddy_access_key: str, go_daddy_secret_key: str, email: str, domain: str):
        LegoCertificateInstaller.LEGO_FILE_PATH.chmod(0o777)
        self._access_key = go_daddy_access_key
        self._secret_key = go_daddy_secret_key
        self._email = email
        self._domain = domain
        LegoCertificateInstaller.CERT_DIR.mkdir(parents=True, exist_ok=True)

    def install_certificates(self) -> bool:
        command = f'GODADDY_API_KEY={self._access_key} \
        GODADDY_API_SECRET={self._secret_key} \
        GODADDY_PROPAGATION_TIMEOUT={LegoCertificateInstaller.DNS_TIMEOUT} {LegoCertificateInstaller.LEGO_FILE_PATH} --path {str(LegoCertificateInstaller.CERT_DIR.absolute())} --email {self._email} --dns godaddy --domains {self._domain} --accept-tos'
        cert_installed = os.system(command + " run") == 0
        if not cert_installed:
            return False

        cron = crontab.CronTab(user='root')  # replace 'root' with your username if needed
        job = cron.new(command=command + " renew")
        job.from_line(f'{random.randrange(0, 59)} {random.randrange(0, 23)} 20 * *')
        cron.write()

        return True

    def get_certificate_root_path(self) -> Tuple[pathlib.Path, pathlib.Path]:
        (LegoCertificateInstaller.CERT_DIR / 'certificates' / f'{self._domain}.crt').chmod(0o644)
        (LegoCertificateInstaller.CERT_DIR / 'certificates' / f'{self._domain}.key').chmod(0o644)
        return (LegoCertificateInstaller.CERT_DIR / 'certificates' / f'{self._domain}.crt',
                LegoCertificateInstaller.CERT_DIR / 'certificates' / f'{self._domain}.key')
