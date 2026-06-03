from flask import Flask
from flask_cors import CORS
from strawberry.flask.views import GraphQLView

from internal.db import db


def create_app():
    from internal.graph.schema import schema

    app = Flask(__name__)

    CORS(app)

    app.config.from_prefixed_env()

    db.init_app(app)

    # Import models so SQLAlchemy registers them
    from internal.models import user  # noqa: F401

    app.add_url_rule(
        "/graphql",
        view_func=GraphQLView.as_view(
            "graphql_view",
            schema=schema,
            multipart_uploads_enabled=True,
        ),
    )

    @app.route("/")
    def hello():
        return "x-timeline-2 GraphQL API"

    return app
