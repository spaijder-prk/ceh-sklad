up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f backend

backup:
	./scripts/backup.sh

restore:
	@test -n "$(FILE)" || (echo "Укажите FILE=backups/имя.dump" && exit 2)
	./scripts/restore.sh "$(FILE)"
