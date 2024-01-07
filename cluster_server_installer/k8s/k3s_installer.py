import base64
import logging
import os
import subprocess
import time
from typing import Final, Optional, Dict
from kubernetes import client
import kubernetes

from cluster_server_installer import LOGGER_NAME
from cluster_server_installer.vpn.vpn_installer import VpnServerInstaller


class K3sInstaller:
    K3S_MAX_STARTUP_TIME_IN_SECONDS: Final[int] = 520
    RELEVANT_CONFIG_FILE: Final[str] = '/etc/rancher/k3s/k3s.yaml'

    def __init__(self):
        self._logger = logging.getLogger(LOGGER_NAME)
        self._kube_client: Optional[kubernetes.client.CoreV1Api] = None
        self._preauth_key: Optional[str] = None

    def check_if_kubernetes_installed_properly(self):
        self._logger.info("Checking if k3s is installed properly...")
        kubernetes_installed = os.system('kubectl --help') == 0
        if not kubernetes_installed:
            self._logger.info("Kubectl not found... reinstalling")
            return False

        kubernetes.config.load_kube_config(config_file=K3sInstaller.RELEVANT_CONFIG_FILE)
        self._logger.info("Waiting for metrics-server...")
        if not K3sInstaller.wait_for_metrics_server_to_start():
            self._logger.error("Metrics-server failed to initialize... uninstalling")
            os.system('/usr/local/bin/k3s-uninstall.sh')
        return False

    @staticmethod
    def wait_for_metrics_server_to_start():
        start = time.time()
        custom_object_api = client.CustomObjectsApi()
        while time.time() - start < K3sInstaller.K3S_MAX_STARTUP_TIME_IN_SECONDS:
            try:
                custom_object_api.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'pods')
                return True
            except Exception as e:
                time.sleep(0.5)
                pass
        return False

    def install_kubernetes(self, host_url: str):
        self._logger.info("Verifiying k3s installation...")
        if not self.check_if_kubernetes_installed_properly():
            self._logger.info("Installing k3s...")
            if not self._install_kube_env(host_url):
                self._logger.error("K3s installation failed...")
                return
        self._logger.info("K3S installed properly")

    def install_k3s(self, host_url: str) -> bool:
        return os.system(
            f'curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.28.5+k3s1 INSTALL_K3S_EXEC="server --vpn-auth="name=tailscale,joinKey={VpnServerInstaller.get_headscale_preauthkey()},controlServerURL=http://{host_url}:{VpnServerInstaller.VPN_PORT}"" sh -s -') == 0

    def _create_namespaced_secret(self, secret_name: str, namespace: str, fields: Dict[str, str]):
        self._kube_client.create_namespaced_secret(
            namespace=namespace,
            body=client.V1Secret(
                api_version='v1',
                metadata=client.V1ObjectMeta(name=secret_name),
                type='Opaque',
                data=fields
            )
        )

    @staticmethod
    def get_k3s_node_token() -> str:
        return subprocess.run(['k3s', 'token', 'create'],
                              stdout=subprocess.PIPE).stdout.decode('utf-8').splitlines()[-1]

    def _install_kube_env(self, host_url: str) -> bool:
        self._preauth_key = VpnServerInstaller.get_api_key()
        if self.install_k3s(host_url) and os.system('kubectl --help') == 0:
            kubernetes.config.load_kube_config(config_file=K3sInstaller.RELEVANT_CONFIG_FILE)
            self._kube_client = kubernetes.client.CoreV1Api()
            self._create_namespaced_secret(secret_name='cloudiy-server-details', namespace='kube-system', fields={
                'vpn-token': base64.b64encode(self._preauth_key.encode('utf-8')).decode('utf-8'),
                'host-source-dns-name': base64.b64encode(host_url.encode('utf-8')).decode('utf-8'),
                'k3s-node-token': base64.b64encode(K3sInstaller.get_k3s_node_token().encode('utf-8')).decode('utf-8')})

            return self.wait_for_metrics_server_to_start()
        else:
            logging.error("Failed to install k3s")
            return False
