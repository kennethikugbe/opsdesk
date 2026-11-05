"""Start the learning app on the local computer only.

The Flask development server is deliberately not a production web server.
"""
import logging

from opsdesk import create_app

app = create_app()
app.logger.setLevel(logging.INFO)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
