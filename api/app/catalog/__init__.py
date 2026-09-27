"""Question-number catalog for the balloon puzzle.

The package is intentionally import-light: ``models`` and ``rules`` are pure and
safe to import from the disposable OCR process, while ``store``/``service`` pull
in the PostgreSQL driver and must only run inside the API process.
"""
