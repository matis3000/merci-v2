import http.server, socketserver, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
S(("127.0.0.1", 8765), http.server.SimpleHTTPRequestHandler).serve_forever()
