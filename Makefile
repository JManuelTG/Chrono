.PHONY: help install build-exe installer uninstall run-gui run-cli test clean

PYTHON ?= python
PIP ?= pip

help:
	@echo ChronoRecovery - Management Commands
	@echo ------------------------------------
	@echo   make install    - Install required dependencies
	@echo   make build-exe  - Build standalone Windows executables
	@echo   make installer  - Run desktop installer (shortcuts & associations)
	@echo   make uninstall  - Uninstall ChronoRecovery desktop app
	@echo   make run-gui    - Launch the ChronoRecovery GUI application
	@echo   make run-cli    - Display CLI commands and options
	@echo   make test       - Run automated test suite
	@echo   make clean      - Clean temporary cache and build artifacts

install:
	$(PIP) install -r requirements.txt

build-exe:
	$(PYTHON) build_exe.py

installer:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts\installer_helper.ps1 -Action Install -SourceDir .

uninstall:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts\installer_helper.ps1 -Action Uninstall

run-gui:
	$(PYTHON) recovery_gui.py

run-cli:
	$(PYTHON) chrono_cli.py --help

test:
	$(PYTHON) -m unittest discover -s . -p "test_*.py" -v

clean:
	@echo Cleaning cache and build artifacts...
	-@rmdir /s /q __pycache__ 2>nul || true
	-@rmdir /s /q recovery_session\__pycache__ 2>nul || true
	-@rmdir /s /q build 2>nul || true
	-@rmdir /s /q dist 2>nul || true
