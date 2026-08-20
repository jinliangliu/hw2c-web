"""hw2c-web FastAPI backend entry point.

Start: cd web/backend && uvicorn app:app --reload --port 8000
"""

import sys
from pathlib import Path

from paths import get_hw2c_root

# Ensure hw2c sibling project is importable
_HW2C_ROOT = get_hw2c_root()
if _HW2C_ROOT.exists() and str(_HW2C_ROOT) not in sys.path:
    sys.path.insert(0, str(_HW2C_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.parse import router as parse_router
from routes.generate import router as generate_router

app = FastAPI(
    title="hw2c-web",
    description="Web UI for hw2c — parse EDA netlist/BOM, preview hardware model",
    version="0.1.0",
)

# Allow frontend dev server (Vite default) to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parse_router)
app.include_router(generate_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "hw2c-web"}


def main():
    """Entry point for python -m or uvicorn."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
