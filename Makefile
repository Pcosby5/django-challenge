.PHONY: up down seed test shell migrate

up:
	docker compose up --build

down:
	docker compose down -v

seed:
	docker compose exec web python manage.py migrate
	docker compose exec web python manage.py seed_data

test:
	docker compose exec web pytest orders/tests/ -v

shell:
	docker compose exec web python manage.py shell

migrate:
	docker compose exec web python manage.py makemigrations
	docker compose exec web python manage.py migrate
