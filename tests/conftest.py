import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from flask import Flask
from spotify import spotify_bp

@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = 'testkey'
    app.register_blueprint(spotify_bp, url_prefix='/spotify')
    
    @app.route('/')
    def home():
        return "Home Page"
        
    @app.route('/profile')
    def profile():
        return "Profile Page"
    
    app.testing = True
    with app.test_client() as client:
        yield client 