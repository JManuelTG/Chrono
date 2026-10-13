.PHONY: help install run-gui run-cli test clean

PYTHON ?= python
PIP ?= pip

help:
	@echo ChronoRecovery - Management Commands
	@echo ------------------------------------
	@echo   make install    - Install required dependencies
	@echo   make run-gui    - Launch the ChronoRecovery GUI application
	@echo   make run-cli    - Display CLI commands and options
	@echo   make test       - Run automated test suite
	@echo   make clean      - Clean temporary cache artifacts

install:
	$(PIP) install -r requirements.txt

run-gui:
	$(PYTHON) recovery_gui.py

run-cli:
	$(PYTHON) chrono_cli.py --help

test:
	$(PYTHON) -m unittest test_recovery_session.py

clean:
	@echo Cleaning cache...
	-@rmdir /s /q __pycache__ 2>nul || true
	-@rmdir /s /q recovery_session\__pycache__ 2>nul || true
