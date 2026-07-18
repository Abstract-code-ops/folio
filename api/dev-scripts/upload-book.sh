#!/bin/bash
# Upload a PDF from any URL to Supabase Storage.
# Usage: ./dev-scripts/upload-book.sh <url> [filename]
#   url      — public URL of the PDF to download
#   filename — optional name for the file in storage (default: derived from URL)

set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <url> [filename]"
    echo ""
    echo "Downloads a PDF from <url> and uploads it to Supabase Storage."
    echo ""
    echo "Examples:"
    echo "  $0 https://example.com/book.pdf book.pdf"
    exit 1
fi

URL=$1
FILENAME=${2:-$(basename "$URL" | sed 's/%[0-9A-Fa-f]\{2\}/_/g')}

echo "Downloading $URL ..."
curl -sL -o "/tmp/$FILENAME" "$URL"
echo "Downloaded: $(wc -c < "/tmp/$FILENAME") bytes"

# Supabase config — read from .env
if [ -f .env ]; then
    KEY=$(grep SERVICE_ROLE .env | head -1 | cut -d= -f2- | sed "s/^[[:space:]]*'//;s/'[[:space:]]*$//")
    BASE=$(grep SUPABASE_URL .env | head -1 | cut -d= -f2- | sed "s/^[[:space:]]*'//;s/'[[:space:]]*$//" | sed 's/\/$//')
fi

if [ -z "$KEY" ] || [ -z "$BASE" ]; then
    echo "ERROR: Could not read SUPABASE_SERVICE_ROLE_KEY and SUPABASE_URL from .env"
    exit 1
fi

echo "Uploading to book-pdfs/$FILENAME ..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "$BASE/storage/v1/object/book-pdfs/$FILENAME" \
    -H "Authorization: Bearer $KEY" \
    -H "apikey: $KEY" \
    -H "Content-Type: application/pdf" \
    --data-binary @"/tmp/$FILENAME")

if [ "$STATUS" = "200" ]; then
    echo "Upload OK"
    echo ""
    echo "$BASE/storage/v1/object/public/book-pdfs/$FILENAME"
else
    echo "Upload failed (HTTP $STATUS)"
    exit 1
fi
