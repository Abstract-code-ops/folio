"""Create SICP Book record and trigger ingestion."""
import os, sys
sys.path.insert(0, '/home/ubuntu/folio/api')
os.chdir('/home/ubuntu/folio/api')
os.environ['DATABASE_URL'] = 'postgresql://postgres.jdvyoywfzvfrcckaytmm:moxbaj-Zynxu6-fugnyx@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres'

import sqlalchemy as sa
from sqlalchemy import create_engine
from uuid import uuid4

engine = create_engine(os.environ['DATABASE_URL'])
storage_url = 'https://jdvyoywfzvfrcckaytmm.supabase.co/storage/v1/object/public/book-pdfs/sicp.pdf'

with engine.begin() as conn:
    book_id = uuid4()
    conn.execute(sa.text("""
        INSERT INTO book (id, title, author, storage_url, ingestion_status, created_at, updated_at)
        VALUES (:id, :title, :author, :url, 'not_started', NOW(), NULL)
    """), {
        'id': book_id,
        'title': "Structure and Interpretation of Computer Programs",
        'author': "Harold Abelson and Gerald Jay Sussman",
        'url': storage_url,
    })
    print(f'Book created: {book_id}')
    print(f'Storage URL: {storage_url}')
