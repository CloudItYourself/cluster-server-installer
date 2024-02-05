import os
import pathlib
import json
import sys
import random
import crontab
from typing import Final, Tuple


class LegoCertificateInstaller:
    LEGO_FILE_PATH: Final[pathlib.Path] = pathlib.Path(__file__).parent.parent / 'resources' / 'cert_provider' / 'lego'
    DNS_TIMEOUT: Final[int] = 10 * 60
    CERT_DIR: Final[pathlib.Path] = pathlib.Path('/usr/local/src/certs')
    CERT_ORIGINAL_DIR: Final[pathlib.Path] = pathlib.Path('/usr/local/src/orig_certs')
    CERT_DETAILS_FILE: Final[pathlib.Path] = pathlib.Path('/usr/local/src/orig_certs') / 'renewal_details.json'
    CERT_RETRY_COUNT: Final[int] = 5

    def __init__(self, go_daddy_access_key: str, go_daddy_secret_key: str, email: str, domain: str):
        LegoCertificateInstaller.LEGO_FILE_PATH.chmod(0o777)
        self._access_key = go_daddy_access_key
        self._secret_key = go_daddy_secret_key
        self._email = email
        self._domain = domain
        LegoCertificateInstaller.CERT_DIR.mkdir(parents=True, exist_ok=True)
        LegoCertificateInstaller.CERT_ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)

    def install_certificates(self) -> bool:
        cert_installed = False

        command = f'GODADDY_API_KEY={self._access_key} \
        GODADDY_API_SECRET={self._secret_key} \
        GODADDY_PROPAGATION_TIMEOUT={LegoCertificateInstaller.DNS_TIMEOUT} {LegoCertificateInstaller.LEGO_FILE_PATH} --path {str(LegoCertificateInstaller.CERT_ORIGINAL_DIR.absolute())} --email {self._email} --dns godaddy --domains {self._domain} --accept-tos'
        for i in range(LegoCertificateInstaller.CERT_RETRY_COUNT):
            cert_installed = os.system(command + " run") == 0
            if cert_installed:
                break

        if not cert_installed:
            return False

        renewal_details = {
            'GODADDY_API_KEY': self._access_key,
            'GODADDY_API_SECRET': self._secret_key,
            'EMAIL': self._email,
            'DOMAIN': self._domain
        }

        LegoCertificateInstaller.CERT_DETAILS_FILE.write_text(json.dumps(renewal_details))
        LegoCertificateInstaller.alter_certificate_permissions(self._domain)

        cron = crontab.CronTab(user='root')
        job = cron.new(command=f'{str(pathlib.Path(sys.executable).absolute())} renew-certs')
        job.from_line(f'{random.randrange(0, 59)} {random.randrange(0, 23)} 20 * *')
        cron.write()

        return True

    def get_certificate_root_path(self) -> Tuple[pathlib.Path, pathlib.Path]:
        return (LegoCertificateInstaller.CERT_DIR / 'certificates' / f'{self._domain}.crt',
                LegoCertificateInstaller.CERT_DIR / 'certificates' / f'{self._domain}.key')

    @staticmethod
    def alter_certificate_permissions(domain_name: str):
        headscale_cert_path = LegoCertificateInstaller.CERT_DIR / 'certificates' / f'{domain_name}.crt'
        headscale_key_path = LegoCertificateInstaller.CERT_DIR / 'certificates' / f'{domain_name}.key'
        headscale_cert_path.parent.mkdir(parents=True, exist_ok=True)

        headscale_cert_path.write_bytes(
            (LegoCertificateInstaller.CERT_ORIGINAL_DIR / 'certificates' / f'{domain_name}.crt').read_bytes())
        headscale_key_path.write_bytes(
            (LegoCertificateInstaller.CERT_ORIGINAL_DIR / 'certificates' / f'{domain_name}.key').read_bytes())

        headscale_cert_path.chmod(0o777)
        headscale_key_path.chmod(0o777)

    @staticmethod
    def renew_certificates():
        cert_renewed = False
        cert_details = json.loads(LegoCertificateInstaller.CERT_DETAILS_FILE.read_text())
        command = f'GODADDY_API_KEY={cert_details["GODADDY_API_KEY"]} \
        GODADDY_API_SECRET={cert_details["GODADDY_API_SECRET"]} \
        GODADDY_PROPAGATION_TIMEOUT={LegoCertificateInstaller.DNS_TIMEOUT} {LegoCertificateInstaller.LEGO_FILE_PATH} --path {str(LegoCertificateInstaller.CERT_ORIGINAL_DIR.absolute())} --email {cert_details["EMAIL"]} --dns godaddy --domains {cert_details["DOMAIN"]} --accept-tos'
        for i in range(LegoCertificateInstaller.CERT_RETRY_COUNT):
            cert_renewed = os.system(command + " renew") == 0
            if cert_renewed:
                break

        if not cert_renewed:
            return False

        LegoCertificateInstaller.alter_certificate_permissions(cert_details["DOMAIN"])
        return True
