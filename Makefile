.PHONY: dev stop logs

# ---------------------------------------------------------------------------
# Development — runs Agent0 in Docker with dev credentials
# ---------------------------------------------------------------------------
# Reads _DEV vars from .env and maps them to the standard env vars the app
# expects. Dev dashboard: http://localhost:9998
# ---------------------------------------------------------------------------

-include .env
export

IMAGE := agent0-dev
CONTAINER := agent0-dev
DEV_PORT := 9998

dev: stop
	docker build -t $(IMAGE) .
	docker run -d \
		--name $(CONTAINER) \
		-p $(DEV_PORT):9999 \
		-v agent0-dev-data:/data \
		-e GITHUB_TOKEN=$(GITHUB_TOKEN_DEV) \
		-e GITHUB_USER=$(GITHUB_USER_DEV) \
		-e ANTHROPIC_API_KEY=$(ANTHROPIC_API_KEY) \
		-e WHITELISTED_ORGS=$(WHITELISTED_ORGS) \
		-e LOG_LEVEL=DEBUG \
		$(IMAGE)
	@echo ""
	@echo "  Agent0 dev running as $(GITHUB_USER_DEV)"
	@echo "  Dashboard: http://localhost:$(DEV_PORT)"
	@echo ""

stop:
	-@docker stop $(CONTAINER) 2>/dev/null
	-@docker rm $(CONTAINER) 2>/dev/null

logs:
	docker logs -f $(CONTAINER)
