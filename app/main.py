from app.api import create_app
from app.routes import router
from app.service import handle_event

app = create_app(router, handle_event)
