"""Upload SICP PDF to Supabase Storage."""
import httpx

url_base = 'https://jdvyoywfzvfrcckaytmm.supabase.co'
key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpkdnlveXdmenZmcmNja2F5dG1tIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTM2MjMzOSwiZXhwIjoyMDk2OTM4MzM5fQ.fViXGGuGKDNIco1ejnUBEbx2fS2IU1PFJfJrHH_KwxW0'

with open('/tmp/sicp.pdf', 'rb') as f:
    data = f.read()

print(f'PDF size: {len(data)} bytes')

r = httpx.post(
    f'{url_base}/storage/v1/object/book-pdfs/sicp.pdf',
    headers={
        'Authorization': f'Bearer {key}',
        'apikey': key,
        'Content-Type': 'application/pdf',
    },
    content=data,
)
print(f'Upload status: {r.status_code}')
if r.status_code == 200:
    pub_url = f'{url_base}/storage/v1/object/public/book-pdfs/sicp.pdf'
    print(f'Public URL: {pub_url}')
else:
    print(f'Error: {r.text[:300]}')
