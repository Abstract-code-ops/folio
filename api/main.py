"""FastAPI app entry point."""

from fastapi import FastAPI

from app.routers import books, coverage, notes, qa

app = FastAPI(title="Folio API", version="0.1.0")

app.include_router(books.router)
app.include_router(coverage.router)
app.include_router(notes.router)
app.include_router(qa.router)

