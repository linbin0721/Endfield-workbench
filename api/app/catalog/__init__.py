"""Question-number catalogs for balloon and source-circuit puzzles.

The package is intentionally import-light: response models and rule modules are
safe to import from disposable OCR processes, while store and service modules
pull in the PostgreSQL driver and must only run inside the API process.
"""
