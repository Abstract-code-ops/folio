"""FastAPI app entry point."""

from fastapi import FastAPI

from app.routers import books, coverage, notes

app = FastAPI(title="Folio API", version="0.1.0")

app.include_router(books.router)
app.include_router(coverage.router)
app.include_router(notes.router)

