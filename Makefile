.PHONY: first-run config up down status logs logs-backend backup restore production-check

first-run:
	@test -f .env || (echo "Не найден .env. Выполните: cp .env.example .env" && exit 2)
	$(MAKE) config
	docker compose up --build -d
	@echo "Локальный контур запущен: web http://localhost:5173, API http://localhost:8000"
	docker compose ps

config:
	docker compose config --quiet

up:
	docker compose up --build

down:
	docker compose down

status:
	docker compose ps

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

backup:
	./scripts/backup.sh

restore:
	@test -n "$(FILE)" || (echo "Укажите FILE=backups/имя.dump" && exit 2)
	./scripts/restore.sh "$(FILE)"

production-check:
	python scripts/deploy_production.py --check-only
