"""
Lambda entry point. API Gateway invokes `handler`; Mangum translates the
API Gateway event into an ASGI call against the existing FastAPI app, so
none of the route logic in app/main.py needed to change.
"""
from mangum import Mangum

from app.main import app

handler = Mangum(app)
