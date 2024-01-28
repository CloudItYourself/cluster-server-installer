import base64
import json
import logging
import os
import pathlib
import random
import string
import subprocess
import time
from tempfile import TemporaryDirectory
from typing import Final, Optional, Dict, List

import requests
from kubernetes import client, utils
import kubernetes

from cluster_server_installer import LOGGER_NAME
from cluster_server_installer.vpn.vpn_installer import VpnServerInstaller


class K3sInstaller:
    K3S_MAX_STARTUP_TIME_IN_SECONDS: Final[int] = 520
    DASHBOARD_STARTUP_TIME_IN_SECONDS: Final[int] = 500

    RELEVANT_CONFIG_FILE: Final[str] = '/etc/rancher/k3s/k3s.yaml'
    DEPLOYMENTS: Final[List[pathlib.Path]] = [
        pathlib.Path(__file__).parent.parent / 'resources' / 'deployments' / 'certificates' / 'cert-manager.yaml',
        pathlib.Path(__file__).parent.parent / 'resources' / 'deployments' / 'certificates' / 'lets-encrypt.yaml',
        pathlib.Path(__file__).parent.parent / 'resources' / 'deployments' / 'certificates' / 'traefik-middleware.yaml',
        pathlib.Path(__file__).parent.parent / 'resources' / 'deployments' / 'dashboard' / 'rancher-namespace.yaml',
        pathlib.Path(__file__).parent.parent / 'resources' / 'deployments' / 'dashboard' / 'rancher.yaml',
        pathlib.Path(__file__).parent.parent / 'resources' / 'deployments' / 'ciy' / 'redis.yaml',
    ]

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

    def install_kubernetes(self, host_url: str, email: str, registry_url: str, access_key: str):
        self._logger.info("Verifiying k3s installation...")
        if not self.check_if_kubernetes_installed_properly():
            self._logger.info("Installing k3s...")
            if not self._install_kube_env(host_url):
                self._logger.error("K3s installation failed...")
                return

            if not self.create_image_pull_secret(registry_url=registry_url, access_key=access_key):
                self._logger.error("K3s installation failed... failed to create cloud-iy pull permissions")
                return

            if not self._install_deployments(email=email, domain=host_url):
                self._logger.error("K3s installation failed... failed to deploy pre-requisites")
                return
        self._logger.info("K3S installed properly")

    def install_k3s(self, host_url: str) -> bool:
        os.system('tailscale down')
        return os.system(
            f'curl -sfL https://get.k3s.io | K3S_URL=https://{host_url}:6443 INSTALL_K3S_VERSION=v1.27.9+k3s1 INSTALL_K3S_EXEC="server --node-label ciy.persistent_node=True --vpn-auth="name=tailscale,joinKey={VpnServerInstaller.get_headscale_preauthkey()},controlServerURL=http://{host_url}:{VpnServerInstaller.VPN_PORT}"" sh -s -') == 0

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
        return pathlib.Path('/var/lib/rancher/k3s/server/agent-token').read_text().replace("\n", "")

    def _install_kube_env(self, host_url: str) -> bool:
        self._preauth_key = VpnServerInstaller.get_api_key()
        if self.install_k3s(host_url) and os.system('kubectl --help') == 0:
            kubernetes.config.load_kube_config(config_file=K3sInstaller.RELEVANT_CONFIG_FILE)
            self._kube_client = kubernetes.client.CoreV1Api()
            try:
                self._kube_client.create_namespace(
                    body=client.V1Namespace(metadata=client.V1ObjectMeta(name="cloud-iy"))
                )
            except Exception:
                self._logger.warning("Failed to create cloud-iy namespace...")
            if not self.wait_for_metrics_server_to_start():
                return False

            remote_kube_config = base64.b64encode(pathlib.Path(K3sInstaller.RELEVANT_CONFIG_FILE).read_text().replace(
                'server: https://127.0.0.1:6443', f'server: https://{host_url}:6443').encode('utf-8')).decode('utf-8')

            self._create_namespaced_secret(secret_name='cloudiy-server-details', namespace='cloud-iy', fields={
                'vpn-token': base64.b64encode(self._preauth_key.encode('utf-8')).decode('utf-8'),
                'host-source-dns-name': base64.b64encode(host_url.encode('utf-8')).decode('utf-8'),
                'k3s-node-token': base64.b64encode(K3sInstaller.get_k3s_node_token().encode('utf-8')).decode('utf-8'),
                'kubernetes-config-file': base64.b64encode(remote_kube_config.encode('utf-8')).decode('utf-8')})

            return True
        else:
            logging.error("Failed to install k3s")
            return False

    def create_image_pull_secret(self, registry_url: str, access_key: str):
        docker_config = {
            "auths": {
                registry_url: {
                    "username": "usr",
                    "password": access_key,
                    "auth": base64.b64encode(f"usr:{access_key}".encode()).decode()
                }
            }
        }

        self._kube_client.create_namespaced_secret(
            namespace='cloud-iy',
            body=client.V1Secret(
                metadata=client.V1ObjectMeta(name='cloud-iy-credentials'),
                type='kubernetes.io/dockerconfigjson',
                data={".dockerconfigjson": base64.b64encode(json.dumps(docker_config).encode()).decode()}
            )
        )

        return True

    @staticmethod
    def wait_for_dashboard_to_respond(domain: str, timeout_in_seconds: int) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout_in_seconds:
            try:
                resp = requests.get(f"https://dashboard.{domain}")
                if resp.status_code != 404:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _install_deployments(self, email: str, domain: str) -> bool:
        dashboard_initial_pwd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        redis_pwd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        self._create_namespaced_secret(secret_name='redis-pwd', namespace='cloud-iy', fields={
            'redis-pwd': base64.b64encode(redis_pwd.encode('utf-8')).decode('utf-8')
        })

        with TemporaryDirectory() as tmp_dir:
            tmp_dir_path = pathlib.Path(tmp_dir)
            for i, deployment in enumerate(K3sInstaller.DEPLOYMENTS):
                tmp_file_name = tmp_dir_path / deployment.name
                tmp_file_name.write_text(
                    deployment.read_text().replace('${EMAIL}', email).replace('${DOMAIN}', domain).replace(
                        '${DASHBOARD_PASSWORD}', dashboard_initial_pwd).replace('${REDIS_PASSWORD}', redis_pwd))

                if os.system(f'kubectl apply -f {str(tmp_file_name.absolute())}') != 0:
                    logging.exception(f"Failed to install {deployment}")
                    return False
                if i == 0:
                    print("Waiting for cert manager to come up...")
                    time.sleep(45)

        if K3sInstaller.wait_for_dashboard_to_respond(domain, K3sInstaller.DASHBOARD_STARTUP_TIME_IN_SECONDS):
            print(f"Dashboard initial password: {dashboard_initial_pwd}")
            return True
        return False
