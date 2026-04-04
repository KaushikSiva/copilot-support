PYTHON ?= python3
VENV ?= .venv
API_DIR := apps/api
WORKER_DIR := apps/worker
HOST ?= 127.0.0.1
PORT ?= 8787
NGROK_URL ?= unmythological-addyson-follicular.ngrok-free.dev

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(VENV)/bin/python -m pip install --upgrade pip setuptools wheel
	$(VENV)/bin/python -m pip install -e $(API_DIR)

install-worker: venv
	$(VENV)/bin/python -m pip install -r $(WORKER_DIR)/requirements.txt

dev:
	$(VENV)/bin/python -m uvicorn app.main:app --app-dir $(API_DIR) --reload --host $(HOST) --port $(PORT)

dev-public: HOST=0.0.0.0
dev-public: dev

ngrok:
	ngrok http --url=$(NGROK_URL) $(PORT)

worker:
	PYTHONPATH=$(PWD)/$(API_DIR):$(PWD)/$(WORKER_DIR) $(VENV)/bin/python -m worker_app start

test:
	cd $(API_DIR) && $(PYTHON) -m unittest discover -s tests -p 'test_*.py'
