"""End-to-end checks run on a real site and always rolled back:

	bench --site <site> execute happy_kitchen.e2e.<feature>.run

Each run() creates its own E2E-* records, asserts, prints "ok" and rolls everything back, so a
site keeps no trace of it (it is safe on the empty rebuild site; avoid production)."""
