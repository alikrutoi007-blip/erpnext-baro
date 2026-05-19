# Baro Service CRM Prototype

Static interactive HTML prototype for the Baro Service ERPNext CRM MVP.

## Open

Double-click:

`C:\Users\epmek\Documents\Erpnext Baro\crm-prototype\index.html`

Or from PowerShell:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro\crm-prototype"
start .\index.html
```

## What is inside

- Live Zadarma call intake queue.
- Repair Job kanban pipeline based on Baro ERPNext statuses.
- Customer chart inspector with phone, address, source, service, equipment, AI summary, transcript and history.
- Action buttons for status movement, diagnostic payment, technician assignment, estimate sending and lost classification.
- Technician dispatch board.
- Warranty, invoice and customer-care follow-up board.
- Local demo state stored in browser localStorage; use `Reset demo` to return to the original sample data.

## Files

- `index.html` - app shell and semantic structure.
- `styles.css` - visual system, layout, responsive behavior and motion.
- `app.js` - demo data, rendering and interactions.

## Notes

This is a visual/UX prototype only. It does not connect to ERPNext, Google Sheets, Zadarma, Make, or OpenAI yet.
