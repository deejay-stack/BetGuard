from fastapi.responses import JSONResponse


def unavailable(code="catalog_unavailable"):
    return JSONResponse(status_code=503, content={"source": "unavailable", "error": {
        "code": code, "message": "Website classification is unavailable. Local manual rules still work."
    }}, headers={"Retry-After": "5"})


