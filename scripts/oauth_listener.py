"""Automated OAuth Token Receiver and GitHub Secret Synchronizer for cTrader."""
import os
import sys
import json
import socket
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx
import base64
from nacl import public

CLIENT_ID = "47211_trXEREWROuEgTuYltDiclHFA6DwVY06XZSjg5quXs160geCrn2"
CLIENT_SECRET = "8bKOQzqOlrRq5jSy9EI38QZJDkMffjX00QWSaR6J7WofGoGx4R"
REDIRECT_URI = "http://localhost"

auth_code = None

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        
        if "code" in qs:
            auth_code = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>cTrader Connected</title>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0b0f19; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                    .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 40px; text-align: center; max-width: 480px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
                    .check { font-size: 48px; color: #22c55e; margin-bottom: 16px; }
                    h1 { margin: 0 0 12px 0; font-size: 24px; color: #ffffff; }
                    p { margin: 0 0 20px 0; color: #94a3b8; line-height: 1.5; font-size: 15px; }
                    .badge { display: inline-block; background: #166534; color: #86efac; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; }
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="check">&#10004;</div>
                    <h1>cTrader Successfully Authorized!</h1>
                    <p>Your authorization code has been received. Antigravity is now encrypting your token and activating 24/7 cloud execution.</p>
                    <div class="badge">You can safely close this browser window</div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing authorization code in redirect query.")

    def log_message(self, format, *args):
        pass

def run():
    global auth_code
    print("Starting local OAuth listener on http://localhost:80/...", flush=True)
    server = HTTPServer(("127.0.0.1", 80), OAuthHandler)
    server.timeout = 600  # Wait up to 10 minutes
    
    while not auth_code:
        server.handle_request()
        
    print(f"Captured code successfully: {auth_code[:8]}...", flush=True)
    
    # Exchange code for Token
    token_url = "https://openapi.ctrader.com/apps/token"
    res_data = None
    
    candidate_uris = [
        "http://localhost",
        "http://localhost/",
        "https://localhost",
        "https://localhost/",
        "http://127.0.0.1",
        "http://127.0.0.1/",
        "localhost"
    ]
    for r_uri in candidate_uris:
        params = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": r_uri,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
        try:
            r = httpx.get(token_url, params=params, timeout=15.0)
            if r.status_code == 200:
                res_data = r.json()
                print(f"Token exchanged successfully with redirect_uri: {r_uri}")
                break
            else:
                # Try POST as fallback
                r_post = httpx.post(token_url, params=params, timeout=15.0)
                if r_post.status_code == 200:
                    res_data = r_post.json()
                    print(f"Token exchanged successfully via POST with redirect_uri: {r_uri}")
                    break
        except Exception as e:
            print(f"Request error with {r_uri}: {e}")

    if not res_data or "accessToken" not in res_data:
        print(f"Token exchange failed. Last response: {r.text if 'r' in locals() else 'None'}", flush=True)
        return

    access_token = res_data["accessToken"]
    refresh_token = res_data.get("refreshToken", "")
    print(f"SUCCESS: Access Token received! (length: {len(access_token)})", flush=True)
    
    # Save token into .env for local persistence
    env_line = f"CTRADER_ACCESS_TOKEN={access_token}\n"
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            lines = f.readlines()
        lines = [l for l in lines if not l.startswith("CTRADER_ACCESS_TOKEN=")]
        lines.append(env_line)
        with open(".env", "w") as f:
            f.writelines(lines)
    else:
        with open(".env", "w") as f:
            f.write(env_line)
    print("Saved CTRADER_ACCESS_TOKEN to local .env.")

    # Upload CTRADER_ACCESS_TOKEN into GitHub Actions Secrets via API
    proc = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = proc.communicate('protocol=https\nhost=github.com\n\n')
    gh_token = None
    for line in out.splitlines():
        if line.startswith('password='):
            gh_token = line.split('password=', 1)[1].strip()

    if gh_token:
        headers = {
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {gh_token}',
            'X-GitHub-Api-Version': '2022-11-28'
        }
        r_pk = httpx.get('https://api.github.com/repos/siddiqx/Trading-Bot/actions/secrets/public-key', headers=headers)
        if r_pk.status_code == 200:
            pk_data = r_pk.json()
            key_id = pk_data['key_id']
            public_key_b64 = pk_data['key']
            public_key_bytes = base64.b64decode(public_key_b64)
            public_key_obj = public.PublicKey(public_key_bytes)
            sealed_box = public.SealedBox(public_key_obj)
            
            enc_val = base64.b64encode(sealed_box.encrypt(access_token.encode('utf-8'))).decode('utf-8')
            payload = {'encrypted_value': enc_val, 'key_id': key_id}
            r_put = httpx.put('https://api.github.com/repos/siddiqx/Trading-Bot/actions/secrets/CTRADER_ACCESS_TOKEN', headers=headers, json=payload)
            if r_put.status_code in (201, 204):
                print("SUCCESS: CTRADER_ACCESS_TOKEN uploaded to GitHub Actions Secrets!")
            else:
                print(f"Failed to upload secret to GitHub: {r_put.status_code} {r_put.text}")
    
    # Trigger test workflow run
    if gh_token:
        r_disp = httpx.post('https://api.github.com/repos/siddiqx/Trading-Bot/actions/workflows/scanner.yml/dispatches', headers=headers, json={'ref': 'main'})
        if r_disp.status_code == 204:
            print("Triggered initial live cloud scanner workflow run on GitHub Actions!")

if __name__ == "__main__":
    run()
