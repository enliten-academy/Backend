from flask import Flask
from main import app

def handler(request):
    """Handle requests in a way that works with Vercel's serverless functions"""
    if request.method == "POST":
        return app.view_functions[request.path[1:]](request)
    return app(request) 