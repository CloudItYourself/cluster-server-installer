#! /bin/bash
pip3 install nuitka
nuitka3 --follow-imports --onefile --include-data-dir=./cluster_server_installer/resources=cluster_server_installer/resources cluster_server_installer/main.py