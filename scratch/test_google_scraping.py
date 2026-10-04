import urllib.request
import urllib.parse
import re

termo = 'site:guiadosquadrinhos.com "Wolverine" 21 Abril'
url = f"https://www.google.com/search?q={urllib.parse.quote(termo)}&hl=pt-BR&gl=BR"
req = urllib.request.Request(
    url,
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
    }
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        matches = re.findall(r'(?:https(?:%3A%2F%2F|://))(?:www\.)?guiadosquadrinhos\.com(?:%2Fedicao%2F|/edicao/)[^&"\'\s<>]+', html)
        print("Matches:", len(matches))
        for m in matches[:5]:
            decoded = urllib.parse.unquote(m)
            print("Match decodificado:", decoded)
except Exception as e:
    print("Google error:", e)
