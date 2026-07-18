#!/bin/bash
cd /home/ubuntu/folio/web
rm -rf .next
NEXT_PUBLIC_API_URL=/api/proxy npx next build 2>&1 | tail -20
