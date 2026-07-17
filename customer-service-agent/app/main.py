"""智能客服 Agent -- aiohttp Application Entry Point"""

from aiohttp import web
from app.config import get_settings
from app.api.routes import routes

settings = get_settings()


def create_app() -> web.Application:
    app = web.Application()
    app.add_routes(routes)
    return app


def main():
    print(f"[{settings.app_name}] 启动中...")
    print(f"   LLM Provider: {settings.llm_provider}")
    print(f"   LLM Model: {settings.llm_model}")
    print(f"   API: http://{settings.host}:{settings.port}")
    print(f"   聊天页面: http://localhost:{settings.port}")

    app = create_app()
    web.run_app(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
