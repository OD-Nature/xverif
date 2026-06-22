.PHONY: all xdebug xbit xentry xloc xberif xcov test full-test clean xcov-test install-xverif-skill install-x-npi-skill _install-agent-skill

PYTHON ?= python3

all: xdebug xbit xentry xloc xberif xcov

xdebug:
	$(MAKE) -C xdebug

xbit:
	$(MAKE) -C xbit

xentry:
	$(MAKE) -C xentry

xloc:
	$(MAKE) -C xloc

xberif:
	$(MAKE) -C xberif

xcov:
	@true

xcov-test:
	$(MAKE) -C xcov PYTHON=$(PYTHON) test

install-xverif-skill:
	$(MAKE) _install-agent-skill SKILL_SRC=skills/xverif SKILL_NAME=xverif

install-x-npi-skill:
	$(MAKE) _install-agent-skill SKILL_SRC=skills/x-npi SKILL_NAME=x-npi

_install-agent-skill:
	@set -eu; \
	src="$(SKILL_SRC)"; \
	name="$(SKILL_NAME)"; \
	ts=$$(date +%Y%m%d-%H%M%S); \
	if [ ! -f "$$src/SKILL.md" ]; then \
		echo "ERROR: missing $$src/SKILL.md"; \
		exit 1; \
	fi; \
	for home in "$$HOME/.codex" "$$HOME/.claude"; do \
		skills_dir="$$home/skills"; \
		dst="$$skills_dir/$$name"; \
		bak="$$home/$$name-skill.bak.$$ts"; \
		echo "==> Installing $$name skill into $$dst"; \
		mkdir -p "$$skills_dir"; \
		if [ -e "$$dst" ]; then \
			echo "    existing skill found: $$dst"; \
			echo "    moving existing skill to backup outside skills dir: $$bak"; \
			mv "$$dst" "$$bak"; \
		else \
			echo "    no existing $$name skill found in $$skills_dir"; \
		fi; \
		echo "    copying $$src -> $$dst"; \
		cp -R "$$src" "$$dst"; \
		echo "    installed $$name skill at $$dst"; \
	done; \
	echo "Done. Backups, if any, were moved to ~/.codex/ or ~/.claude/ so agents do not load old and new skills twice."

test: xdebug xbit xentry xloc xberif xcov
	$(MAKE) -C xdebug PYTHON=$(PYTHON) schema-test
	$(MAKE) -C xdebug PYTHON=$(PYTHON) contract-test
	$(MAKE) -C xdebug unit-test
	$(MAKE) -C xdebug PYTHON=$(PYTHON) mcp-test
	$(MAKE) -C xbit PYTHON=$(PYTHON) test
	$(MAKE) -C xentry PYTHON=$(PYTHON) test
	$(MAKE) -C xloc test
	$(MAKE) -C xberif PYTHON=$(PYTHON) test
	$(MAKE) -C xcov PYTHON=$(PYTHON) test
	$(MAKE) -C xdebug/testdata/combined/active_driver fixture
	regression/run_xdebug_regression.sh

full-test: xdebug xbit xentry xloc xberif
	$(MAKE) -C xbit PYTHON=$(PYTHON) test
	$(MAKE) -C xentry PYTHON=$(PYTHON) test
	$(MAKE) -C xloc test
	$(MAKE) -C xberif PYTHON=$(PYTHON) test
	regression/run_full_regression.sh

clean:
	$(MAKE) -C xdebug clean
	$(MAKE) -C xbit clean
	$(MAKE) -C xentry clean
	$(MAKE) -C xloc clean
	$(MAKE) -C xberif clean
