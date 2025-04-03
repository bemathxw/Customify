from flask import Flask
from spotify import spotify_bp
import os

def before_all(context):
    """Setup application before running tests."""
    # Determine the root path of your application
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    template_dir = os.path.join(root_path, 'templates')

    # Use a valid import name
    app = Flask('spotify_app', template_folder=template_dir, root_path=root_path)
    app.secret_key = 'testkey'
    app.register_blueprint(spotify_bp, url_prefix='/spotify')

    @app.route('/')
    def home():
        return "Home Page"
        
    @app.route('/profile')
    def profile():
        return "Profile Page"

    app.testing = True
    context.client = app.test_client()
