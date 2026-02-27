from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os

from .config import settings
from .database import init_db
from .migrations import run_migrations
from .routers import transactions, categories, rules, imports, stats, accounts, profiles, auth

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])

app = FastAPI(
    title="Finanzmanager",
    description="Selbst-gehostete Finanzmanager-Webanwendung",
    version="2.0.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - restricted to specific origins only
if settings.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    # CSP - allow self only, inline styles needed for the current frontend
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )

    # HSTS only when not in debug mode (assumes HTTPS via reverse proxy)
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# Include routers
app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(categories.router)
app.include_router(rules.router)
app.include_router(imports.router)
app.include_router(stats.router)
app.include_router(accounts.router)
app.include_router(profiles.router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint - no auth required"""
    return {"status": "ok", "version": "2.0.0"}


# Static files for frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # Serve static files or fallback to index.html for SPA routing
        # Use realpath to prevent path traversal via ../ or encoded sequences
        real_frontend = os.path.realpath(frontend_path)
        file_path = os.path.realpath(os.path.join(frontend_path, path))
        if not file_path.startswith(real_frontend + os.sep) and file_path != real_frontend:
            return FileResponse(os.path.join(frontend_path, "index.html"))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_path, "index.html"))


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    run_migrations()
