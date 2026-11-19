.DEFAULT_GOAL := run

PYTHON ?= python
SOURCE ?= examples/stack.cuco
OUTPUT_DIR ?= outputs
CFLAGS ?= -std=c17 -Wall -Wextra

.PHONY: build run

build run:
	@set -e; \
	source_file="$(SOURCE)"; \
	filename="$${source_file##*/}"; \
	name="$${filename%.cuco}"; \
	output_dir="$(OUTPUT_DIR)"; \
	mkdir -p "$$output_dir"; \
	$(PYTHON) main.py build "$$source_file" -o "$$output_dir/$$name.c"; \
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) "$$output_dir/$$name.c" -o "$$output_dir/$$name" $(LDLIBS); \
	if [ "$@" = run ]; then \
		exec "$$output_dir/$$name"; \
	fi
