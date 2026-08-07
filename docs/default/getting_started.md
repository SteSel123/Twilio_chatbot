# Business Knowledge Base (Default)

Add `.md` or `.txt` files in `docs/{your-business}/` or edit `businesses/{tenant_id}.json` to point `docs_subdir` at your folder.

## Example topics to document
- Opening hours and location
- Products or services with prices
- Booking / ordering process
- FAQs and policies (returns, cancellations)
- Contact details

## Tips
- One file per topic keeps search results focused
- Use clear headings — the bot searches by keyword and vector similarity
- Update docs when prices or hours change

## Getting started
1. Copy `businesses/default.json` to `businesses/your-tenant.json`
2. Create `docs/your-tenant/` with your business info
3. Set `docs_subdir` to `your-tenant` in the profile
4. Send WhatsApp messages with header `X-Tenant-Id: your-tenant` (admin) or set `DEFAULT_TENANT_ID`
