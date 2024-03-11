import logging
import os
import pathlib
from typing import Final

from cluster_server_installer import LOGGER_NAME


class CiySchedulerInstaller:
    ENVIRONMENT_FILE_PATH: Final[pathlib.Path] = pathlib.Path('/etc/ciy-scheduling/env.cfg')
    ENVIRONMENT_FILE_CONTENTS: Final[str] = """KUBECONFIG=/etc/rancher/k3s/k3s.yaml
CLUSTER_ACCESS_URL=https://cluster-access.{host}
    """

    CIY_SCHEDULER_SCALE_VERSION: Final[str] = '1.0.0'

    def __init__(self):
        self._logger = logging.getLogger(LOGGER_NAME)

    @staticmethod
    def check_if_ciy_scheduler_is_installed() -> bool:
        return os.system('systemctl is-active quiet ciy-scheduler') == 0

    def install_kube_scheduler(self, host_url: str, gitlab_token: str):
        installation_status = True
        self._logger.info("Checking if ciy-scheduler is installed")
        if not CiySchedulerInstaller.check_if_ciy_scheduler_is_installed():
            installation_status = self.install_ciy_scheduler(host_url=host_url, gitlab_token=gitlab_token)
            self._logger.info(f"ciy-scheduler installation status: {installation_status}")

        if not installation_status:
            self._logger.fatal("Error!! failed to install ciy-scheduler... aborting")
            raise RuntimeError("Failed to install ciy-scheduler... aborting")

    def install_ciy_scheduler(self, host_url: str, gitlab_token: str) -> bool:
        status = True
        status &= os.system(f'wget --header="PRIVATE-TOKEN: {gitlab_token}" --output-document=ciy-scheduler.deb \
  https://gitlab.com/api/v4/projects/54080196/packages/generic/ciy-scheduler/{CiySchedulerInstaller.CIY_SCHEDULER_SCALE_VERSION}/ciy-scheduler-{CiySchedulerInstaller.CIY_SCHEDULER_SCALE_VERSION}-amd64.deb') == 0
        self._logger.info("Ciy-scheduler dpkg in progress")
        status &= os.system(f'dpkg --install ciy-scheduler.deb') == 0

        self._logger.info("Enabling ciy-scheduler service")
        status &= os.system(f'systemctl enable ciy-scheduler') == 0
        if not status:
            return False

        self._logger.info("Configuring ciy-scheduler service")
        CiySchedulerInstaller.ENVIRONMENT_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CiySchedulerInstaller.ENVIRONMENT_FILE_PATH.write_text(
            CiySchedulerInstaller.ENVIRONMENT_FILE_CONTENTS.format(host=host_url))

        self._logger.info("Starting ciy-scheduler")
        status &= os.system(f'systemctl start ciy-scheduler') == 0
        return status
