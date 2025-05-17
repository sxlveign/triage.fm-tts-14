"""
Keep-alive server for Replit

This module creates a simple web server that can be pinged to keep the Replit instance active.
"""
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

# Set up logging
logger = logging.getLogger(__name__)

class KeepAliveHandler(BaseHTTPRequestHandler):
    """Simple HTTP request handler to keep Replit alive."""
    
    def do_GET(self):
        """Handle GET requests."""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'triage.fm bot is running!')
    
    def log_message(self, format, *args):
        """Override log_message to avoid polluting the logs."""
        return

def start_server(port=8080):
    """
    Start the keep-alive server.
    
    Args:
        port (int): Port to listen on
    """
    server_address = ('', port)
    httpd = HTTPServer(server_address, KeepAliveHandler)
    
    def run_server():
        logger.info(f"Keep-alive server started on port {port}")
        httpd.serve_forever()
    
    # Start the server in a new thread
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    return httpd

def start_keep_alive():
    """Start the keep-alive server and return the server instance."""
    return start_server()