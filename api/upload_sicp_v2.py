"""Upload SICP to Supabase Storage using service role key from .env."""
import httpx

with open('/home/ubuntu/folio/.env') as f:
    for line in f:
        if 'SERVICE_ROLE' in line:
            key = line.split('=', 1)[1].strip().strip("'\"")

url_base = 'https://jdvyoywfzvfrcckaytmm.supabase.co'
url = 'https://web.mit.edu/6.001/6.037/sicp.pdf'

r = httpx.get(url, follow_redirects=True, timeout=30)
data = r.content
print(f'Downloaded: {len(data)} bytes')

r2 = httpx.post(
    f'{url_base}/storage/v1/object/book-pdfs/sicp.pdf',
    headers={
        'Authorization': f'Bearer {key}',
        'apikey': key,
        'Content-Type': 'application/pdf',
        'cache-control': 'public, max-age=31536000, immutable',
        'x-upsert': 'true',
    },
    content=data,
)
print(f'Upload: {r2.status_code}')
if r2.status_code == 200:
    print(f'URL: {url_base}/storage/v1/object/public/book-pdfs/sicp.pdf')
else:
    print(f'Error: {r2.text[:200]}')
